"""상태머신. 누가 다음에 말할지는 LLM이 아니라 여기가 정한다."""
import hashlib
import threading

import bus
import config
import runner
import store
import usage
from schemas import Criterion, Plan, Task
from tools import fs

# slug -> Thread. 여러 프로젝트를 동시에 돌릴 수 있다.
_runs: dict[str, threading.Thread] = {}
_runs_lock = threading.Lock()
MAX_CONCURRENT = int(__import__("os").environ.get("MAX_CONCURRENT", "3"))
MOCK = False


class Stop(Exception):
    pass


# ── 완성도 ──────────────────────────────────────────────────────────
# QA 통과율은 일부러 뺐다. QA가 관대할수록 점수가 오르는 순환논리가 되기 때문.
# 남은 두 항목은 QA의 판단과 독립적이다: 태스크 완료는 오케스트레이터가 세고,
# 테스트 통과는 파이썬이 실행한 결과다.
W_TASK, W_TEST = 0.70, 0.30


class Score:
    def __init__(self) -> None:
        self.total_tasks = 0
        self.done_tasks = 0
        self.tests = {"passed": 0, "failed": 0, "errors": 0}
        self.tests_pass = False
        self.tests_ran = False
        self.reviews = 0
        self.passes = 0
        self.reworks = 0
        self.replans = 0
        self.ac_total = 0
        self.ac_covered = 0          # 테스트가 붙은 인수기준 수
        self.ac_met: int | None = None   # 최종 검수 결과

    def value(self) -> int:
        if self.ac_met is not None and self.ac_total:
            return round(100 * self.ac_met / self.ac_total)
        task = self.done_tasks / self.total_tasks if self.total_tasks else 0.0
        test = 1.0 if self.tests_pass else 0.0
        return round(100 * (W_TASK * task + W_TEST * test))

    def push(self) -> None:
        bus.state(score=self.value(), score_detail={
            "tasks": f"{self.done_tasks}/{self.total_tasks}",
            "tests": runner.summary_line({
                "skipped_run": not self.tests_ran, "timed_out": False,
                **self.tests}) if self.tests_ran else "미실행",
            "ac_coverage": f"{self.ac_covered}/{self.ac_total}" if self.ac_total else "—",
            "review_pass_rate": round(100 * self.passes / self.reviews) if self.reviews else 0,
            "reworks": self.reworks,
            "replans": self.replans,
            "criteria": (f"{self.ac_met}/{self.ac_total}"
                         if self.ac_met is not None else "—"),
            "final": self.ac_met is not None,
        })


def _agents():
    if MOCK:
        from agents import mock
        return mock, mock, mock
    from agents import dev, pm, qa
    return pm, dev, qa


def _spend_guard(rounds: int, about_to_spend: float = 0.0) -> None:
    """호출 *전에* 검사한다. 사후 감지는 예산 상한이 아니라 예산 부고다."""
    if rounds > config.MAX_ROUNDS:
        raise Stop(f"라운드 상한({config.MAX_ROUNDS}) 도달 — 중단합니다.")
    projected = usage.total_cost() + about_to_spend
    if projected > config.BUDGET_USD:
        raise Stop(f"비용 상한(${config.BUDGET_USD}) — 다음 호출의 최악 비용까지 더하면 "
                   f"${projected:.2f}가 되어 중단합니다.")


def _topo(tasks: list[Task]) -> list[Task]:
    """의존성 순서로 정렬. 순환이 있으면 남은 걸 그냥 뒤에 붙인다."""
    done, out, pending = set(), [], list(tasks)
    while pending:
        ready = [t for t in pending if all(d in done for d in t.deps)]
        if not ready:
            out.extend(pending)
            break
        for t in ready:
            out.append(t)
            done.add(t.id)
            pending.remove(t)
    return out


def _sig(task: Task) -> str:
    """태스크의 '의미' 지문. REPLAN으로 내용이 바뀌면 지문도 바뀐다.

    done을 task.id로만 관리하면, PM이 같은 id로 다른 태스크를 정의했을 때
    이미 끝났다고 착각하고 건너뛴다. 그래서 id가 아니라 지문으로 기억한다.
    """
    raw = f"{task.id}|{task.title}|{task.done_when}|{sorted(task.covers)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _board(plan: Plan, done: set[str], current: str | None) -> list[dict]:
    rows = [{"id": t.id, "title": t.title,
             "status": "done" if _sig(t) in done else ("doing" if t.id == current else "todo")}
            for t in plan.tasks]
    bus.state(tasks=rows)
    return rows


