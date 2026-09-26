"""Cloud Run 감독자의 임대 (DAY 27) — 쓰는 인스턴스는 언제나 하나.

Cloud Storage 대신 세대 번호를 흉내 낸 메모리 저장소로 시나리오를 돌린다.
조건부 쓰기(ifGenerationMatch)의 의미만 맞으면 된다.
"""
import importlib.util
import threading
import time
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "deploy" / "cloudrun" / "supervisor.py"


class FakeGCS:
    def __init__(self):
        self.doc, self.gen, self.lock = None, 0, threading.Lock()

    def read(self):
        with self.lock:
            return (dict(self.doc) if self.doc else None), self.gen

    def write(self, doc, if_gen):
        with self.lock:
            if if_gen != self.gen:
                return None
            self.gen += 1
            self.doc = dict(doc)
            return self.gen


class Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


def load(gcs, clock, me, revision, monkeypatch):
    spec = importlib.util.spec_from_file_location(f"sup_{me}", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "read", gcs.read)
    monkeypatch.setattr(m, "write", gcs.write)
    monkeypatch.setattr(m, "time", clock)
    m.ME, m.REVISION = me, revision
    m.log = lambda *_: None
    return m


@pytest.fixture
def world(monkeypatch):
    gcs, clock = FakeGCS(), Clock()
    return gcs, clock, lambda me, rev: load(gcs, clock, me, rev, monkeypatch)


def test_first_instance_takes_an_empty_lease(world):
    gcs, _clock, new = world
    a = new("a", "ai-company-00001-aaa")
    a.acquire()
    assert gcs.doc["holder"] == "a" and gcs.doc["state"] == "held"


def test_new_revision_asks_the_old_one_to_hand_over(world):
    """배포: 새 리비전이 뜨면 옛 주인에게 넘겨 달라고 적는다."""
    gcs, clock, new = world
    old = new("old", "ai-company-00001-aaa")
    old.acquire()
    b = new("b", "ai-company-00002-bbb")
    kind, state = b._acquire_step(clock.t, -1, clock.t, False)
    assert kind == "wait" and state[2] is True
    assert gcs.doc["state"] == "handoff" and gcs.doc["holder"] == "old"
    # 옛 주인의 다음 박동은 실패하고, 읽어 보면 handoff 다 → 내려놓는다
    assert old.write(old._doc("held"), gcs.gen - 1) is None
    doc, cur = gcs.read()
    assert doc["holder"] == "old" and doc["state"] == "handoff"
    old.write(old._doc("released"), cur)
    kind, gen = b._acquire_step(clock.t, *state)
    assert kind == "got" and gcs.doc["holder"] == "b"


def test_same_revision_duplicate_never_evicts_a_healthy_owner(world):
    """잠깐 한도를 넘어 뜬 복제본이 멀쩡한 주인을 끌어내리면 실행이 끊긴다."""
    gcs, clock, new = world
    a = new("a", "ai-company-00001-aaa")
    gen = a.acquire()
    dup = new("dup", "ai-company-00001-aaa")
    started, seen = clock.t, (-1, clock.t, False)
    with pytest.raises(SystemExit) as e:
        while True:
            # 주인은 계속 박동한다
            gen = a.write(a._doc("held"), gen)
            kind, val = dup._acquire_step(started, *seen)
            assert kind == "wait"
            seen = val
    assert e.value.code == 3
    assert gcs.doc["holder"] == "a" and gcs.doc["state"] == "held"


def test_a_dead_owner_is_replaced_after_it_goes_stale(world):
    """주인이 박동을 멈추면(죽음) STALE 뒤에 넘어간다. 시계는 **내 것**으로 잰다."""
    gcs, clock, new = world
    a = new("a", "ai-company-00001-aaa")
    a.acquire()
    b = new("b", "ai-company-00001-aaa")
    b.acquire()                      # 같은 리비전 — 주인이 멈춰 있으니 STALE 뒤 받는다
    assert gcs.doc["holder"] == "b"
    assert clock.t - 1000.0 >= b.STALE


