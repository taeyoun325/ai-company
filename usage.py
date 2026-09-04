"""에이전트별 토큰·비용 집계.

Claude와 Gemini가 각각 다른 SDK를 쓰므로, 사용량을 여기 한 곳으로 모은다.
캐시 적중을 따로 세는 이유: cache_control을 붙였다는 사실과 캐시가 실제로
걸렸다는 사실은 다르다. 최소 프리픽스 길이 미만이면 조용히 무시되므로,
읽힌 캐시 토큰이 0이면 "캐싱으로 절감했다"는 말은 근거가 없다.
"""
import threading

import bus
import config

_lock = threading.Lock()

_EMPTY = {"input": 0, "output": 0, "cached": 0, "cache_written": 0,
          "cost": 0.0, "calls": 0}
agents: dict[str, dict] = {}


def reset() -> None:
    with _lock:
        agents.clear()
        for a in ("PM", "DEV", "QA"):
            agents[a] = dict(_EMPTY)


def record(agent: str, model: str, input_tokens: int, output_tokens: int,
           cached_tokens: int = 0, cache_written: int = 0) -> None:
    with _lock:
        row = agents.setdefault(agent, dict(_EMPTY))
        row["input"] += input_tokens
        row["output"] += output_tokens
        row["cached"] += cached_tokens
        row["cache_written"] += cache_written
        # 캐시 읽기도 입력 토큰으로 과금된다(단가는 더 저렴하나 여기선 보수적으로 합산)
        row["cost"] += config.price_of(model, input_tokens + cached_tokens, output_tokens)
        row["calls"] += 1
    push()


def totals() -> dict:
    with _lock:
        return {
            "input": sum(r["input"] for r in agents.values()),
            "output": sum(r["output"] for r in agents.values()),
            "cached": sum(r["cached"] for r in agents.values()),
            "cost": sum(r["cost"] for r in agents.values()),
            "calls": sum(r["calls"] for r in agents.values()),
        }


def total_cost() -> float:
    return totals()["cost"]


def cache_working() -> bool | None:
    """None = 아직 판단 불가, False = 캐시가 안 걸리고 있음."""
    t = totals()
    if t["calls"] < 2:
        return None
    return t["cached"] > 0


def push() -> None:
    with _lock:
        snap = {a: dict(r) for a, r in agents.items()}
    bus.state(usage=snap, totals=totals(), cache_ok=cache_working())
