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

## 대화는 파일에 남는다 (DAY 22 에 고침)

그 전까지 대화 이력은 프로세스 메모리에만 있었다. 서버를 다시 켜면
**진행 중이던 대화가 통째로 사라졌고**, 사용자는 자기가 무슨 지시를
했는지 다시 떠올려야 했다. 인스턴스를 둘 띄우면 요청마다 다른 기억을
가진 회사를 만나게 되는 것도 같은 이유다.

이제 프로젝트 폴더 안(`.manual.json`)에 쓴다. 메모리는 사본이고 파일이
진실이다 — §12 의 규칙을 대화에도 적용한다.

## 예산은 AUTO 와 같은 상한을 쓴다

MANUAL 이라고 상한이 없으면, 버튼을 스무 번 누르는 것으로 상한을 우회할
수 있다. 호출 *전에* 최악 비용을 더해서 검사한다.

## 크레딧도 AUTO 와 같이 깎는다 (DAY 19 에 고침)

DAY 18 까지 MANUAL 은 **크레딧을 한 개도 깎지 않았다.** 상한은 걸려
있었지만 그건 프로젝트 하나의 상한이고, 프로젝트는 얼마든지 새로 열 수
있다. 요금제를 붙이는 순간 이건 구멍이 아니라 무료 이용권이 된다 —
AUTO 는 결제하고 MANUAL 은 공짜인 제품이 되기 때문이다.

