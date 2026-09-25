"""관측성 — "왜 느린가" (DAY 25).

## 이 파일이 지키려는 것

1. **호출마다 시간이 남는다.** 시작과 끝이 버스에 나가고, 사용량 집계에
   직원별 누적 시간·최대 시간·재시도·기다린 시간이 쌓인다.
2. **기다린 시간과 모델 시간이 갈린다.** 한도에 걸려 기다린 것과 모델이
   오래 생각한 것은 대응이 다르다.
3. **실패한 호출도 시간을 남긴다.** 돈은 안 나갔어도 시간은 나갔다.
4. **지표가 이벤트에서 접힌다.** 직원별 p95 · 단계별 시간 · 지금 몇
   초째 기다리는 호출 · 병렬도.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config, metrics, usage                    # noqa: E402
from app.providers import base                                  # noqa: E402
from app.providers.base import GenerateRequest, RateLimited     # noqa: E402
from app.providers.mock import Failure, MockProvider            # noqa: E402

RUN = "test-metrics"


@pytest.fixture(autouse=True)
def _bound(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    bus.bind(RUN)
    bus.reset(RUN)
    usage.bind(RUN)
    yield
    usage.drop(RUN)
    bus.reset(RUN)
    bus.release()


def _calls() -> list[dict]:
    return [e for e in bus.history(RUN) if e["type"] == "call"]


def test_each_call_emits_start_and_end_with_timings():
    p = MockProvider(name="mock:claude", model="claude-opus-5", latency=0.02)
    p.generate(GenerateRequest.ask("s", "u", agent="developer"))
    evs = _calls()
    assert [e["stage"] for e in evs] == ["start", "end"]
    end = evs[1]
    assert end["ok"] is True and end["agent"] == "developer"
    assert end["ms"] >= 20 and end["attempts"] == 1
    assert end["output"] > 0


def test_usage_accumulates_latency_per_employee():
    p = MockProvider(name="mock:claude", model="claude-opus-5", latency=0.01)
    for _ in range(3):
        p.generate(GenerateRequest.ask("s", "u", agent="writer"))
    row = usage.agents_of(RUN)["writer"]
    assert row["calls"] == 3
    assert row["latency_ms"] >= 30
    assert row["max_latency_ms"] >= 10
    assert usage.totals(RUN)["latency_ms"] == pytest.approx(row["latency_ms"])


def test_backoff_wait_is_separated_from_model_time(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(base, "_sleep", lambda s: slept.append(s))
    monkeypatch.setattr(base, "backoff_delay", lambda a, r=None: 0.0)
    p = MockProvider(name="mock:gemini", model="gemini-2.5-pro",
                     failure=Failure(error=RateLimited, times=2))
    p.generate(GenerateRequest.ask("s", "u", agent="analyst"))
    end = _calls()[-1]
    assert end["attempts"] == 3
    row = usage.agents_of(RUN)["analyst"]
    assert row["retries"] == 2
    assert len(slept) == 2


def test_failed_calls_still_record_their_time(monkeypatch):
    monkeypatch.setattr(base, "_sleep", lambda s: None)
    monkeypatch.setattr(config, "MAX_RETRY", 0)
    p = MockProvider(name="mock:openai", model="gpt-5",
                     failure=Failure(error=RateLimited, times=5))
    with pytest.raises(RateLimited):
        p.generate(GenerateRequest.ask("s", "u", agent="writer"))
    end = _calls()[-1]
    assert end["ok"] is False and end["error"] == "RateLimited"
    assert usage.agents_of(RUN)["writer"]["failures"] == 1


def test_calls_outside_a_run_do_not_pollute_the_log():
    bus.release()
    try:
        MockProvider().generate(GenerateRequest.ask("s", "u"))
    finally:
        bus.bind(RUN)
    assert not _calls()


def test_old_usage_rows_without_timing_fields_do_not_crash():
    """DAY 24 이전 메타의 사용량에는 시간 칸이 없다 — 재개하면 그 행을
    이어받는다. `+=` 에서 KeyError 가 나면 재개가 통째로 죽는다."""
    usage.seed(RUN, {"developer": {"input": 1, "output": 1, "cost": 0.1,
                                   "calls": 1}})
    usage._runs[RUN]["developer"].pop("latency_ms", None)
    MockProvider(name="mock:claude", model="claude-opus-5").generate(
        GenerateRequest.ask("s", "u", agent="developer"))
    assert usage.agents_of(RUN)["developer"]["calls"] == 2


# ── 지표 접기 ──────────────────────────────────────────────────────
def _ev(t, type, **kw):
    return {"id": int(t * 1000), "ts": t, "type": type, "run": RUN, **kw}


def test_compute_folds_agents_phases_and_parallelism():
    evs = [
        _ev(0.0, "phase", name="PLAN"),
        _ev(0.0, "call", stage="start", call_id=1, agent="strategist"),
        _ev(2.0, "call", stage="end", call_id=1, agent="strategist", ok=True,
            ms=2000.0, attempts=1, output=100),
        _ev(2.0, "phase", name="IMPLEMENT", lane="t2"),
        _ev(2.0, "phase", name="IMPLEMENT", lane="t3"),
        _ev(2.0, "call", stage="start", call_id=2, agent="writer"),
        _ev(2.0, "call", stage="start", call_id=3, agent="designer"),
        _ev(6.0, "call", stage="end", call_id=2, agent="writer", ok=True,
            ms=4000.0, attempts=2, wait_ms=500.0, output=400),
        _ev(6.0, "call", stage="end", call_id=3, agent="designer", ok=True,
            ms=4000.0, attempts=1, output=200),
        _ev(6.0, "done", ok=True),
    ]
    m = metrics.compute(evs, now=100.0)
    assert m["finished"] is True
    assert m["wall_ms"] == pytest.approx(6000)
    assert m["by_agent"]["writer"]["retries"] == 1
    assert m["by_agent"]["writer"]["wait_ms"] == 500
    assert m["by_agent"]["writer"]["tokens_per_sec"] == pytest.approx(100)
    assert m["by_phase"]["PLAN"]["ms"] == pytest.approx(2000)
    # 두 줄이 4초씩 — 한 단계 이름으로 합쳐 8초, 벽시계로는 4초.
    assert m["by_phase"]["IMPLEMENT"]["ms"] == pytest.approx(8000)
    assert m["parallelism"] == pytest.approx(10000 / 6000, rel=0.01)
    assert m["slowest"][0]["ms"] == 4000
    assert not m["inflight"]


def test_compute_reports_calls_still_waiting():
    evs = [_ev(10.0, "phase", name="REVIEW"),
           _ev(10.0, "call", stage="start", call_id=7, agent="analyst",
               model="gemini-2.5-pro")]
    m = metrics.compute(evs, now=73.0)
    assert m["finished"] is False
    assert m["inflight"] == [{"call_id": 7, "agent": "analyst",
                              "provider": None, "model": "gemini-2.5-pro",
                              "elapsed_ms": 63000.0}]


def test_human_wait_is_not_counted_as_work():
    evs = [_ev(0.0, "phase", name="PLAN"),
           _ev(1.0, "awaiting", approvals=[]),
           _ev(3601.0, "phase", name="WRITE_TESTS"),
           _ev(3602.0, "done", ok=True)]
    m = metrics.compute(evs)
    assert m["human_wait_ms"] == pytest.approx(3600_000)
    assert m["by_phase"]["PLAN"]["ms"] == pytest.approx(1000)
    assert m["by_phase"]["WRITE_TESTS"]["ms"] == pytest.approx(1000)


def test_a_resumed_run_is_not_finished_until_its_last_done():
    evs = [_ev(0.0, "phase", name="PLAN"), _ev(1.0, "done", ok=False),
           _ev(5.0, "phase", name="IMPLEMENT", lane="t1")]
    assert metrics.compute(evs, now=6.0)["finished"] is False


def test_full_mock_run_produces_metrics(tmp_path, monkeypatch):
    """엔진 전 구간을 돌리고 API 로 지표를 읽는다."""
    import time
    from fastapi.testclient import TestClient
    from app.database import store
    from app.main import app
    from app.orchestrator import engine
    from app.providers import registry
    from app.usage import credits
    bus.release()
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    credits.reset()
    registry.reset()
    slug = engine.start("계산기")
    deadline = time.time() + 90
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    assert store.meta(slug)["status"] == "done"
    body = TestClient(app).get(f"/api/runs/{slug}/metrics").json()
    assert body["finished"] is True
    assert {"strategist", "developer", "analyst", "writer", "designer"} \
        <= set(body["by_agent"])
    assert {"PLAN", "WRITE_TESTS", "IMPLEMENT", "TEST", "REVIEW",
            "FINALIZE"} <= set(body["by_phase"])
    assert store.meta(slug)["usage"]["developer"]["latency_ms"] >= 0
    registry.reset()
    bus.bind(RUN)