def start(requirement: str, mock: bool = False,
          attachment_ids: list[str] | None = None) -> str:
    """새 실행을 시작하고 프로젝트 slug를 돌려준다.

    동시 실행 수를 제한하는 이유: 각 실행이 LLM을 호출하므로 무제한이면
    비용과 요청 한도가 동시에 터진다.
    """
    global MOCK
    MOCK = mock
    _reap()
    with _runs_lock:
        if len(_runs) >= MAX_CONCURRENT:
            raise RuntimeError(
                f"동시 실행 한도({MAX_CONCURRENT})에 도달했습니다. "
                f"진행 중인 작업이 끝난 뒤에 시작하세요.")

    slug = store.new_project(requirement)
    t = threading.Thread(target=_run, args=(requirement, slug, attachment_ids or []),
                         daemon=True,
                         name=f"run:{slug}")
    with _runs_lock:
        _runs[slug] = t
    t.start()
    return slug


def _reap() -> None:
    with _runs_lock:
        for slug in [s for s, t in _runs.items() if not t.is_alive()]:
            _runs.pop(slug, None)


def running_slugs() -> list[str]:
    _reap()
    with _runs_lock:
        return sorted(_runs)


def is_running(slug: str | None = None) -> bool:
    """slug를 주면 그 실행만, 안 주면 하나라도 도는지."""
    _reap()
    with _runs_lock:
        return slug in _runs if slug else bool(_runs)


def _run_tests(score: Score) -> dict:
    bus.say("SYSTEM", "격리 환경에서 pytest 실행 중…", kind="tool")
    r = runner.run(fs.root())
    score.tests_ran = not r.get("skipped_run")
    score.tests_pass = r["ok"]
    score.tests = {k: r.get(k, 0) for k in ("passed", "failed", "errors")}
    head = "테스트 통과" if r["ok"] else f"테스트 실패 — {runner.summary_line(r)}"
    detail = "\n".join(r["failed_tests"][:5])
    bus.say("SYSTEM", head + (f"\n```\n{detail}\n```" if detail else ""), kind="tool")
    return r


