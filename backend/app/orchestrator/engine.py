"""상태머신 — 누가 다음에 말할지는 LLM 이 아니라 여기가 정한다 (지시서 §9 · §10).

## 왜 코드가 정하는가

LLM 라우터는 디버깅이 지옥이다. "왜 저 직원을 불렀나"에 답할 수 없고,
무한 루프에 빠지면 멈출 방법이 없다. 순서·정지조건·예산은 전부 파이썬이
쥔다. 모델은 **각 칸을 채우는 일**만 한다.

AUTO(§10)에서 모델이 고르는 것은 딱 하나다: 태스크별 담당 직원.
그것도 `assignable()` 안에서만 고를 수 있고, 벗어나면 오케스트레이터가
기본 담당자로 되돌린다. "모델이 정한다"와 "모델이 고른 것을 검사 없이
따른다"는 다르다.

## 흐름

    PLAN ─▶ WRITE_TESTS ─▶ ┌─ IMPLEMENT ─▶ TEST ─▶ REVIEW ─┐ ─▶ FINALIZE ─▶ DONE
                           └──── 반려면 되돌아간다 ────────┘

정지 조건(OR): 태스크 전부 완료 / 라운드 상한 / 비용 상한 / 재기획 상한.

## 비용은 호출 *전에* 검사한다

사후 감지는 상한이 아니라 부고다. 개발자 한 번이 예산을 통째로 넘길 수
있으므로, 다음 호출의 **최악 비용**을 더해서 넘으면 그 자리에서 멈춘다.

## 실행 하나가 스레드 하나

`bus` · `usage` · `project_fs` 가 전부 스레드 로컬로 현재 실행을 찾는다.
그래서 여러 프로젝트를 동시에 돌려도 이벤트와 비용이 섞이지 않는다.
이것이 제공자 인터페이스를 동기로 둔 이유이기도 하다(§7 이탈 기록).
"""
from __future__ import annotations

import hashlib
import os
import threading
import time

from app import bus, config, lang, tenant, usage
from app.agents import employee, roles
from app.agents.schemas import (Criterion, FinalReport, Plan, Routing, Task,
                                TestSuite, Verdict, WorkResult)
from app.database import store
from app.usage import credits
from app.orchestrator import prompts, runner
from app.orchestrator.score import Score
from app.tools import project_fs as pfs

MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "3"))

_runs: dict[str, threading.Thread] = {}
_runs_lock = threading.RLock()
_cancelled: set[str] = set()


class Stop(Exception):
    """계획된 중단. 예산·라운드·재기획 상한에 닿았을 때."""


# ── 실행 관리 ───────────────────────────────────────────────────────
def _reap() -> None:
    with _runs_lock:
        for slug in [s for s, t in _runs.items() if not t.is_alive()]:
            _runs.pop(slug, None)
            _cancelled.discard(slug)


def running_slugs() -> list[str]:
    _reap()
    with _runs_lock:
        return sorted(_runs)


def is_running(slug: str | None = None) -> bool:
    _reap()
    with _runs_lock:
        return slug in _runs if slug else bool(_runs)


# ── 살아 있다는 신호 (DAY 22) ───────────────────────────────────────
#
# ## 왜 필요한가
#
# `new_project()` 는 status 를 `running` 으로 쓰고, 그걸 끝으로 바꾸는 것은
# **실행 스레드뿐**이다. 프로세스가 죽으면 되돌릴 사람이 없다. 그 프로젝트는
# 목록에서 영원히 "진행 중"으로 남고, 화면은 오지 않는 로그를 기다린다.
#
# 서버를 다시 켜는 일은 드물지 않다 — 배포, 재시작, 죽음. 그때마다 좀비가
# 하나씩 쌓인다.
#
# ## 왜 시각을 쓰나
#
# "이 프로세스가 살아 있나"는 **다른 프로세스에서 확인할 수 없다.** pid 는
# 재사용되고, 컨테이너가 바뀌면 의미도 없다. 대신 **최근에 무언가 했는가**를
# 본다 — 실행 중에는 주기적으로 시각을 찍고, 그게 오래되면 죽은 것으로 친다.
#
# 간격보다 넉넉하게 잡는다. 모델 호출 하나가 몇 분씩 걸리므로, 박자가 조금
# 늦었다고 살아 있는 실행을 죽었다고 하면 그게 더 나쁘다.
BEAT_EVERY = 20.0          # 초. 실행 중에 이 간격으로 찍는다
BEAT_STALE = 180.0         # 초. 이보다 오래됐으면 죽은 것으로 본다

