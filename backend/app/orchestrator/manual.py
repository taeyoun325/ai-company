"""MANUAL 모드 — CEO 가 직원을 직접 지목해 지시한다 (지시서 §11).

## AUTO 와 무엇이 다른가

AUTO(§10)는 오케스트레이터가 계획부터 검수까지 끝까지 돌린다. MANUAL 은
**CEO 가 한 수씩 둔다.** 누구에게, 무엇을, 지금. 검증도 CEO 가 누를 때만
돈다.

## 그래도 권한 경계는 같다

"CEO 가 시켰다"는 이유로 작가가 `src/` 에 쓰게 해주지 않는다. 직원의
권한은 §8 의 직원 표 하나에서만 나온다. 여기에 예외를 두면 두 경로가
서로 다른 규칙을 갖게 되고, 그 차이가 곧 구멍이 된다.

## 대화 이력을 직원별로 따로 둔다

한 지시의 결과를 다음 지시에서 이어받아야 CEO 가 "거기서 이것만 고쳐줘"
라고 말할 수 있다. 다만 직원끼리는 섞지 않는다 — 검증자가 개발자의
자기 설명을 읽으면 교차검증이 오염된다(§9 와 같은 이유).

## 예산은 AUTO 와 같은 상한을 쓴다

MANUAL 이라고 상한이 없으면, 버튼을 스무 번 누르는 것으로 상한을 우회할
수 있다. 호출 *전에* 최악 비용을 더해서 검사한다.
"""
from __future__ import annotations

import threading

from app import bus, config, usage
from app.agents import employee, roles
from app.agents.schemas import Verdict, WorkResult
from app.database import store
from app.orchestrator import prompts, runner
from app.providers.base import Message
from app.tools import project_fs as pfs

MAX_HISTORY = 12          # 직원 한 명당 유지할 메시지 수(user+assistant 합계)

_lock = threading.RLock()
# (slug, employee_id) -> 메시지 목록
_history: dict[tuple[str, str], list[Message]] = {}
# slug -> 지금 이 프로젝트에서 누가 일하는 중인가
_busy: dict[str, str] = {}


class Busy(RuntimeError):
    """이 프로젝트에서 이미 누군가 일하고 있다."""


def history(slug: str, employee_id: str) -> list[Message]:
    with _lock:
        return list(_history.get((slug, employee_id), []))


def clear_history(slug: str, employee_id: str | None = None) -> None:
    with _lock:
        if employee_id is None:
            for key in [k for k in _history if k[0] == slug]:
                _history.pop(key, None)
        else:
            _history.pop((slug, employee_id), None)


def _remember(slug: str, employee_id: str, user: str, assistant: str) -> None:
    with _lock:
        msgs = _history.setdefault((slug, employee_id), [])
        msgs.append(Message("user", user))
        msgs.append(Message("assistant", assistant))
        # 오래된 것부터 버린다. 무한히 쌓이면 한 번 호출에 컨텍스트 전체를
        # 다시 보내게 되고, 비용이 대화 길이의 제곱으로 자란다.
        del msgs[:-MAX_HISTORY]


def busy_employee(slug: str) -> str | None:
    with _lock:
        return _busy.get(slug)


def is_busy(slug: str) -> bool:
    return busy_employee(slug) is not None


class _Session:
    """한 번의 MANUAL 지시 동안 스레드 컨텍스트를 묶는다.

    AUTO 와 같은 방식으로 묶어야 이벤트·비용·파일이 이 프로젝트 것으로 잡힌다.
    """

    def __init__(self, slug: str, employee_id: str):
        self.slug = slug
        self.employee_id = employee_id

    def __enter__(self):
        with _lock:
            if self.slug in _busy:
                raise Busy(f"{roles.get(_busy[self.slug]).name}이(가) 아직 "
                           f"작업 중입니다. 끝난 뒤에 지시하세요.")
            _busy[self.slug] = self.employee_id
        bus.bind(self.slug)
        usage.attach(self.slug)
        pfs.use(self.slug)
        return self

    def __exit__(self, *exc):
        with _lock:
            _busy.pop(self.slug, None)
        pfs.release()
        return False


def _guard(employee_id: str, slug: str) -> None:
    """호출 전 예산 검사. MANUAL 이라고 상한을 비켜가지 않는다."""
    projected = usage.total_cost(slug) + employee.worst_case_cost(employee_id)
    if projected > config.MAX_PROJECT_COST:
        raise RuntimeError(
            f"비용 상한(${config.MAX_PROJECT_COST}) — 이 호출의 최악 비용까지 "
            f"더하면 ${projected:.2f}가 되어 지시를 받지 않습니다.")


def _persist(slug: str) -> None:
    store.save_meta(slug, {
        "usage": usage.agents_of(slug),
        "cost": round(usage.total_cost(slug), 4),
        "files": store.files_of(slug),
    })
    bus.state(files=store.files_of(slug))


