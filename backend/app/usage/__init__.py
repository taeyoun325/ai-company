"""에이전트별 토큰·비용 집계 — 실행(프로젝트)별로 따로 센다.

Claude와 Gemini가 각각 다른 SDK를 쓰므로, 사용량을 여기 한 곳으로 모은다.

**실행별로 나누는 이유**: 여러 프로젝트를 동시에 돌리면 전역 집계는
누가 얼마를 썼는지 알 수 없게 되고, 예산 상한도 엉뚱하게 걸린다.
실행 하나가 스레드 하나이므로 스레드 로컬로 현재 실행을 찾는다.

캐시 적중을 따로 세는 이유: cache_control을 붙였다는 사실과 캐시가 실제로
걸렸다는 사실은 다르다. 최소 프리픽스 길이 미만이면 조용히 무시되므로,
읽힌 캐시 토큰이 0이면 "캐싱으로 절감했다"는 말은 근거가 없다.
"""
import threading

from app import bus
from app import config

_lock = threading.RLock()
_local = threading.local()

_EMPTY = {"input": 0, "output": 0, "cached": 0, "cache_written": 0,
          "cost": 0.0, "calls": 0}

# run_id(프로젝트 slug) -> {에이전트 -> 사용량}
_runs: dict[str, dict[str, dict]] = {}


def _keys() -> tuple[str, ...]:
    """집계 칸을 미리 만들어 둘 대상.

    DAY 1~3 에는 여기가 `("PM", "DEV", "QA")` 로 **하드코딩**되어 있었다.
    직원이 5명이 되면서 그대로 두면 직원별 사용량이 세 칸에 섞여버린다.
    이제 직원 표(§8)를 읽는다 — 직원을 늘려도 여기를 고칠 일이 없다.

    import 를 함수 안에서 하는 이유: `agents.roles` 가 `config` 를 읽고
    `usage` 는 `config` 보다 먼저 올라올 수 있다. 순환을 만들지 않는다.
    """
    try:
        from app.agents import roles
        return (*roles.ids(), "SYSTEM")
    except Exception:                       # noqa: BLE001 — 집계가 기동을 막으면 안 된다
        return ("SYSTEM",)


def _blank() -> dict[str, dict]:
    return {a: dict(_EMPTY) for a in _keys()}


def bind(run_id: str) -> None:
    """이 스레드의 집계 대상을 정한다. 실행 시작 시 한 번."""
    _local.run = run_id
    with _lock:
        _runs[run_id] = _blank()


def current() -> str | None:
    return getattr(_local, "run", None)


def reset(run_id: str | None = None) -> None:
    rid = run_id or current()
    if rid is None:
        return
    with _lock:
        _runs[rid] = _blank()


def agents_of(run_id: str | None = None) -> dict[str, dict]:
    rid = run_id or current()
    with _lock:
        return {a: dict(r) for a, r in _runs.get(rid, _blank()).items()}


def record(agent: str, model: str, input_tokens: int, output_tokens: int,
           cached_tokens: int = 0, cache_written: int = 0) -> None:
    rid = current()
    if rid is None:
        return                      # 실행 밖의 호출은 집계하지 않는다
    with _lock:
        row = _runs.setdefault(rid, _blank()).setdefault(agent, dict(_EMPTY))
        row["input"] += input_tokens
        row["output"] += output_tokens
        row["cached"] += cached_tokens
        row["cache_written"] += cache_written
        # 캐시 읽기도 입력 토큰으로 과금된다(단가는 더 저렴하나 보수적으로 합산)
        row["cost"] += config.price_of(model, input_tokens + cached_tokens, output_tokens)
        row["calls"] += 1
    push()


def totals(run_id: str | None = None) -> dict:
    rows = agents_of(run_id).values()
    return {
        "input": sum(r["input"] for r in rows),
        "output": sum(r["output"] for r in rows),
        "cached": sum(r["cached"] for r in rows),
        "cost": sum(r["cost"] for r in rows),
        "calls": sum(r["calls"] for r in rows),
    }


def total_cost(run_id: str | None = None) -> float:
    return totals(run_id)["cost"]


def cache_working(run_id: str | None = None) -> bool | None:
    """None = 아직 판단 불가, False = 캐시가 안 걸리고 있음."""
    t = totals(run_id)
    if t["calls"] < 2:
        return None
    return t["cached"] > 0


def drop(run_id: str) -> None:
    with _lock:
        _runs.pop(run_id, None)


def push() -> None:
    rid = current()
    if rid is None:
        return
    bus.state(usage=agents_of(rid), totals=totals(rid), cache_ok=cache_working(rid))
