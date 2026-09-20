"""실시간 작업 로그 · SSE (지시서 §13).

## 이 파일이 지키려는 것

1. **여러 프로젝트가 한 화면에서 섞이지 않는다.** run 없이 구독하면 전부,
   주면 그것만.
2. **끊겨도 잃지 않는다.** SSE 는 끊긴다 — 프록시가 끊고, 노트북이 잠들고,
   탭이 백그라운드로 간다. 재연결 때 못 받은 것부터 이어받아야 한다.
3. **느린 화면 하나가 서버를 죽이지 않는다.** 안 읽어가는 구독자의 큐가
   무한히 자라면 메모리를 먹는다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from fastapi.testclient import TestClient                       # noqa: E402

from app import bus, config                                     # noqa: E402
from app import main                                            # noqa: E402


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    bus.release()
    yield
    bus.close_all_traces()
    for run in ("run-a", "run-b", None):
        bus.reset(run)
    bus.release()


def _emit(run: str, text: str) -> dict:
    bus.bind(run)
    bus.say("SYSTEM", text)
    return bus.history(run)[-1]


# ── 실행별 분리 ────────────────────────────────────────────────────
def test_events_are_tagged_with_their_run():
    ev = _emit("run-a", "안녕")
    assert ev["run"] == "run-a"


def test_subscriber_scoped_to_one_run_ignores_others():
    sub = bus.subscribe("run-a")
    try:
        _emit("run-a", "내 것")
        _emit("run-b", "남의 것")
        got = [sub.q.get_nowait()["text"] for _ in range(sub.q.qsize())]
        assert got == ["내 것"]
    finally:
        bus.unsubscribe(sub)


def test_global_subscriber_sees_everything():
    """대시보드(§12)는 여러 프로젝트를 한 화면에서 본다."""
    sub = bus.subscribe()
    try:
        # 구독 즉시 오는 것은 다른 테스트가 남긴 과거 이력이다. 비우고 본다.
        while not sub.q.empty():
            sub.q.get_nowait()
        _emit("run-a", "A")
        _emit("run-b", "B")
        got = [sub.q.get_nowait()["text"] for _ in range(sub.q.qsize())]
        assert got == ["A", "B"]
    finally:
        bus.unsubscribe(sub)


def test_history_of_one_run_is_not_evicted_by_another():
    """한 덱에 전부 쌓으면 바쁜 실행이 조용한 실행의 이력을 밀어낸다."""
    _emit("run-a", "소중한 기록")
    for i in range(bus.HISTORY_LIMIT + 10):
        _emit("run-b", str(i))
    assert [e["text"] for e in bus.history("run-a")] == ["소중한 기록"]


# ── 재연결 ─────────────────────────────────────────────────────────
def test_ids_increase_monotonically():
    a = _emit("run-a", "1")
    b = _emit("run-a", "2")
    assert b["id"] > a["id"]


def test_replay_after_id_skips_what_was_already_seen():
    a = _emit("run-a", "1")
    _emit("run-a", "2")
    assert [e["text"] for e in bus.replay("run-a", after=a["id"])] == ["2"]


def test_late_subscriber_gets_the_backlog():
    """늦게 접속한 화면도 처음부터 볼 수 있어야 한다."""
    _emit("run-a", "이미 지나간 일")
    sub = bus.subscribe("run-a")
    try:
        assert sub.q.get_nowait()["text"] == "이미 지나간 일"
    finally:
        bus.unsubscribe(sub)


def test_reconnecting_subscriber_does_not_see_duplicates():
    a = _emit("run-a", "1")
    _emit("run-a", "2")
    sub = bus.subscribe("run-a", after=a["id"])
    try:
        got = [sub.q.get_nowait()["text"] for _ in range(sub.q.qsize())]
        assert got == ["2"], "재연결 때 본 것을 또 보내면 로그가 두 번 찍힌다"
    finally:
        bus.unsubscribe(sub)


# ── 느린 구독자 ────────────────────────────────────────────────────
def test_slow_subscriber_is_capped_not_unbounded(monkeypatch):
    """브라우저 탭 하나가 멈춰서 안 읽어가면 그 큐만 무한히 자란다.
    전체를 멈추는 것보다 한 화면이 일부를 놓치는 편이 낫다."""
    monkeypatch.setattr(bus, "SUBSCRIBER_LIMIT", 5)
    sub = bus.subscribe("run-a")
    try:
        for i in range(20):
            _emit("run-a", str(i))
        assert sub.q.qsize() <= bus.SUBSCRIBER_LIMIT
        assert sub.dropped > 0, "버렸다는 사실이 기록되지 않으면 아무도 모른다"
    finally:
        bus.unsubscribe(sub)


def test_unsubscribe_removes_the_subscriber():
    before = bus.subscriber_count()
    sub = bus.subscribe()
    assert bus.subscriber_count() == before + 1
    bus.unsubscribe(sub)
    assert bus.subscriber_count() == before


# ── 트레이스 ───────────────────────────────────────────────────────
def test_trace_is_written_per_run():
    """한 파일에 전부 쌓으면 '이 프로젝트에서 무슨 일이 있었나'를 보려고
    수십만 줄을 훑어야 하고, 동시 실행이 서로의 줄 사이에 끼어든다."""
    _emit("run-a", "A")
    _emit("run-b", "B")
    bus.close_all_traces()
    assert (config.LOGS / "run-a.jsonl").read_text(encoding="utf-8").count("A") == 1
    assert "A" not in (config.LOGS / "run-b.jsonl").read_text(encoding="utf-8")


def test_trace_failure_does_not_stop_the_run(monkeypatch):
    """트레이스는 증거물이지 실행의 전제가 아니다."""
    monkeypatch.setattr(config, "LOGS", Path("/존재하지않는/경로"))
    bus.close_all_traces()
    _emit("run-a", "그래도 진행")          # 예외가 나면 여기서 터진다
    assert bus.history("run-a")[-1]["text"] == "그래도 진행"


# ── HTTP 표면 ──────────────────────────────────────────────────────
def test_events_endpoint_mirrors_the_stream():
    """SSE 하나에만 기대면, 그 경로가 막힌 환경에서 화면이 통째로 빈다."""
    _emit("run-a", "안녕")
    body = TestClient(main.app).get("/api/events", params={"run": "run-a"}).json()
    assert [e["text"] for e in body["events"]] == ["안녕"]
    assert body["last_id"] == body["events"][-1]["id"]


def test_events_endpoint_supports_after():
    a = _emit("run-a", "1")
    _emit("run-a", "2")
    body = TestClient(main.app).get(
        "/api/events", params={"run": "run-a", "after": a["id"]}).json()
    assert [e["text"] for e in body["events"]] == ["2"]


def test_roster_names_every_employee():
    """말풍선에 id 가 그대로 뜨면 CEO 는 누가 말한 건지 모른다."""
    from app.agents import roles
    r = bus.roster()
    for e in roles.EMPLOYEES.values():
        assert e.id in r and e.name in r[e.id]["name"]


def test_reserved_event_fields_are_refused():
    """실제로 approvals 가 `id` 로 승인 번호를 실었고, 그게 이벤트
    일련번호를 덮어써서 재연결 이어받기가 깨졌다. 조용한 덮어쓰기는
    증상이 엉뚱한 곳에서 나온다."""
    for field in bus.RESERVED:
        # `type` 은 emit 의 위치 인자라서 파이썬이 먼저 TypeError 로 막는다.
        # 어느 쪽이든 조용히 통과하지 않는다는 것이 요점이다.
        with pytest.raises((ValueError, TypeError)):
            bus.emit("아무거나", **{field: "충돌"})


def test_approval_events_do_not_clash():
    from app import approvals
    bus.bind("run-a")
    approvals.decide("없는승인", "approve")     # 없는 id 여도 이벤트 경로는 탄다
    assert all(isinstance(e["id"], int) for e in bus.history("run-a"))
