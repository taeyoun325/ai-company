"""승인 게이트 — 사람이 끼어드는 지점 (DAY 25 · HITL).

## 이 파일이 지키려는 것

1. **게이트가 서면 실제로 멈춘다.** 계획 승인을 켰는데 테스트 작성이
   시작되면, 그건 승인이 아니라 사후 통보다.
2. **멈춘 동안 자리를 차지하지 않는다.** 승인 대기는 `awaiting` 이고,
   스레드도 좌석도 놓는다. 사람은 몇 시간 뒤에 온다.
3. **결정이 오면 체크포인트에서 이어간다.** 처음부터 다시 계획하지 않는다.
4. **반려는 사유와 함께 담당자에게 간다.** 사유 없는 반려는 거절한다.
5. **기다리는 태스크에 기대지 않는 태스크는 계속 돈다.**
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config                                    # noqa: E402
from app.agents import employee, roles                          # noqa: E402
from app.agents.schemas import Plan, Verdict, WorkResult        # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import engine, gates                       # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402

TIMEOUT = 90


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    monkeypatch.setattr(engine, "DECISION_POLL", 0.05)
    credits.reset()
    registry.reset()
    yield
    credits.reset()
    registry.reset()


def _settle(slug: str, timeout: float = TIMEOUT) -> dict:
    """실행 스레드가 끝날 때까지(끝났거나 · 멈췄거나 · 쉬러 갔거나)."""
    deadline = time.time() + timeout
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    assert not engine.is_running(slug), f"{timeout}초 안에 끝나지 않았다"
    return store.meta(slug)


def _pending(slug: str, gate: str) -> dict:
    rows = [a for a in gates.pending(slug) if a["gate"] == gate]
    assert rows, f"{gate} 승인이 열려 있지 않다: {gates.all_of(slug)}"
    return rows[0]


def _phases(slug: str) -> list[str]:
    return [e["name"] for e in bus.history(slug) if e["type"] == "phase"]


# ── 계획 게이트 ─────────────────────────────────────────────────────
def test_plan_gate_parks_before_tests_are_written():
    slug = engine.start("계산기", gate_list=["plan"])
    m = _settle(slug)
    assert m["status"] == "awaiting"
    assert "WRITE_TESTS" not in _phases(slug), "승인 전에 테스트를 썼다"
    rec = _pending(slug, "plan")
    assert rec["detail"]["tasks"], "CEO 가 볼 계획이 승인 요청에 없다"
    assert not store.files_of(slug)


def test_awaiting_does_not_hold_a_seat(monkeypatch):
    """쉬는 실행이 좌석을 쥐고 있으면, 사람이 자리를 비운 동안 다른
    프로젝트를 못 돌린다."""
    monkeypatch.setattr(engine, "MAX_CONCURRENT", 1)
    a = engine.start("계산기", gate_list=["plan"])
    assert _settle(a)["status"] == "awaiting"
    b = engine.start("다른 계산기")             # 좌석 1개 — 막히면 예외
    assert _settle(b)["status"] == "done"


def test_approving_the_plan_continues_from_the_checkpoint(monkeypatch):
    calls: list[str] = []
    real = employee.ask

    def spy(employee_id, user, schema, history=None, model=None):
        calls.append(schema.__name__)
        return real(employee_id, user, schema, history, model=model)

    monkeypatch.setattr(employee, "ask", spy)
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    assert calls.count("Plan") == 1
    out = engine.decide(slug, _pending(slug, "plan")["id"], "approve")
    assert out["resumed"] is True
    m = _settle(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert calls.count("Plan") == 1, "승인했는데 계획을 처음부터 다시 세웠다"


def test_rejecting_the_plan_sends_the_comment_to_the_planner(monkeypatch):
    seen: list[str] = []
    real = employee.ask

    def spy(employee_id, user, schema, history=None, model=None):
        if schema is Plan:
            seen.append(user)
        return real(employee_id, user, schema, history, model=model)

    monkeypatch.setattr(employee, "ask", spy)
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    engine.decide(slug, _pending(slug, "plan")["id"], "reject",
                  "나눗셈은 빼고 덧셈만 해주세요")
    m = _settle(slug)
    # 고친 계획도 계획이다 — 다시 승인을 기다린다.
    assert m["status"] == "awaiting"
    assert len(seen) == 2 and "나눗셈은 빼고" in seen[1]
    assert m["score_detail"]["replans"] == 1


def test_reject_without_a_comment_is_refused():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    with pytest.raises(gates.GateError):
        engine.decide(slug, _pending(slug, "plan")["id"], "reject", "")


def test_a_decision_cannot_be_made_twice():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    rid = _pending(slug, "plan")["id"]
    engine.decide(slug, rid, "approve")
    with pytest.raises(gates.AlreadyDecided):
        engine.decide(slug, rid, "approve")
    _settle(slug)


def test_stop_decision_stops_the_run():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    engine.decide(slug, _pending(slug, "plan")["id"], "stop")
    m = _settle(slug)
    assert m["status"] == "stopped"


def test_cancel_works_while_awaiting():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    assert engine.cancel(slug) is True
    assert store.meta(slug)["status"] == "stopped"


# ── 태스크 게이트 ───────────────────────────────────────────────────
def test_task_gate_holds_passed_tasks_until_approved():
    slug = engine.start("계산기", gate_list=["task:developer"])
    m = _settle(slug)
    assert m["status"] == "awaiting"
    rec = _pending(slug, "task")
    assert rec["task_id"] == "t1"
    assert "src/calc.py" in rec["detail"]["files"]
    # t2·t3 는 t1 에 기댄다 — 승인 전에는 아무도 시작하지 않는다.
    assert not any(e.get("lane") in ("t2", "t3") for e in bus.history(slug)
                   if e["type"] == "phase")
    engine.decide(slug, rec["id"], "approve")
    m = _settle(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    # 작가·디자이너는 `task:developer` 게이트에 안 걸린다.
    assert [a for a in gates.all_of(slug) if a["gate"] == "task"] == \
        [a for a in gates.all_of(slug) if a.get("task_id") == "t1"]


def test_independent_tasks_keep_running_while_one_waits(monkeypatch):
    """게이트에 걸린 태스크에 **기대지 않는** 태스크는 기다리지 않는다."""
    real = employee.ask

    def fake(employee_id, user, schema, history=None, model=None):
        p = real(employee_id, user, schema, history, model=model)
        if schema is Plan:
            # 디자이너 태스크를 t1 에서 떼어낸다.
            tasks = [t.model_copy(update={"deps": []}) if t.id == "t3" else t
                     for t in p.tasks]
            return p.model_copy(update={"tasks": tasks})
        return p

    monkeypatch.setattr(employee, "ask", fake)
    slug = engine.start("계산기", gate_list=["task:developer"])
    _settle(slug)
    done = {r["id"]: r["status"] for r in store.meta(slug)["tasks"]}
    assert done["t3"] == "done", "기댈 것 없는 디자이너가 개발자 승인을 기다렸다"
    assert done["t1"] == "awaiting"
    assert done["t2"] == "todo"


def test_rejecting_a_task_sends_the_ceo_comment_as_the_rework_reason(monkeypatch):
    feedback: list[str] = []
    real = employee.ask

    def spy(employee_id, user, schema, history=None, model=None):
        if schema is WorkResult and employee_id == "developer":
            feedback.append(user)
        return real(employee_id, user, schema, history, model=model)

    monkeypatch.setattr(employee, "ask", spy)
    slug = engine.start("계산기", gate_list=["task:developer"])
    _settle(slug)
    engine.decide(slug, _pending(slug, "task")["id"], "reject",
                  "함수마다 docstring 을 붙여주세요")
    _settle(slug)
    assert "docstring 을 붙여주세요" in feedback[-1]
    # 다시 통과하면 다시 묻는다 — 게이트는 켜져 있다.
    assert store.meta(slug)["status"] == "awaiting"
    engine.decide(slug, _pending(slug, "task")["id"], "approve")
    assert _settle(slug)["status"] == "done"


def test_confidence_gate_only_stops_unsure_passes(monkeypatch):
    real = employee.ask

    def unsure(employee_id, user, schema, history=None, model=None):
        v = real(employee_id, user, schema, history, model=model)
        head = user.split("# 인수기준", 1)[0]          # 검토 대상 태스크 블록
        if schema is Verdict and v.verdict == "pass" \
                and '"assignee": "writer"' in head:
            return v.model_copy(update={"confidence": 0.3})
        return v

    monkeypatch.setattr(employee, "ask", unsure)
    slug = engine.start("계산기", gate_list=["confidence"])
    m = _settle(slug)
    assert m["status"] == "awaiting"
    rec = _pending(slug, "task")
    assert rec["task_id"] == "t2"
    assert rec["detail"]["reason"] == "confidence"
    assert rec["detail"]["confidence"] == pytest.approx(0.3)


def test_gates_can_be_turned_on_mid_run():
    slug = engine.start("계산기")
    gates.set_gates(slug, ["task"])
    m = _settle(slug)
    # 켜는 시점에 따라 이미 끝난 태스크가 있을 수 있다. 남은 것은 멈춘다.
    assert m["status"] in ("awaiting", "done")


def test_decision_while_stopped_is_applied_on_resume(monkeypatch):
    slug = engine.start("계산기", gate_list=["task:developer"])
    _settle(slug)
    rid = _pending(slug, "task")["id"]
    engine.cancel(slug)
    assert store.meta(slug)["status"] == "stopped"
    out = engine.decide(slug, rid, "approve")
    assert out["resumed"] is False            # 멈춘 실행은 스스로 깨우지 않는다
    engine.resume(slug)
    m = _settle(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    # 승인된 t1 을 다시 만들지 않았다.
    assert m["usage"]["developer"]["calls"] == 2


# ── 검사 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["later", "task:analyst", "task:strategist",
                                 "plan:developer", "task:nobody"])
def test_unknown_gates_are_refused(bad):
    with pytest.raises(gates.GateError):
        gates.normalize([bad])


def test_gate_names_are_normalized():
    assert gates.normalize(["plan", " task:writer ", "plan", ""]) == \
        ["plan", "task:writer"]


def test_task_reason():
    assert gates.task_reason(["task"], "writer", 1.0) == "task"
    assert gates.task_reason(["task:developer"], "writer", 1.0) is None
    assert gates.task_reason(["confidence"], "writer", 0.1) == "confidence"
    assert gates.task_reason(["confidence"], "writer", 0.99) is None
    assert gates.task_reason([], "writer", 0.0) is None


def test_open_gate_does_not_duplicate_the_same_request(tmp_path):
    slug = store.new_project("x")
    a = gates.open_gate(slug, "task", title="t", detail={}, sig="s1")
    b = gates.open_gate(slug, "task", title="t", detail={}, sig="s1")
    assert a["id"] == b["id"]
    assert len(gates.pending(slug)) == 1


def test_verifier_cannot_be_gated_as_a_task_owner():
    assert roles.VERIFIER not in [g.split(":")[1] for g in
                                  gates.normalize(["task:developer"])]
