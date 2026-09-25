"""사무실 상태와 대표 지시창 (DAY 25 · 사규 §2 · §4).

## 이 파일이 지키려는 것

1. **상태 다섯 가지의 규칙.** 연동 대기와 대기를 섞지 않는다 · 상태마다
   이유가 있다 · Mock 으로 끝낸 일을 완료로 치지 않는다.
2. **승인 대기는 회의실에서.** 결재가 열리면 담당자와 검증자가 회의실로
   간다.
3. **"왜 늦어져?" 는 병목 하나.** 결재 대기면 그것부터, 멈췄으면 멈춘
   사유, 문제가 없으면 "지연 없습니다". 내용 없는 답은 없다.
4. **"승인할게" 는 한 건일 때만 결재한다.** 질문처럼 들리는 말은 결재가
   아니다.
"""
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config, office, secretary                      # noqa: E402
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


def _settle(slug: str) -> dict:
    deadline = time.time() + TIMEOUT
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    return store.meta(slug)


def _emp(snap: dict, eid: str) -> dict:
    return next(e for e in snap["employees"] if e["id"] == eid)


# ── 상태 규칙 ───────────────────────────────────────────────────────
def test_every_employee_has_one_of_five_states_and_a_reason():
    slug = engine.start("계산기")
    _settle(slug)
    for snap in (office.snapshot("local"), office.snapshot("local", slug)):
        for e in snap["employees"]:
            assert e["state"] in office.STATES
            assert e["reason"].strip(), f"{e['id']} 상태에 이유가 없다"


def test_mock_employees_are_integration_not_done():
    """사규 §2 ③ — 연결 안 된 서비스는 '완료'로 표시하지 않는다."""
    slug = engine.start("계산기")
    assert _settle(slug)["status"] == "done"
    snap = office.snapshot("local", slug)
    for e in snap["employees"]:
        assert e["state"] != "done", f"Mock 으로 끝낸 {e['id']} 이 완료로 보인다"
        assert e["state"] == "integration"
        assert e["mock"] is True
    assert snap["integrations"], "연동 대기 항목이 비었다"
    for item in snap["integrations"]:
        assert item["why"] and item["affects"]