지시 한 번을 AUTO 의 한 라운드와 같게 취급한다: 시작 전에 잔액을 보고,
끝나면 **그 지시로 실제로 늘어난 만큼** 깎는다.
"""
from __future__ import annotations

import json
import os
import threading

from app import bus, config, lang, safeio, tenant, usage
from app.agents import employee, roles
from app.agents.schemas import Verdict, WorkResult
from app.database import index, store
from app.orchestrator import prompts, runner
from app.providers.base import Message
from app.tools import project_fs as pfs
from app.usage import credits

MAX_HISTORY = 12          # 직원 한 명당 유지할 메시지 수(user+assistant 합계)

_lock = threading.RLock()
# slug -> {직원 id -> 메시지 목록}. **메모리는 사본이고 파일이 진실이다.**
_history: dict[str, dict[str, list[Message]]] = {}
# 한 번의 지시가 잡고 있는 시간의 상한 (초). 모델 호출이 길어질 수 있어
# 넉넉히 두되, 잠근 인스턴스가 죽어도 이만큼 뒤에는 풀린다 — 영원히 잠긴
# 프로젝트는 고장이지 안전이 아니다.
LEASE = float(os.getenv("MANUAL_LEASE", "600"))


class Busy(RuntimeError):
    """이 프로젝트에서 이미 누군가 일하고 있다."""


# 대화 이력이 사는 파일. 프로젝트 폴더 안이다 — 산출물과 같은 자리에
# 두면 프로젝트를 지울 때 대화도 함께 사라진다(§12: 파일이 진실).
HISTORY_FILE = ".manual.json"


def _history_path(slug: str):
    return store.dir_of(slug) / HISTORY_FILE


def _load_history(slug: str) -> dict[str, list[Message]]:
    """파일에서 이 프로젝트의 대화를 읽는다.

    읽지 못하면 **빈 대화**로 친다. 여기서 예외를 올리면 파일 하나가
    깨진 것 때문에 MANUAL 화면 전체가 열리지 않는다 — 그건 대화를
    잃는 것보다 나쁘다.
    """
    try:
        raw = json.loads(_history_path(slug).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, list[Message]] = {}
    for who, msgs in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(msgs, list):
            continue
        out[who] = [Message(m.get("role", "user"), m.get("content", ""))
                    for m in msgs if isinstance(m, dict)]
    return out


def _save_history(slug: str, table: dict[str, list[Message]]) -> None:
    try:
        safeio.write_json(
            _history_path(slug),
            {who: [{"role": m.role, "content": m.content} for m in msgs]
             for who, msgs in table.items() if msgs},
            indent=1)
    except OSError:
        # 저장 실패가 지시를 막지는 않는다. 이번 대화는 메모리에 남는다.
        pass


def _table(slug: str) -> dict[str, list[Message]]:
    """이 프로젝트의 대화표. 메모리에 없으면 파일에서 올린다.

    메모리는 **사본**이다. 서버를 다시 켜면 비어 있고, 그때 파일에서
    다시 올라온다 — DAY 22 이전에는 그 자리에서 대화가 사라졌다.
    """
    table = _history.get(slug)
    if table is None:
        table = _load_history(slug)
        _history[slug] = table
    return table


def history(slug: str, employee_id: str) -> list[Message]:
    with _lock:
        return list(_table(slug).get(employee_id, []))


def clear_history(slug: str, employee_id: str | None = None) -> None:
    with _lock:
        table = _table(slug)
        if employee_id is None:
            table.clear()
        else:
            table.pop(employee_id, None)
        _save_history(slug, table)


def _remember(slug: str, employee_id: str, user: str, assistant: str) -> None:
    with _lock:
        table = _table(slug)
        msgs = table.setdefault(employee_id, [])
        msgs.append(Message("user", user))
        msgs.append(Message("assistant", assistant))
        # 오래된 것부터 버린다. 무한히 쌓이면 한 번 호출에 컨텍스트 전체를
        # 다시 보내게 되고, 비용이 대화 길이의 제곱으로 자란다.
        del msgs[:-MAX_HISTORY]
        _save_history(slug, table)


def forget_cached_history() -> None:
    """메모리 사본을 버린다. 테스트와, 파일을 밖에서 고친 경우에 쓴다."""
    with _lock:
        _history.clear()


def busy_employee(slug: str) -> str | None:
    """지금 이 프로젝트를 잡고 있는 직원. 인스턴스를 넘어 본다."""
    return index.lock_holder(slug)


def is_busy(slug: str) -> bool:
    return busy_employee(slug) is not None


class _Session:
    """한 번의 MANUAL 지시 동안 스레드 컨텍스트를 묶는다.

    AUTO 와 같은 방식으로 묶어야 이벤트·비용·파일이 이 프로젝트 것으로 잡힌다.
    """

    def __init__(self, slug: str, employee_id: str, owner: str = "local"):
        self.slug = slug
        self.employee_id = employee_id
        self.owner = owner
        self._tenant = None
        self._before = 0.0

    def __enter__(self):
        # 점유는 **인스턴스 밖**에 둔다 (DAY 22). 파이썬 딕셔너리로 표시하면
        # 두 대로 띄웠을 때 같은 프로젝트에 두 지시가 동시에 들어가고,
        # 파일 쓰기는 각자 원자적이지만 마지막에 쓴 쪽이 이긴다 — 앞 사람의
        # 작업이 조용히 사라진다.
        held_by = index.acquire_lock(self.slug, self.employee_id, LEASE)
        if held_by is not None:
            raise Busy(lang.t("manual.busy",
                              name=roles.display_name(held_by)
                              if roles.exists(held_by) else held_by))
        try:
            # 어느 키로 부를지 먼저 정한다 (DAY 19). BYOK 인데 키가 없으면
            # 여기서 멈춘다 — 운영자 키로 대신 부르지 않는다.
            tenant.require_runnable(self.owner)
            credits.reserve(self.owner, employee.worst_case_cost(self.employee_id))
        except BaseException:
            index.release_lock(self.slug, self.employee_id)
            raise
        self._tenant = tenant.bind(self.owner)
        self._tenant.__enter__()
        bus.bind(self.slug)
        usage.attach(self.slug)
        pfs.use(self.slug)
        self._before = usage.total_cost(self.slug)
        return self

    def __exit__(self, *exc):
        # **이 지시로 늘어난 만큼만** 깎는다. 프로젝트 누적으로 깎으면
        # 지시를 한 번 더 할 때마다 앞의 지시를 다시 청구하게 된다.
        spent = max(0.0, usage.total_cost(self.slug) - self._before)
        try:
            if spent:
                left = credits.charge(self.owner, spent)
                bus.state(credits=left,
                          credits_used=credits.usd_to_credits(spent))
        finally:
            if self._tenant is not None:
                self._tenant.__exit__(*exc)
                self._tenant = None
            index.release_lock(self.slug, self.employee_id)
            pfs.release()
        return False


def _guard(employee_id: str, slug: str, owner: str = "local") -> None:
    """호출 전 예산 검사. MANUAL 이라고 상한을 비켜가지 않는다.

    요금제 상한과 전역 하드 상한 중 **작은 쪽**을 쓴다 — AUTO 의
    `_spend_guard` 와 같은 규칙이다. 두 경로가 다른 상한을 쓰면, 싼
    요금제로 MANUAL 만 돌리는 것이 상한 우회가 된다.
    """
    limit = min(config.MAX_PROJECT_COST,
                float(credits.plan(credits.wallet(owner).plan)
                      .get("max_project_cost", config.MAX_PROJECT_COST)))
    about_to_spend = employee.worst_case_cost(employee_id)
    projected = usage.total_cost(slug) + about_to_spend
    if projected > limit:
        raise RuntimeError(
            lang.t("manual.cost", limit=limit,
                   projected=f"{projected:.2f}"))
    # 프로젝트 상한 위의 두 번째 벽(§18) — AUTO 의 `_spend_guard` 와 같은 검사.
    # MANUAL 이라고 비켜가면, 싼 요금제로 MANUAL 만 돌리는 것이 우회가 된다.
    credits.check_global_caps(owner, about_to_spend)


def _persist(slug: str) -> None:
    store.save_meta(slug, {
        "usage": usage.agents_of(slug),
        "cost": round(usage.total_cost(slug), 4),
        "files": store.files_of(slug),
    })
    bus.state(files=store.files_of(slug))


def instruct(slug: str, employee_id: str, message: str,
             owner: str = "local") -> dict:
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
        raise ValueError(lang.t("manual.empty"))

    with _Session(slug, employee_id, owner):
        _guard(employee_id, slug, owner)
        bus.say("USER", f"@{roles.display(e.id)} {message}")
        bus.phase("MANUAL", lang.t("phase.manual", who=roles.display_name(e.id)),
                  owner=e.id)
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
                info = pfs.write(f.path, f.content, employee_id,
                                 reason=message[:120])
            except pfs.Denied as ex:
                # "CEO 가 시켰다"는 권한의 근거가 아니다. 거부하고 사실을 남긴다.
                bus.say(employee_id, lang.t("log.denied", path=f.path, why=ex),
                        kind="error")
                continue
            written.append(f.path)
            # AUTO 쪽(`engine._apply`)과 **같은 문장**을 쓴다. 여기만 따로
            # 적고 있어서 MANUAL 로그에서는 번역이 빠져 있었다.
            bus.say(employee_id,
                    lang.t("log.created", path=f.path) if info["created"]
                    else lang.t("log.updated", path=f.path,
                                n=info["new_lines"]),
                    kind="tool")

        _remember(slug, employee_id, message,
                  f"{work.message_to_team}\n{work.summary}")
        _persist(slug)
        return {"employee": employee_id, "text": work.message_to_team,
                "summary": work.summary, "self_check": work.self_check,
                "files": written}


def verify(slug: str, owner: str = "local") -> dict:
    """CEO 가 누를 때만 도는 검증 (§11).

    AUTO 처럼 매 태스크마다 자동으로 돌지 않는다. 대신 **같은 검증자**가
    **같은 방식**으로 본다 — 담당자의 설명 없이 산출물 원문과 테스트
    결과만. MANUAL 이라고 검증 기준을 느슨하게 하면, 두 모드의 결과물이
    같은 이름으로 나가면서 품질만 다르게 된다.
    """
    if not store.exists(slug):
        raise KeyError(f"없는 프로젝트: {slug}")

    with _Session(slug, roles.VERIFIER, owner):
        _guard(roles.VERIFIER, slug, owner)
        bus.phase("REVIEW", lang.t("phase.review_manual"))
        report = runner.run(pfs.root())
        bus.say("SYSTEM", runner.summary_line(report), kind="tool")

        m = store.meta(slug)
        criteria = _criteria_of(m)
        task = _pseudo_task(m)
        v: Verdict = employee.ask(
            roles.VERIFIER,
            prompts.review(task, criteria, pfs.snapshot(roles.VERIFIER), report),
            Verdict)
        icon = (lang.t("verdict.pass") if v.verdict == "pass"
                    else lang.t("verdict.fail", severity=v.severity))
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
    bus.say("SYSTEM", lang.t("log.manualMode"), kind="verdict")
    return slug