_beater: threading.Thread | None = None


def _beat_once() -> None:
    for slug in running_slugs():
        try:
            store.save_meta(slug, {"beat": time.time()})
        except Exception:                                      # noqa: BLE001
            # 박자를 못 찍는다고 실행을 멈추지는 않는다. 다음에 찍힌다.
            pass


def _beat_loop() -> None:
    while True:
        time.sleep(BEAT_EVERY)
        if not running_slugs():
            return
        _beat_once()


def _start_beating() -> None:
    """실행이 있는 동안만 도는 스레드 하나. 실행마다 두지 않는다."""
    global _beater
    if _beater is not None and _beater.is_alive():
        return
    _beater = threading.Thread(target=_beat_loop, daemon=True, name="beat")
    _beater.start()


def sweep_stale_runs() -> list[str]:
    """기동 시 한 번. 아무도 돌리고 있지 않은 '진행 중'을 끝낸다.

    **지우지 않고 중단으로 표시한다.** 그때까지 만든 산출물은 그대로 있고,
    사용자는 무슨 일이 있었는지 알아야 한다 — 조용히 사라지면 자기가 뭘
    잘못했는지 찾게 된다.
    """
    stopped = []
    now = time.time()
    for row in store.list_projects():
        if row.get("status") != "running":
            continue
        slug = row.get("slug")
        if not slug or slug in running_slugs():
            continue
        beat = float(row.get("beat") or row.get("created_at") or 0)
        if now - beat < BEAT_STALE:
            continue          # 다른 인스턴스가 돌리는 중일 수 있다
        store.save_meta(slug, {
            "status": "stopped",
            "stopped_reason": "서버가 다시 시작되어 중단됐습니다. "
                              "그때까지 만든 산출물은 그대로 남아 있습니다.",
        })
        stopped.append(slug)
    return stopped


def cancel(slug: str) -> bool:
    """CEO 의 정지 버튼 (§18).

    스레드를 강제로 죽이지 않는다 — 파일을 반쯤 쓴 상태로 끊기면 산출물이
    깨진다. 대신 표시만 해두고, 다음 단계 경계에서 스스로 멈춘다.
    """
    _reap()
    with _runs_lock:
        if slug not in _runs:
            return False
        _cancelled.add(slug)
    bus.say("SYSTEM", lang.t("log.stopRequested"), kind="error")
    return True


def _check_cancelled(slug: str) -> None:
    with _runs_lock:
        if slug in _cancelled:
            raise Stop("CEO 가 정지시켰습니다.")


def start(requirement: str, attachment_ids: list[str] | None = None,
          owner: str = "local") -> str:
    """새 실행을 시작하고 프로젝트 slug 를 돌려준다 (AUTO, §10).

    동시 실행 수를 제한하는 이유: 각 실행이 모델을 호출하므로 무제한이면
    비용과 요청 한도가 동시에 터진다.
    """
    _reap()
    # **요금제부터 본다.** 좌석 검사보다 먼저여야 한다 — 요금제를 고르지
    # 않은 계정은 좌석이 0 이라, 순서가 바뀌면 "요금제를 고르세요" 대신
    # "동시 실행 한도(0)에 도달했습니다"라는 말이 나간다. 같은 거절이지만
    # 사용자가 할 일이 전혀 다르다.
    tenant.require_runnable(owner)

    # 동시 실행 한도는 요금제가 정한다 (§16). 환경변수 MAX_CONCURRENT 는
    # 그 위의 하드 상한이다 — 요금제를 잘못 적어도 서버가 무너지지 않게.
    seats = min(MAX_CONCURRENT,
                int(credits.plan(credits.wallet(owner).plan)
                    .get("max_concurrent", MAX_CONCURRENT)))
    with _runs_lock:
        if len(_runs) >= seats:
            raise RuntimeError(lang.t("run.concurrent", n=seats))

    # 잔액을 **시작 전에** 본다 (§15). 0 이 된 다음에 막으면 이미 쓴 것이다.
    # 다만 프로젝트 상한 전액이 아니라 **한 번 부를 돈**만 요구한다.
    # 전액을 요구하면 무료 요금제(월 한도 == 프로젝트 상한)는 한 달에
    # 한 번만 시작할 수 있게 되는데, 그건 상한이 아니라 횟수 제한이다.
    credits.reserve(owner, employee.max_worst_case())

    slug = store.new_project(requirement, owner=owner)
    # 요청의 언어를 **여기서** 집는다. 실행 스레드는 요청 컨텍스트를
    # 물려받지 못하므로, 안 집으면 영어로 요청한 사람이 한국어 산출물을
    # 받는다 (DAY 21).
    t = threading.Thread(
        target=_run,
        args=(requirement, slug, attachment_ids or [], owner, lang.current()),
        daemon=True, name=f"run:{slug}")
    with _runs_lock:
        _runs[slug] = t
    store.save_meta(slug, {"beat": time.time()})
    _start_beating()
    t.start()
    return slug


