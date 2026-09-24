"""작업 로그를 평범한 말로 옮긴다 (DAY 23 · §13 의 연장).

## 왜 있는가

작업 로그는 기술 어휘로 쌓인다 — `PLAN`·`WRITE_TESTS` 같은 단계 이름,
직원 id, 도구 호출 문장. 개발자가 아닌 CEO 가 그걸 읽고 "지금 뭐가 되고
있는지"를 바로 알기는 어렵다. 이 모듈은 같은 사실을 모델에게 한 번 풀어
쓰게 한다 — 로그를 지우거나 대신하지 않는다, 옆에 문단 하나를 더할 뿐이다.

## 왜 버튼을 눌러야 나오나 (자동으로 돌지 않는다)

이 호출도 돈이 든다(§14). 이벤트마다 자동으로 돌리면 아무도 보지 않는
요약에 비용이 계속 나간다. 검증(§11)과 같은 규칙 — **CEO 가 누를 때만**
돈다.

## 왜 strategist 를 빌려 쓰나

새 직원을 하나 더 정의하면 권한 표(§8)에 자리가 하나 늘고, 화면의
사무실에 여섯 번째 자리가 필요한지부터 다시 물어야 한다. strategist 는
이미 "파일을 쓰지 않고 글로만 답하는" 직원이고, 그 성질이 그대로 맞는다.

## 비용은 프로젝트 것으로 잡힌다

MANUAL 지시(`orchestrator/manual.py`)와 같은 규칙이다 — 예산 상한을
호출 *전에* 검사하고, 실제로 늘어난 만큼만 지갑에서 깎고, 프로젝트
누적 비용에도 더한다. 이 호출만 계산에서 빠지면 "AUTO 는 돈이 들고 이
버튼은 공짜"가 되고, 그건 MANUAL 이 DAY 18 까지 갖고 있던 구멍과 같다.
"""
from __future__ import annotations

from app import bus, config, lang, tenant, usage
from app.agents import employee
from app.database import store
from app.usage import credits

NARRATOR = "strategist"          # 파일을 쓰지 않는 직원을 빌려 쓴다.

MAX_LOG_LINES = 12                # 프롬프트에 실을 최근 줄 수

# 프로젝트 메타(파일) 안에 캐시를 둔다. 프로세스 메모리에 두면 이 요청을
# 받은 인스턴스와 지난번 요청을 받은 인스턴스가 다를 때 캐시를 못 찾고
# **다시 부르고 다시 청구한다** — 오늘 고친 SSE·MANUAL 점유와 같은 종류의
# 버그를 새로 심는 셈이다(§13 DAY 23). 프로젝트 메타는 이미 파일이 진실인
# 자리이므로(§12) 여기 얹으면 그 문제가 생기지 않는다.
META_KEY = "narration"


class NoProgress(RuntimeError):
    """아직 설명할 만한 일이 없다."""


def _recent_lines(slug: str) -> tuple[list[dict], int]:
    """이 프로젝트의 최근 로그. 인스턴스를 안 가린다(§13 DAY 23).

    실행을 시작한 인스턴스와 이 요청을 받은 인스턴스가 다를 수 있다 —
    트레이스 파일을 읽으면 어느 쪽이든 같은 로그가 나온다.

    `last_id` 는 **말·단계·종료 이벤트만** 보고 정한다. 청구가 끝나면
    `bus.state(credits=...)` 가 지갑 갱신을 SSE 로 알리려고 같은 트레이스에
    이벤트를 하나 더 남기는데, 그걸 기준으로 삼으면 **narrate 가 자기
    호출로 자기 캐시를 무효화한다** — 실제로는 아무 일도 더 안 일어났는데
    "새 일이 생겼다"로 보인다.
    """
    events = bus.read_trace(slug, 0)
    rows = [e for e in events
            if e.get("type") in ("message", "phase", "done")]
    last_id = rows[-1]["id"] if rows else 0
    return rows[-MAX_LOG_LINES:], last_id


def _prompt(requirement: str, rows: list[dict]) -> str:
    lines = []
    for e in rows:
        if e["type"] == "phase":
            lines.append(f"[단계] {e.get('name')}"
                         + (f" · {e['detail']}" if e.get("detail") else ""))
        elif e["type"] == "done":
            lines.append(f"[종료] ok={e.get('ok')} score={e.get('score')} "
                         f"{e.get('summary', '')}")
        else:
            lines.append(f"[{e.get('agent')}/{e.get('kind', 'say')}] "
                         f"{str(e.get('text', ''))[:400]}")
    log = "\n".join(lines) or "(아직 로그 없음)"
    return (
        f"# 요구사항\n{requirement}\n\n"
        f"# 최근 작업 로그\n{log}\n\n"
        "# 할 일\n"
        "위 로그를 바탕으로, 개발을 모르는 대표(CEO)에게 **지금 무슨 일이\n"
        "일어나고 있는지** 2~3문장으로 설명하세요. 규칙:\n"
        "- 직원 id·단계 이름(PLAN 등)·도구 이름 같은 내부 용어를 그대로\n"
        "  쓰지 말고 풀어 쓰세요('전략가가 요구사항을 정리하고 있습니다'처럼).\n"
        "- 지어내지 마세요. 로그에 없는 진행 상황은 말하지 마세요.\n"
        "- 문장만 내보내세요. 제목·불릿·따옴표 없이.\n"
    )


def _guard(owner: str, slug: str) -> None:
    limit = min(config.MAX_PROJECT_COST,
                float(credits.plan(credits.wallet(owner).plan)
                      .get("max_project_cost", config.MAX_PROJECT_COST)))
    projected = usage.total_cost(slug) + employee.worst_case_cost(NARRATOR)
    if projected > limit:
        raise RuntimeError(
            lang.t("manual.cost", limit=limit, projected=f"{projected:.2f}"))


def narrate(slug: str, owner: str = "local", *, force: bool = False) -> dict:
    """이 프로젝트를 평범한 말로 설명한다. 이미 설명한 것이면 다시 부르지 않는다.

    `force` 는 화면의 "다시 설명" 버튼이다 — 캐시를 무시하고 다시 한 번
    부른다(비용이 또 나간다는 뜻이므로 사용자가 직접 눌러야 한다).
    """
    if not store.exists(slug):
        raise KeyError(f"없는 프로젝트: {slug}")

    rows, last_id = _recent_lines(slug)
    m = store.meta(slug)
    cached = m.get(META_KEY)
    if not force and cached and cached.get("last_id") == last_id:
        return {"text": cached["text"], "cached": True}
    if not rows:
        raise NoProgress(lang.t("narrate.empty"))

    tenant.require_runnable(owner)
    _guard(owner, slug)
    credits.reserve(owner, employee.worst_case_cost(NARRATOR))

    requirement = m.get("requirement", "")

    with tenant.bind(owner):
        bus.bind(slug)
        usage.attach(slug)
        before = usage.total_cost(slug)
        try:
            text = employee.ask_text(NARRATOR, _prompt(requirement, rows)).strip()
        finally:
            spent = max(0.0, usage.total_cost(slug) - before)
            patch: dict = {}
            if spent:
                left = credits.charge(owner, spent)
                bus.state(credits=left, credits_used=credits.usd_to_credits(spent))
                patch["usage"] = usage.agents_of(slug)
                patch["cost"] = round(usage.total_cost(slug), 4)

    patch[META_KEY] = {"text": text, "last_id": last_id}
    store.save_meta(slug, patch)
    return {"text": text, "cached": False}
