"""Cloud Run 감독자의 임대 (DAY 27) — 쓰는 인스턴스는 언제나 하나.

Cloud Storage 대신 세대 번호를 흉내 낸 메모리 저장소로 시나리오를 돌린다.
조건부 쓰기(ifGenerationMatch)의 의미만 맞으면 된다.
"""
import importlib.util
import threading
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


class FakeApp:
    pid = 0

    def poll(self):
        return None


def _hold_until(m, gen, stop, clock, after, event=None):
    """가짜 시계로 hold() 를 돌린다. `after` 초 뒤 event() → 그 뒤 SIGTERM."""
    m.start_app = lambda: FakeApp()
    m.stop_app = lambda app, hard: None
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
        return m.hold(gen, stop)
    finally:
        clock.sleep = real_sleep


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