# ── 보조 ────────────────────────────────────────────────────────────
def _spend_guard(rounds: int, about_to_spend: float = 0.0,
                 owner: str = "local") -> None:
    """호출 *전에* 검사한다. 사후 감지는 예산 상한이 아니라 예산 부고다.

    세 가지를 함께 본다: 라운드(§18) · 프로젝트 비용 상한(§18) ·
    남은 크레딧(§15). 크레딧을 여기서 같이 보는 이유는, 상한은 사고를
    막는 장치이고 크레딧은 **사용자가 산 만큼**이라서 둘이 다르기 때문이다.
    """
    if rounds > config.MAX_ROUNDS:
        raise Stop(f"라운드 상한({config.MAX_ROUNDS}) 도달 — 중단합니다.")
    spent = usage.total_cost()
    projected = spent + about_to_spend
    # 요금제 상한과 전역 하드 상한 중 **작은 쪽**. 전역 상한은 요금제를
    # 잘못 적어도 사고가 나지 않게 하는 마지막 방벽이므로, 요금제가 그것을
    # 넘어설 수 있으면 방벽이 아니다.
    limit = min(config.MAX_PROJECT_COST,
                float(credits.plan(credits.wallet(owner).plan)
                      .get("max_project_cost", config.MAX_PROJECT_COST)))
    if projected > limit:
        raise Stop(f"비용 상한(${limit}) — 다음 호출의 최악 비용까지 "
                   f"더하면 ${projected:.2f}가 되어 중단합니다.")
    if credits.usd_to_credits(about_to_spend) > credits.balance(owner):
        raise Stop(f"크레딧이 부족합니다 — 잔액 "
                   f"{credits.balance(owner):.1f} 크레딧으로는 다음 작업을 "
                   f"시작할 수 없습니다.")


def _topo(tasks: list[Task]) -> list[Task]:
    """의존성 순서로 정렬. 순환이 있으면 남은 걸 그냥 뒤에 붙인다.

    순환을 오류로 올리지 않는 이유: 계획을 세운 것도 모델이다. 모델이 만든
    순환 하나 때문에 실행 전체를 버리는 것보다, 순서를 포기하고 진행한 뒤
    검증자에게 판정을 맡기는 편이 낫다.
    """
    done: set[str] = set()
    out: list[Task] = []
    pending = list(tasks)
    while pending:
        ready = [t for t in pending if all(d in done for d in t.deps)]
        if not ready:
            bus.say("SYSTEM", lang.t("log.cycle"), kind="error")
            out.extend(pending)
            break
        for t in ready:
            out.append(t)
            done.add(t.id)
            pending.remove(t)
    return out


def _sig(task: Task) -> str:
    """태스크의 '의미' 지문.

    done 을 `task.id` 로만 관리하면, 재기획에서 전략가가 같은 id 로 다른
    태스크를 정의했을 때 이미 끝났다고 착각하고 건너뛴다. 그래서 id 가
    아니라 지문으로 기억한다.
    """
    raw = f"{task.id}|{task.title}|{task.done_when}|{sorted(task.covers)}|{task.assignee}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _assignee(task: Task) -> str:
    """담당자를 검사한다 (§10).

    모델이 없는 직원이나 맡길 수 없는 직원(기획자·검증자)을 적을 수 있다.
    그대로 따르면 KeyError 로 실행이 죽거나, 검증자가 자기 코드를 검증하게
    된다. 벗어나면 되돌린다 — **고르게 하되 검사 없이 따르지는 않는다.**
    """
    if task.assignee in roles.assignable():
        return task.assignee
    fallback = roles.assignable()[0]
    bus.say("SYSTEM",
            lang.t("log.badAssignee", task=task.title, who=task.assignee,
                   fallback=roles.display_name(fallback)), kind="error")
    return fallback


