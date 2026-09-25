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
          "cost": 0.0, "credits": 0.0, "calls": 0,
          # 걸린 시간 (DAY 25). 비용만으로는 "왜 느린가"가 안 보인다.
          # latency_ms 는 성공한 호출의 벽시계 합(재시도·대기 포함),
          # wait_ms 는 그중 백오프로 **기다리기만 한** 몫, failed_ms 는
          # 끝내 실패한 호출이 태운 시간이다 — 실패도 시간은 먹는다.
          "latency_ms": 0.0, "max_latency_ms": 0.0, "wait_ms": 0.0,
          "retries": 0, "failures": 0, "failed_ms": 0.0}

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
    """이 스레드의 집계 대상을 정하고 **0부터 다시 센다.** 실행 시작 시 한 번."""
    _local.run = run_id
    with _lock:
        _runs[run_id] = _blank()


def seed(run_id: str, data: dict[str, dict]) -> None:
    """저장된 값에서 다시 센다 (재개, §18).

    `bind()` 처럼 이 스레드의 집계 대상을 정하지만, 0 이 아니라 **디스크에
    남아 있던 값**에서 시작한다. 멈췄던 실행이 재개될 때, 그 사이 서버가
    재시작됐다면 메모리에는 아무것도 안 남아 있다 — `store.meta(slug)`
    에 저장해 둔 값을 여기로 명시적으로 넣어야, 재개한 뒤의 사용량이
    처음부터 다시 세지지 않고 이어진다.
    """
    _local.run = run_id
    with _lock:
        keys = set(_keys()) | set(data or {})
        merged: dict[str, dict] = {}
        for a in keys:
            row = dict(_EMPTY)
            row.update(data.get(a) or {})
            merged[a] = row
        _runs[run_id] = merged


def attach(run_id: str) -> None:
    """집계 대상만 정한다. 이미 쌓인 값은 건드리지 않는다.

    MANUAL(§11)은 한 프로젝트에 지시를 여러 번 내린다. 매번 `bind` 하면
    그때마다 그 프로젝트의 누적 사용량이 0 이 되고, 예산 상한(§18)이
    영영 걸리지 않는다 — 버튼을 스무 번 누르는 것으로 상한을 우회할 수 있다.
    """
    _local.run = run_id
    with _lock:
        _runs.setdefault(run_id, _blank())


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


def _row(rid: str, agent: str) -> dict:
    """집계 칸. 디스크에서 올라온 옛 칸(DAY 25 이전)에는 시간 칸이 없다 —
    없는 칸은 0 으로 채운다. 안 채우면 `+=` 에서 KeyError 로 실행이 죽는다."""
    row = _runs.setdefault(rid, _blank()).setdefault(agent, dict(_EMPTY))
    for k, v in _EMPTY.items():
        row.setdefault(k, v)
    return row


def record(agent: str, model: str, input_tokens: int, output_tokens: int,
           cached_tokens: int = 0, cache_written: int = 0, *,
           latency_ms: float = 0.0, wait_ms: float = 0.0,
           retries: int = 0) -> None:
    rid = current()
    if rid is None:
        return                      # 실행 밖의 호출은 집계하지 않는다
    with _lock:
        row = _row(rid, agent)
        row["latency_ms"] += latency_ms
        row["max_latency_ms"] = max(row["max_latency_ms"], latency_ms)
        row["wait_ms"] += wait_ms
        row["retries"] += retries
        row["input"] += input_tokens
        row["output"] += output_tokens
        row["cached"] += cached_tokens
        row["cache_written"] += cache_written
        # 캐시는 입력 단가의 배수로 따로 계산한다(§14). DAY 11 전에는 캐시
        # 토큰을 보통 입력처럼 더했는데, 그러면 원가를 실제보다 크게 잡고
        # §17 마진 판단이 틀어진다 — 안전한 쪽으로 틀린 숫자도 틀린 숫자다.
        cost = config.price_of(model, input_tokens, output_tokens,
                               cached_tokens, cache_written)
        row["cost"] += cost
        row["credits"] += cost / config.CREDIT_USD if config.CREDIT_USD else 0.0
        row["calls"] += 1
    push()


def record_failure(agent: str, ms: float) -> None:
    """끝내 실패한 호출. 돈은 안 나갔어도(대개) **시간은** 나갔다."""
    rid = current()
    if rid is None:
        return
    with _lock:
        row = _row(rid, agent)
        row["failures"] += 1
        row["failed_ms"] += ms
    push()


def totals(run_id: str | None = None) -> dict:
    rows = agents_of(run_id).values()
    return {
        "input": sum(r["input"] for r in rows),
        "output": sum(r["output"] for r in rows),
        "cached": sum(r["cached"] for r in rows),
        "cost": sum(r["cost"] for r in rows),
        "credits": sum(r.get("credits", 0.0) for r in rows),
        "calls": sum(r["calls"] for r in rows),
        "latency_ms": sum(r.get("latency_ms", 0.0) for r in rows),
        "wait_ms": sum(r.get("wait_ms", 0.0) for r in rows),
        "retries": sum(r.get("retries", 0) for r in rows),
        "failures": sum(r.get("failures", 0) for r in rows),
    }


def total_cost(run_id: str | None = None) -> float:
    return totals(run_id)["cost"]


def total_credits(run_id: str | None = None) -> float:
    """이 실행이 먹은 크레딧 (§15). 원가를 크레딧 단가로 나눈 값이다."""
    return totals(run_id)["credits"]


def cache_working(run_id: str | None = None) -> bool | None:
    """None = 아직 판단 불가, False = 캐시가 안 걸리고 있음."""
    t = totals(run_id)
    if t["calls"] < 2:
        return None
    return t["cached"] > 0


def drop(run_id: str) -> None:
    with _lock:
        _runs.pop(run_id, None)


def drop_all() -> None:
    """집계를 통째로 비운다.

    테스트용이다. 집계는 **slug 문자열**을 전역 키로 쓰므로, 같은 이름의
    프로젝트가 서로 다른 폴더에서 만들어지면(테스트가 매번 임시 폴더를
    쓰는 경우) 두 프로젝트의 비용이 한 통에 섞인다. 그러면 예산 상한이
    엉뚱한 곳에서 걸린다.
    """
    with _lock:
        _runs.clear()


def push() -> None:
    rid = current()
    if rid is None:
        return
    bus.state(usage=agents_of(rid), totals=totals(rid), cache_ok=cache_working(rid))