def _run(requirement: str, slug: str, attachment_ids: list[str]) -> None:
    # 이 스레드의 컨텍스트를 묶는다. 이후 bus/usage/fs 호출은 전부 이 실행 소유가 된다.
    bus.bind(slug)
    usage.bind(slug)
    fs.use(slug)
    bus.reset(slug)
    score = Score()
    m = store.meta(slug)
    bus.state(project={"slug": slug, "name": m["name"], "requirement": requirement})
    bus.emit("projects", list=store.list_projects())

    pm, dev, qa = _agents()
    rounds = 0
    done: set[str] = set()          # 태스크 지문 집합
    rows: list[dict] = []
    plan = None
    report: dict = {}

    bus.say("USER", requirement)
    if attachment_ids:
        import attachments
        bus.say("USER", f"첨부: {attachments.summary(attachment_ids)}", kind="tool")
        store.save_meta(slug, {"attachments": attachments.summary(attachment_ids)})
    bus.phase("PLAN", "PM이 계획을 세우는 중")
    score.push()

    try:
        # 1) 기획
        _spend_guard(rounds := rounds + 1, config.WORST_CASE["PM"])
        plan = pm.plan(requirement, attachment_ids)
        criteria: list[Criterion] = plan.acceptance_criteria
        score.total_tasks = len(plan.tasks)
        score.ac_total = len(criteria)
        store.save_meta(slug, {"name": plan.project_name,
                               "criteria": [c.model_dump() for c in criteria]})
        bus.state(project={"slug": slug, "name": plan.project_name,
                           "requirement": requirement})
        rows = _board(plan, done, None)
        score.push()

        # 2) 검증자가 테스트를 먼저 쓴다 — 구현자는 이 파일들을 건드릴 수 없다
        bus.phase("WRITE_TESTS", "QA가 인수기준으로 테스트 작성")
        _spend_guard(rounds := rounds + 1, config.WORST_CASE["QA"])
        suite = qa.write_tests(criteria, plan.tasks)
        covered: set[str] = set()
        for tf in suite.files:
            path = tf.path if tf.path.startswith("tests/") else f"tests/{tf.path}"
            try:
                fs.write(path, tf.content, "QA")
                covered.update(tf.covers)
                bus.say("QA", f"`{path}` 작성 — 검증 대상 {', '.join(tf.covers) or '미지정'}",
                        kind="tool")
            except fs.Denied as e:
                bus.say("QA", f"테스트 파일 거부됨 — `{path}` ({e})", kind="error")
        score.ac_covered = len(covered & {c.id for c in criteria})
        if suite.uncovered:
            bus.say("QA", "자동 검증 불가로 남긴 인수기준: " + ", ".join(suite.uncovered),
                    kind="verdict")
        bus.state(files=store.files_of(slug))
        score.push()

        # 3) 태스크 루프
        queue = _topo(plan.tasks)
        i = 0
        while i < len(queue):
            task = queue[i]
            if _sig(task) in done:
                i += 1
                continue
            rows = _board(plan, done, task.id)
            rework = 0
            feedback = None

            while True:
                bus.phase("IMPLEMENT", task.title)
                _spend_guard(rounds := rounds + 1, config.WORST_CASE["DEV"])
                bus.state(round=rounds)
                dev.implement(task, criteria, feedback)
                bus.state(files=store.files_of(slug))

                bus.phase("TEST", task.title)
                report = _run_tests(score)
                score.push()

                bus.phase("REVIEW", task.title)
                _spend_guard(rounds, config.WORST_CASE["QA"])
                # 변경분만이 아니라 전체를 보여준다. 부분만 보면 회귀를 놓친다.
                verdict = qa.review(task, criteria, fs.snapshot("QA"), report)
                score.reviews += 1

                if verdict.verdict == "pass":
                    score.passes += 1
                    done.add(_sig(task))
                    score.done_tasks = len(done)
                    rows = _board(plan, done, None)
                    score.push()
                    _persist(slug, plan, rows, score)
                    break

                score.reworks += 1
                score.push()
                rework += 1
                feedback = verdict
                if rework >= config.MAX_REWORK:
                    score.replans += 1
                    if score.replans > config.MAX_REPLANS:
                        raise Stop(f"재기획 상한({config.MAX_REPLANS}) 도달 — "
                                   f"'{task.title}'에서 진전이 없습니다.")
                    bus.phase("REPLAN", task.title)
                    _spend_guard(rounds := rounds + 1, config.WORST_CASE["PM"])
                    plan = pm.replan(plan, task, verdict)
                    score.total_tasks = len(plan.tasks)
                    queue = _topo(plan.tasks)
                    i = -1                       # 큐를 처음부터 다시 훑는다
                    break
            i += 1

        # 4) 최종 검수
        bus.phase("FINALIZE", "최종 검수")
        _spend_guard(rounds := rounds + 1, config.WORST_CASE["PM"])
        final = pm.finalize(plan, fs.snapshot("SYSTEM"), report)
        ids = {c.id for c in criteria}
        score.ac_met = len(set(final.met_criteria) & ids)
        score.push()

        _persist(slug, plan, rows, score, status="done")
        bus.emit("projects", list=store.list_projects())
        bus.emit("done", ok=not final.unmet_criteria, summary=final.summary,
                 unmet=final.unmet_criteria, score=score.value())

    except Stop as e:
        _fail(slug, plan, rows, score, str(e))
    except Exception as e:
        _fail(slug, plan, rows, score, f"{type(e).__name__}: {e}")
    finally:
        with _runs_lock:
            _runs.pop(slug, None)


def _persist(slug, plan, rows, score, status="running") -> None:
    store.save_meta(slug, {
        "status": status,
        "score": score.value(),
        "tasks": rows,
        "usage": usage.agents_of(slug),
        "cost": round(usage.total_cost(slug), 4),
        "cache_ok": usage.cache_working(slug),
        "criteria": [c.model_dump() for c in plan.acceptance_criteria] if plan else [],
    })


def _fail(slug, plan, rows, score, msg: str) -> None:
    bus.say("SYSTEM", f"중단: {msg}", kind="error")
    _persist(slug, plan, rows, score, status="stopped")
    bus.emit("projects", list=store.list_projects())
    bus.emit("done", ok=False, summary=msg, unmet=[], score=score.value())