def instruct(slug: str, employee_id: str, message: str) -> dict:
    """직원 한 명에게 지시한다 (§11).

    쓸 수 있는 직원이면 파일을 만들게 하고(구조화 응답), 쓸 수 없는 직원
    (전략가)이면 글로 답하게 한다. 같은 스키마를 억지로 씌우지 않는 이유:
    파일을 쓸 수 없는 직원에게 `files` 를 요구하면 빈 배열을 채워 넣으려고
    없는 파일을 지어낸다.
    """
    if not store.exists(slug):
        raise KeyError(f"없는 프로젝트: {slug}")
    e = roles.get(employee_id)
    message = message.strip()
    if not message:
        raise ValueError("지시 내용이 비어 있습니다")

    with _Session(slug, employee_id):
        _guard(employee_id, slug)
        bus.say("USER", f"@{e.name}({e.role}) {message}")
        bus.phase("MANUAL", f"{e.name} · 직접 지시")
        hist = history(slug, employee_id)

        if not e.writes:
            text = employee.ask_text(employee_id, message, hist)
            employee.say(e, text)
            _remember(slug, employee_id, message, text)
            _persist(slug)
            return {"employee": employee_id, "text": text, "files": []}

        ask = (
            f"# CEO 의 지시\n{message}\n\n"
            f"# 지금까지의 산출물\n"
            + prompts.files_block(pfs.snapshot(employee_id))
            + "\n\n# 할 일\n지시된 것만 처리하세요. 파일은 전문으로 내보냅니다.\n"
              "`...생략...` 은 그대로 저장되어 코드를 지웁니다.\n"
              f"쓸 수 있는 폴더는 {', '.join(a + '/' for a in e.writes)} 뿐입니다."
        )
        work: WorkResult = employee.ask(employee_id, ask, WorkResult)
        employee.say(e, work.message_to_team)

        written: list[str] = []
        for f in work.files:
            try:
                info = pfs.write(f.path, f.content, employee_id)
            except pfs.Denied as ex:
                # "CEO 가 시켰다"는 권한의 근거가 아니다. 거부하고 사실을 남긴다.
                bus.say(employee_id, f"`{f.path}` 거부됨 — {ex}", kind="error")
                continue
            written.append(f.path)
            bus.say(employee_id,
                    f"`{f.path}` " + ("새로 만듦" if info["created"]
                                      else f"수정 ({info['new_lines']}줄)"),
                    kind="tool")

        _remember(slug, employee_id, message,
                  f"{work.message_to_team}\n{work.summary}")
        _persist(slug)
        return {"employee": employee_id, "text": work.message_to_team,
                "summary": work.summary, "self_check": work.self_check,
                "files": written}


def verify(slug: str) -> dict:
    """CEO 가 누를 때만 도는 검증 (§11).

    AUTO 처럼 매 태스크마다 자동으로 돌지 않는다. 대신 **같은 검증자**가
    **같은 방식**으로 본다 — 담당자의 설명 없이 산출물 원문과 테스트
    결과만. MANUAL 이라고 검증 기준을 느슨하게 하면, 두 모드의 결과물이
    같은 이름으로 나가면서 품질만 다르게 된다.
    """
    if not store.exists(slug):
        raise KeyError(f"없는 프로젝트: {slug}")

    with _Session(slug, roles.VERIFIER):
        _guard(roles.VERIFIER, slug)
        bus.phase("REVIEW", "CEO 요청으로 검증")
        report = runner.run(pfs.root())
        bus.say("SYSTEM", runner.summary_line(report), kind="tool")

        m = store.meta(slug)
        criteria = _criteria_of(m)
        task = _pseudo_task(m)
        v: Verdict = employee.ask(
            roles.VERIFIER,
            prompts.review(task, criteria, pfs.snapshot(roles.VERIFIER), report),
            Verdict)
        icon = "통과" if v.verdict == "pass" else f"반려 ({v.severity})"
        bus.say(roles.VERIFIER, f"**{icon}** — {v.message_to_team}", kind="verdict")
        for f in v.findings:
            bus.say(roles.VERIFIER, f"`{f.file}` · {f.issue}", kind="tool")
        store.save_meta(slug, {"last_verdict": v.model_dump(),
                               "usage": usage.agents_of(slug),
                               "cost": round(usage.total_cost(slug), 4)})
        return {"verdict": v.model_dump(), "report": report}


def _criteria_of(meta: dict):
    from app.agents.schemas import Criterion
    rows = meta.get("criteria") or []
    if rows:
        return [Criterion(**r) for r in rows]
    # MANUAL 로만 만든 프로젝트에는 인수기준이 없다. 요구사항 한 줄을
    # 기준으로 세운다 — 기준 없이 검증하면 검증자가 기준을 지어낸다.
    return [Criterion(id="ac1", text=meta.get("requirement", "요구사항을 만족한다"))]


def _pseudo_task(meta: dict):
    from app.agents.schemas import Task
    return Task(id="manual", title="CEO 직접 지시로 만든 산출물 전체",
                assignee="developer", deps=[], files=[], covers=["ac1"],
                done_when=meta.get("requirement", "요구사항을 만족한다"))


def open_project(requirement: str, owner: str = "local") -> str:
    """MANUAL 전용 빈 프로젝트를 연다. 계획 단계 없이 바로 지시할 수 있어야 한다."""
    slug = store.new_project(requirement, owner=owner)
    store.save_meta(slug, {"status": "manual", "mode": "manual"})
    bus.bind(slug)
    bus.say("USER", requirement)
    bus.say("SYSTEM", "MANUAL 모드입니다. 직원을 골라 직접 지시하세요.", kind="verdict")
    return slug