def _board(plan: Plan, done: set[str], current: str | None) -> list[dict]:
    rows = [{"id": t.id, "title": t.title, "assignee": _assignee(t),
             "status": ("done" if _sig(t) in done
                        else "doing" if t.id == current else "todo")}
            for t in plan.tasks]
    bus.state(tasks=rows)
    return rows


def _apply(result: WorkResult, employee_id: str, *,
           round: int = 0, reason: str = "") -> list[str]:
    """직원이 낸 파일을 실제로 쓴다.

    권한 위반은 실행을 죽이지 않는다 — 그 파일만 거부하고 사실을 남긴다.
    한 파일의 경로가 틀렸다고 나머지 산출물까지 버릴 이유가 없고,
    거부 사실이 로그에 남아야 검증자와 CEO 가 판단할 수 있다.

    `round` 와 `reason` 은 파일 이력에 함께 남는다 — 나중에 이 파일을
    짚고 "몇 라운드에서 어떤 지적을 받고 고쳤나"를 따라갈 수 있어야 한다.
    """
    written: list[str] = []
    for f in result.files:
        try:
            info = pfs.write(f.path, f.content, employee_id,
                             round=round, reason=reason)
        except pfs.Denied as e:
            bus.say(employee_id, lang.t("log.denied", path=f.path, why=e),
                    kind="error")
            continue
        written.append(f.path)
        bus.say(employee_id,
                lang.t("log.created", path=f.path) if info["created"]
                else lang.t("log.updated", path=f.path, n=info["new_lines"]),
                kind="tool")
    return written


def _run_tests(score: Score) -> dict:
    bus.say("SYSTEM", lang.t("log.pytest"), kind="tool")
    r = runner.run(pfs.root())
    score.tests_ran = not r.get("skipped_run")
    score.tests_pass = r["ok"]
    score.tests = {k: r.get(k, 0) for k in ("passed", "failed", "errors")}
    head = (lang.t("test.passed") if r["ok"]
            else lang.t("test.failed", detail=runner.summary_line(r)))
    detail = "\n".join(r["failed_tests"][:5])
    bus.say("SYSTEM", head + (f"\n```\n{detail}\n```" if detail else ""), kind="tool")
    return r


def route(requirement: str) -> Routing:
    """AUTO 라우팅 한 번 (§10). MANUAL 화면이 '누가 맡을까'를 물을 때도 쓴다."""
    roster = [roles.get(i).info() for i in roles.assignable()]
    r = employee.ask(roles.PLANNER, prompts.route(requirement, roster), Routing)
    if r.employee not in roles.assignable():
        r = Routing(employee=roles.assignable()[0],
                    why=f"{r.employee} 는 맡길 수 없는 직원이라 기본 담당자로 배정했습니다.")
    return r


# ── 본체 ────────────────────────────────────────────────────────────
def _run(requirement: str, slug: str, attachment_ids: list[str],
         owner: str = "local", language: str = "ko") -> None:
    """실행 스레드의 입구. 테넌트 자세를 **이 스레드에서 다시 세운다.**

    컨텍스트 변수는 새 스레드로 따라오지 않는다. 여기서 세우지 않으면
    실행 전체가 운영자 키로 돌아간다 — 무료 사용자가 우리 키를 태우고,
    BYOK 고객의 요금을 우리가 낸다. 둘 다 조용히 일어난다.
    """
    with tenant.bind(owner), lang.bind(language):
        _run_bound(requirement, slug, attachment_ids, owner)