def test_real_providers_finish_as_done(monkeypatch):
    """키가 있으면(Mock 이 아니면) 끝낸 직원은 완료다."""
    monkeypatch.setattr(office, "_integration_items", lambda owner: ([], {}))
    slug = engine.start("계산기")
    m = _settle(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    snap = office.snapshot("local", slug)
    assert {e["id"]: e["state"] for e in snap["employees"]} == {
        "strategist": "done", "developer": "done", "analyst": "done",
        "writer": "done", "designer": "done"}


def test_integration_and_idle_are_never_mixed(monkeypatch):
    """연동 대기의 이유는 **무엇이 없는지**를 말한다. 대기는 앞 단계를 말한다."""
    snap = office.snapshot("local")
    for e in snap["employees"]:
        if e["state"] == "integration":
            assert any(lbl in e["reason"] for lbl in
                       ("Anthropic", "Gemini", "OpenAI")), e["reason"]
    monkeypatch.setattr(office, "_integration_items", lambda owner: ([], {}))
    for e in office.snapshot("local")["employees"]:
        assert e["state"] == "idle"


def test_pending_approval_moves_people_to_the_meeting_room():
    slug = engine.start("계산기", gate_list=["task:developer"])
    m = _settle(slug)
    assert m["status"] == "awaiting"
    snap = office.snapshot("local", slug)
    dev, qa = _emp(snap, "developer"), _emp(snap, "analyst")
    assert dev["state"] == qa["state"] == "approval"
    assert dev["place"] == qa["place"] == "meeting"
    assert set(snap["meeting"]["who"]) == {"developer", "analyst"}
    assert _emp(snap, "writer")["state"] != "approval"
    step = {s["key"]: s["state"] for s in snap["scenario"]}
    assert step["task_gate"] == "current"
    assert step["plan_gate"] == "off"


def test_held_approval_is_still_pending_and_says_so():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    rid = gates.pending(slug)[0]["id"]
    out = engine.decide(slug, rid, "hold", "내일 보겠습니다")
    assert out["resumed"] is False
    assert gates.pending(slug)[0]["held"] is True
    snap = office.snapshot("local", slug)
    assert "보류" in _emp(snap, "strategist")["reason"]
    engine.decide(slug, rid, "approve")                 # 보류 뒤에도 결정할 수 있다
    assert _settle(slug)["status"] == "done"


def test_discarding_a_task_rolls_it_back_and_the_rest_continues():
    slug = engine.start("계산기", gate_list=["task:designer"])
    m = _settle(slug)
    assert m["status"] == "awaiting"
    rid = next(a for a in gates.pending(slug) if a.get("task_id") == "t3")["id"]
    engine.decide(slug, rid, "discard")
    m = _settle(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert "design/screen.md" not in store.files_of(slug), "폐기한 태스크의 파일이 남았다"
    assert all(t["id"] != "t3" for t in m["checkpoint"]["plan"]["tasks"])


def test_discarding_the_plan_stops_the_run():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    engine.decide(slug, gates.pending(slug)[0]["id"], "discard")
    m = _settle(slug)
    assert m["status"] == "stopped"


# ── 대표 지시창 ─────────────────────────────────────────────────────
NAMES = {"strategist": "한지수", "developer": "박도현", "analyst": "최유나",
         "writer": "이서준", "designer": "정하린"}


@pytest.mark.parametrize("text,intent,who", [
    ("현황 보고", "status", None),
    ("status report", "status", None),
    ("왜 늦어져?", "why", None),
    ("why so slow?", "why", None),
    ("なぜ遅い?", "why", None),
    ("박도현 뭐해?", "whois", "developer"),
    ("what is the designer doing", "whois", "designer"),
    ("검증팀 뭐해", "whois", "analyst"),
    ("회의 소집", "meeting", None),
    ("지금 브리핑", "brief", None),
    ("집중 모드", "focus", None),
    ("집중 모드 해제", "unfocus", None),
    ("승인할게", "approve", None),
    ("approve it", "approve", None),
    ("승인 대기 뭐 있어?", "help", None),       # 질문은 결재가 아니다
    ("결재 대기 몇 건이야", "help", None),
    ("아무 말", "help", None),
])
def test_command_parsing(text, intent, who):
    got_intent, got_who = secretary.parse(text, NAMES)
    assert got_intent == intent, text
    if who:
        assert got_who == who


def test_why_says_the_approval_first_and_nothing_else():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    a = secretary.answer("왜 늦어져?", "local", slug)
    text = a["lines"][0]["text"]
    assert text.startswith("원인은 하나예요 — 대표님 결재 대기입니다")
    assert "회의실에서 2명" in text


def test_why_on_a_stopped_run_names_the_reason(monkeypatch):
    monkeypatch.setattr(config, "MAX_ROUNDS", 2)
    slug = engine.start("계산기")
    m = _settle(slug)
    a = secretary.answer("왜 늦어져?", "local", slug)
    assert "멈춰 있습니다" in a["lines"][0]["text"]
    assert m["stopped_reason"][:10] in a["lines"][0]["text"]


def test_why_without_problems_is_one_line(monkeypatch):
    monkeypatch.setattr(office, "_integration_items", lambda owner: ([], {}))
    assert secretary.answer("왜 늦어져?", "local")["lines"][0]["text"] == \
        "진행 중인 일이 없습니다 — 지연 없습니다."


def test_why_on_a_stopped_run_with_pending_approvals_names_the_stop():
    """멈춘 실행에서는 승인해도 안 넘어간다 — "승인만 주시면" 이라고 하면 거짓말이다."""
    slug = engine.start("계산기", gate_list=["task:developer"])
    _settle(slug)
    engine.cancel(slug)
    text = secretary.answer("왜 늦어져?", "local", slug)["lines"][0]["text"]
    assert text.startswith("멈춰 있습니다")
    assert "재개할 때 그 결정부터" in text
    assert "승인만 주시면" not in text


def test_why_with_nothing_running_still_names_missing_connections():
    """도는 일이 없어도, 맡기는 순간 막힐 것(키 없음)은 말한다 — 사규 §4 ③."""
    text = secretary.answer("왜 늦어져?", "local")["lines"][0]["text"]
    assert text.startswith("진행 중인 일이 없습니다")
    assert "외부 연동 문제" in text and "Anthropic" in text


def test_no_empty_answers():
    """사규 §4 ⑤ — 내용 없는 답변 금지."""
    slug = engine.start("계산기")
    _settle(slug)
    for q in ("현황 보고", "왜 늦어져?", "박도현 뭐해?", "회의 소집",
              "지금 브리핑", "집중 모드", "승인할게", "?"):
        for line in secretary.answer(q, "local", slug)["lines"]:
            assert line["text"].strip()
            assert "열심히" not in line["text"]


def test_meeting_is_one_line_each_in_order():
    slug = engine.start("계산기")
    _settle(slug)
    a = secretary.answer("회의 소집", "local", slug)
    who = [l["who"] for l in a["lines"]]
    assert who == [*secretary.MEETING_ORDER, "secretary"]
    assert all("\n" not in l["text"] for l in a["lines"])
    assert a["action"]["meeting"] == list(secretary.MEETING_ORDER)


def test_approve_command_only_acts_on_a_single_pending_item():
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    a = secretary.answer("승인할게", "local", slug)
    assert a["action"]["decided"]
    assert _settle(slug)["status"] == "done"
    assert secretary.answer("승인할게", "local", slug)["lines"][0]["text"] == \
        "결재할 건이 없습니다."


def test_approve_command_asks_to_choose_when_several_are_pending():
    slug = store.new_project("x")
    gates.open_gate(slug, "task", title="A", detail={}, sig="a")
    gates.open_gate(slug, "task", title="B", detail={}, sig="b")
    a = secretary.answer("승인할게", "local", slug)
    assert len(a["action"]["choose"]) == 2
    assert all(x["status"] == "pending" for x in gates.all_of(slug))


def test_status_report_uses_the_viewers_clock():
    now = 1_790_000_000.0      # UTC 기준 어느 순간
    a = secretary.answer("현황 보고", "local", tz_offset=-540, now=now)
    assert time.strftime("%H:%M", time.gmtime(now + 9 * 3600)) in a["lines"][0]["text"]


# ── API ─────────────────────────────────────────────────────────────
def test_api_office_and_ask():
    from app.main import app
    c = TestClient(app)
    slug = engine.start("계산기", gate_list=["plan"])
    _settle(slug)
    body = c.get(f"/api/office?run={slug}").json()
    assert body["run"]["slug"] == slug and body["approvals"]
    r = c.post("/api/office/ask", json={"text": "왜 늦어져?", "run": slug})
    assert r.status_code == 200 and r.json()["intent"] == "why"
    assert c.post("/api/office/ask", json={"text": "  "}).status_code == 400
    r = c.post(f"/api/runs/{slug}/approvals/{body['approvals'][0]['id']}",
               json={"decision": "hold"})
    assert r.status_code == 200 and r.json()["resumed"] is False