def test_owner_stops_itself_before_anyone_may_take_over():
    """스스로 멈추는 시한이 남이 가져가는 시한보다 짧아야 겹치지 않는다."""
    spec = importlib.util.spec_from_file_location("sup_consts", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.SELF_FENCE + m.HEARTBEAT <= m.STALE


def test_old_revision_never_takes_the_lease_back(world):
    """넘겨준 옛 리비전을 Cloud Run 이 다시 띄워도 새 주인에게 넘겨 달라고
    하지 않는다 — DAY 27 실측에서 1분 동안 여섯 번 주인이 바뀐 핑퐁."""
    gcs, clock, new = world
    newer = new("new", "ai-company-00006-sp6")
    newer.acquire()
    old = new("old-again", "ai-company-00005-vnr")
    started, seen = clock.t, (-1, clock.t, False)
    with pytest.raises(SystemExit):
        while True:
            kind, seen = old._acquire_step(started, *seen)
            assert kind == "wait"
            assert gcs.doc["state"] == "held" and gcs.doc["holder"] == "new"


def test_old_revision_ignores_a_released_lease_of_a_newer_one(world):
    """새 리비전이 유휴로 내려가며 놓은 임대를 옛 리비전이 줍지 않는다."""
    gcs, clock, new = world
    newer = new("new", "ai-company-00006-sp6")
    g = newer.acquire()
    newer.write(newer._doc("released"), g)
    old = new("old", "ai-company-00005-vnr")
    kind, _ = old._acquire_step(clock.t, -1, clock.t, False)
    assert kind == "wait" and gcs.doc["holder"] == "new"
    again = new("new-2", "ai-company-00006-sp6")
    assert again._acquire_step(clock.t, -1, clock.t, False)[0] == "got"


def test_revision_numbers_are_read_from_cloud_run_names():
    spec = importlib.util.spec_from_file_location("sup_rev", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.rev_num("ai-company-00012-x7z") == 12
    assert m.rev_num("local") == 0 and m.rev_num(None) == 0


class FakeProcs:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name in ("restore", "replicate", "go", "wait_ready", "stop_all", "stop_writers"):
            return lambda *a, **k: self.calls.append(name)
        raise AttributeError(name)

    def dead(self):
        return None


class FakeFront:
    def __init__(self):
        self.modes = []

    def open(self):
        self.modes.append("open")

    def set(self, mode):
        self.modes.append(mode)


def _hold_until(m, gen, stop, clock, after, event=None):
    """가짜 시계로 serve() 를 돌린다. `after` 초 뒤 event() → 그 뒤 SIGTERM."""
    procs, front = FakeProcs(), FakeFront()
    t0, fired = clock.t, {"done": False}
    real_sleep = clock.sleep

    def sleep(s):
        real_sleep(s)
        if event and not fired["done"] and clock.t - t0 >= after:
            fired["done"] = True
            event()
        if clock.t - t0 >= after * 3:
            stop["sig"] = True
    clock.sleep = sleep
    try:
        rc = m.serve(gen, stop, procs, front)
    finally:
        clock.sleep = real_sleep
    _hold_until.last = (procs, front)
    return rc


def test_owner_refuses_a_handoff_request_from_an_older_revision(world):
    """옛 코드의 옛 리비전이 요청해 온 것을 받아 줬다가 40초 동안 아무도
    서비스하지 않았다(DAY 27). 쥐는 쪽도 규칙을 지킨다."""
    gcs, clock, new = world
    owner = new("owner", "ai-company-00007-gxp")
    gen = owner.acquire()

    def old_asks():
        doc, g = gcs.read()
        gcs.write({**doc, "state": "handoff", "by": "old", "by_revision": "ai-company-00006-sp6"}, g)

    rc = _hold_until(owner, gen, {"sig": False}, clock, 25, old_asks)
    assert rc == 0                                   # SIGTERM 으로 끝났지 넘겨주지 않았다
    assert gcs.doc["holder"] == "owner" and gcs.doc["state"] == "released"


def test_owner_hands_over_to_a_newer_revision(world):
    gcs, clock, new = world
    owner = new("owner", "ai-company-00007-gxp")
    gen = owner.acquire()

    def newer_asks():
        doc, g = gcs.read()
        gcs.write({**doc, "state": "handoff", "by": "n", "by_revision": "ai-company-00008-mlw"}, g)

    assert _hold_until(owner, gen, {"sig": False}, clock, 25, newer_asks) == "handoff"
    assert gcs.doc["state"] == "released"
    procs, front = _hold_until.last
    # 앞문을 먼저 닫고(대기) → 쓰는 쪽을 멈춘 뒤 → 놓는다. 순서가 바뀌면
    # 새 주인이 받기 전에 옛 앱이 한 번 더 쓴다.
    assert front.modes[-1] == "standby" and procs.calls[-1] == "stop_writers"


def test_standby_takes_the_lease_back_when_it_is_its_turn(world):
    """주인이 없어졌는데 대기 인스턴스가 영영 대기만 하면 그동안 아무도
    서비스하지 않는다(DAY 27 실측 40초)."""
    gcs, clock, new = world
    stand = new("stand", "ai-company-00007-gxp")
    other = new("other", "ai-company-00007-gxp")
    g = other.acquire()
    other.write(other._doc("released"), g)
    assert stand.acquire({"sig": False}, give_up=False) is not None
    assert gcs.doc["holder"] == "stand"


# ── 앞문: 인계 동안 요청을 실패시키지 않고 붙잡는다 ─────────────────
import http.client                                             # noqa: E402
import http.server                                             # noqa: E402
import socket                                                  # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def front(monkeypatch):
    spec = importlib.util.spec_from_file_location("sup_front", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.log = lambda *_: None
    up_port, front_port = _free_port(), _free_port()

    class Up(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"upstream {self.path}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass
    up = http.server.ThreadingHTTPServer(("127.0.0.1", up_port), Up)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    monkeypatch.setattr(m, "PORT", front_port)
    monkeypatch.setattr(m, "NEXT_PORT", up_port)
    f = m.Front()
    yield m, f, front_port
    up.shutdown()


def _get(port, path, timeout=10):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.request("GET", path)
    r = c.getresponse()
    return r.status, r.read().decode()


def test_held_requests_succeed_once_ready(front):
    """실패가 아니라 지연이어야 한다 — 인계 동안 온 요청."""
    m, f, port = front
    f.open()                                   # hold
    out = {}
    t = threading.Thread(target=lambda: out.update(r=_get(port, "/api/x")))
    t.start()
    time.sleep(0.5)
    assert t.is_alive(), "준비 전인데 답이 나갔다"
    f.set("ready")
    t.join(5)
    assert out["r"] == (200, "upstream /api/x")


def test_standby_answers_liveness_only(front):
    m, f, port = front
    f.mode = "standby"
    f.open()
    assert _get(port, "/api/deploy")[0] == 200
    assert _get(port, "/api/projects")[0] == 503


def test_hold_gives_up_before_the_hosting_timeout(front, monkeypatch):
    m, f, port = front
    monkeypatch.setattr(m, "HOLD_MAX", 0.3)
    f.open()
    assert _get(port, "/api/projects")[0] == 503


def test_old_standby_does_not_retake_a_lease_released_for_the_newer_one(world):
    """넘겨준 쪽이 대기 모드에서 방금 놓은 자기 임대를 다시 집어 갔다 —
    새 인스턴스가 옛 인스턴스가 끝날 때까지 5초를 더 기다렸다(DAY 27 실측)."""
    gcs, clock, new = world
    old = new("old", "ai-company-00010-xsr")
    g = old.acquire()
    old.write(old._doc("released", for_revision="ai-company-00011-h8b", **{"for": "n"}), g)
    kind, _ = old._acquire_step(None, -1, clock.t, False)
    assert kind == "wait" and gcs.doc["state"] == "released", "옛 주인이 다시 집어 갔다"
    newer = new("n", "ai-company-00011-h8b")
    assert newer._acquire_step(clock.t, -1, clock.t, True)[0] == "got"


def test_a_reservation_expires_if_the_newer_one_never_comes(world):
    gcs, clock, new = world
    old = new("old", "ai-company-00010-xsr")
    g = old.acquire()
    old.write(old._doc("released", for_revision="ai-company-00011-h8b"), g)
    assert old.acquire({"sig": False}, give_up=False) is not None   # STALE 뒤
    assert clock.t - 1000.0 >= old.STALE


def test_owner_notices_a_handoff_request_within_a_second(world):
    """박동(10초) 때만 보면 최대 10초 늦게 안다 — 그동안 요청이 붙잡혀 있다."""
    gcs, clock, new = world
    owner = new("owner", "ai-company-00010-xsr")
    gen = owner.acquire()
    asked_at = {}

    def newer_asks():
        doc, g = gcs.read()
        gcs.write({**doc, "state": "handoff", "by": "n", "by_revision": "ai-company-00011-h8b"}, g)
        asked_at["t"] = clock.t

    rc = _hold_until(owner, gen, {"sig": False}, clock, 2.2, newer_asks)
    assert rc == "handoff"
    assert clock.t - asked_at["t"] <= owner.LOOK_EVERY + 1.0
    assert gcs.doc.get("for_revision") == "ai-company-00011-h8b"


def test_hold_answers_liveness_without_counting_it_as_traffic(front):
    m, f, port = front
    f.open()
    assert _get(port, "/api/deploy", timeout=3)[0] == 200
    assert not f.first_request.is_set(), "생존 검사를 트래픽으로 쳤다"
    t = threading.Thread(target=lambda: _get(port, "/api/projects"), daemon=True)
    t.start()
    assert f.first_request.wait(3), "실제 요청이 왔는데 표시가 안 됐다"
    f.set("ready")
    t.join(5)


def test_newer_revision_waits_for_real_traffic_before_asking(world):
    """앞문을 열자마자 넘겨 달라고 했더니, Cloud Run 이 아직 옛 리비전으로 보내던
    요청에 이미 넘겨준 옛 인스턴스가 503 을 냈다(DAY 27 실측 360회 중 5회)."""
    gcs, clock, new = world
    old = new("old", "ai-company-00012-wm5")
    old.acquire()
    n = new("n", "ai-company-00013-r7g")
    traffic = {"on": False}
    kind, state = n._acquire_step(clock.t, -1, clock.t, False, lambda: traffic["on"])
    assert kind == "wait" and gcs.doc["state"] == "held", "트래픽 전에 요청했다"
    traffic["on"] = True
    kind, state = n._acquire_step(clock.t, *state, lambda: traffic["on"])
    assert gcs.doc["state"] == "handoff" and state[2] is True