def _run_bound(requirement: str, slug: str, attachment_ids: list[str],
               owner: str = "local") -> None:
    # 이 스레드의 컨텍스트를 묶는다. 이후 bus/usage/pfs 호출은 전부 이 실행 소유다.
    bus.bind(slug)
    usage.bind(slug)
    pfs.use(slug)
    bus.reset(slug)

    score = Score()
    m = store.meta(slug)
    any_mock = any(employee.is_mock(e) for e in roles.EMPLOYEES.values())
    store.save_meta(slug, {"mock": any_mock})
    bus.state(project={"slug": slug, "name": m.get("name", ""),
                       "requirement": requirement, "mock": any_mock})
    bus.emit("projects", list=store.list_projects())

    rounds = 0
    done: set[str] = set()
    rows: list[dict] = []
    plan: Plan | None = None
    report: dict = {}

    bus.say("USER", requirement)
    if any_mock:
        bus.say("SYSTEM", lang.t("log.mock"), kind="error")
    attachments_note = ""
    if attachment_ids:
        from app import attachments
        attachments_note = attachments.summary(attachment_ids)
        bus.say("USER", lang.t("log.attached", what=attachments_note),
                kind="tool")
        store.save_meta(slug, {"attachments": attachments_note})

    bus.phase("PLAN", lang.t("phase.plan"))
    score.push()

    try:
        # 1) 기획 ────────────────────────────────────────────────────
        _check_cancelled(slug)
        _spend_guard(rounds := rounds + 1, employee.worst_case_cost(roles.PLANNER), owner)
        plan = employee.ask(roles.PLANNER,
                            prompts.plan(requirement, attachments_note), Plan)
        employee.say(roles.get(roles.PLANNER), plan.message_to_team)
        criteria: list[Criterion] = plan.acceptance_criteria
        if not plan.tasks:
            raise Stop("계획에 태스크가 하나도 없습니다 — 진행할 수 없습니다.")
        score.total_tasks = len(plan.tasks)
        score.ac_total = len(criteria)
        store.save_meta(slug, {"name": plan.project_name,
                               "criteria": [c.model_dump() for c in criteria]})
        bus.state(project={"slug": slug, "name": plan.project_name,
                           "requirement": requirement, "mock": any_mock})
        rows = _board(plan, done, None)
        score.push()

        # 2) 검증자가 테스트를 **먼저** 쓴다 ─────────────────────────
        #    구현자는 이 파일들을 읽지도 못한다. 보면 맞춰 짜기 때문이다.
        bus.phase("WRITE_TESTS", lang.t("phase.write_tests"))
        _check_cancelled(slug)
        _spend_guard(rounds := rounds + 1, employee.worst_case_cost(roles.VERIFIER), owner)
        suite: TestSuite = employee.ask(
            roles.VERIFIER, prompts.write_tests(criteria, plan.tasks), TestSuite)
        employee.say(roles.get(roles.VERIFIER), suite.message_to_team)
        covered: set[str] = set()
        for tf in suite.files:
            path = tf.path if tf.path.startswith("tests/") else f"tests/{tf.path}"
            try:
                pfs.write(path, tf.content, roles.VERIFIER, round=rounds)
            except pfs.Denied as e:
                bus.say(roles.VERIFIER,
                        lang.t("log.testDenied", path=path, why=e),
                        kind="error")
                continue
            covered.update(tf.covers)
            bus.say(roles.VERIFIER,
                    lang.t("log.testWritten", path=path,
                           covers=", ".join(tf.covers) or lang.t("log.unspecified")),
                    kind="tool")
        score.ac_covered = len(covered & {c.id for c in criteria})
        if suite.uncovered:
            bus.say(roles.VERIFIER,
                    lang.t("log.uncovered", ids=", ".join(suite.uncovered)),
                    kind="verdict")
        bus.state(files=store.files_of(slug))
        score.push()

        # 3) 태스크 루프 ─────────────────────────────────────────────
        queue = _topo(plan.tasks)
        i = 0
        while i < len(queue):
            task = queue[i]
            if _sig(task) in done:
                i += 1
                continue
            who = _assignee(task)
            rows = _board(plan, done, task.id)
            rework = 0
            feedback: Verdict | None = None

            while True:
                _check_cancelled(slug)
                bus.phase("IMPLEMENT", f"{roles.get(who).name} · {task.title}")
                _spend_guard(rounds := rounds + 1, employee.worst_case_cost(who), owner)
                bus.state(round=rounds)
                work: WorkResult = employee.ask(
                    who, prompts.implement(task, criteria, pfs.snapshot(who), feedback),
                    WorkResult)
                employee.say(roles.get(who), work.message_to_team)
                # 반려를 받고 다시 쓰는 것이면 그 사유를 이력에 남긴다.
                _apply(work, who, round=rounds,
                       reason=(feedback.message_to_team if feedback else ""))
                bus.state(files=store.files_of(slug))

                bus.phase("TEST", task.title)
                report = _run_tests(score)
                score.push()

                bus.phase("REVIEW", task.title)
                _check_cancelled(slug)
                _spend_guard(rounds, employee.worst_case_cost(roles.VERIFIER), owner)
                # 변경분이 아니라 전체를 보여준다. 부분만 보면 회귀를 놓친다.
                # 담당자의 설명(work.summary)은 **넘기지 않는다** — 자기 합리화에
                # 오염되지 않아야 교차검증이 성립한다.
                verdict: Verdict = employee.ask(
                    roles.VERIFIER,
                    prompts.review(task, criteria, pfs.snapshot(roles.VERIFIER), report),
                    Verdict)
                score.reviews += 1
                icon = "통과" if verdict.verdict == "pass" else f"반려 ({verdict.severity})"
                bus.say(roles.VERIFIER, f"**{icon}** — {verdict.message_to_team}",
                        kind="verdict")
                for f in verdict.findings:
                    bus.say(roles.VERIFIER, f"`{f.file}` · {f.issue}", kind="tool")

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
                                   f"'{task.title}' 에서 진전이 없습니다.")
                    bus.phase("REPLAN", task.title)
                    _spend_guard(rounds := rounds + 1,
                                 employee.worst_case_cost(roles.PLANNER), owner)
                    plan = employee.ask(roles.PLANNER,
                                        prompts.replan(plan, task, verdict), Plan)
                    employee.say(roles.get(roles.PLANNER), plan.message_to_team)
                    score.total_tasks = len(plan.tasks)
                    queue = _topo(plan.tasks)
                    i = -1                       # 큐를 처음부터 다시 훑는다
                    break
            i += 1

        # 4) 최종 검수 ───────────────────────────────────────────────
        bus.phase("FINALIZE", lang.t("phase.finalize"))
        _check_cancelled(slug)
        _spend_guard(rounds := rounds + 1, employee.worst_case_cost(roles.PLANNER), owner)
        final: FinalReport = employee.ask(
            roles.PLANNER,
            prompts.finalize(criteria, pfs.snapshot("SYSTEM"), report), FinalReport)
        employee.say(roles.get(roles.PLANNER), final.message_to_team)
        ids = {c.id for c in criteria}
        score.ac_met = len(set(final.met_criteria) & ids)
        score.push()

        _persist(slug, plan, rows, score, status="done", report=final)
        bus.emit("projects", list=store.list_projects())
        bus.emit("done", ok=not final.unmet_criteria, summary=final.summary,
                 unmet=final.unmet_criteria, score=score.value())

    except Stop as e:
        _fail(slug, plan, rows, score, str(e))
    except employee.EmployeeFailed as e:
        _fail(slug, plan, rows, score, f"직원 호출 실패 — {e}")
    except Exception as e:                       # noqa: BLE001
        _fail(slug, plan, rows, score, f"{type(e).__name__}: {e}")
    finally:
        # 실제로 쓴 만큼만 깎는다 (§15). 예약해두고 돌려주는 방식이 아닌
        # 이유: 실행이 죽으면 돌려줄 사람이 없다. Mock 은 원가가 0 이므로
        # 저절로 0 이 깎인다 — 따로 분기하지 않는다.
        cost = usage.total_cost(slug)
        left = credits.charge(owner, cost)
        store.save_meta(slug, {"credits": round(credits.usd_to_credits(cost), 3),
                               "credits_left": left})
        bus.state(credits=left, credits_used=credits.usd_to_credits(cost))
        with _runs_lock:
            _runs.pop(slug, None)
            _cancelled.discard(slug)
        pfs.release()


def _persist(slug, plan, rows, score, status="running",
             report: FinalReport | None = None) -> None:
    patch = {
        "status": status,
        "score": score.value(),
        "score_detail": score.detail(),
        "tasks": rows,
        "usage": usage.agents_of(slug),
        "cost": round(usage.total_cost(slug), 4),
        "cache_ok": usage.cache_working(slug),
        "criteria": [c.model_dump() for c in plan.acceptance_criteria] if plan else [],
        "files": store.files_of(slug),
    }
    if report is not None:
        patch["report"] = report.model_dump()
    store.save_meta(slug, patch)


def _fail(slug, plan, rows, score, msg: str) -> None:
    bus.say("SYSTEM", lang.t("log.stopped", why=msg), kind="error")
    _persist(slug, plan, rows, score, status="stopped")
    store.save_meta(slug, {"stopped_reason": msg})
    bus.emit("projects", list=store.list_projects())
    bus.emit("done", ok=False, summary=msg, unmet=[], score=score.value())
