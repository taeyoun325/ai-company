"""자가 회귀 테스트 — 재설계된 구조용.

여기 있는 것들은 '고쳐도 되는 동작'이 아니라 '깨지면 안 되는 불변식'이다.

이전 설계는 역할별 쓰기 권한(신뢰 경계)이 방어의 축이었다. 그걸 버리고
실제 폴더에서 일하게 됐으므로, 이제 축은 **권한 게이트와 경로 검사** 두 개다.
이 파일이 지키는 게 그 둘이다.

    python -m pytest tests_selftest.py -q
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import approvals    # noqa: E402
from app import config       # noqa: E402
from app import workspace    # noqa: E402


# ── 작업 폴더 경로 안전 ─────────────────────────────────────────────
# 이전에는 격리된 projects/ 안에서만 놀았다. 이제 사용자의 진짜 폴더를 열므로
# 여기가 뚫리면 에이전트가 홈 디렉터리 전체를 건드린다.

@pytest.fixture
def ws(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    workspace.use(str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("path", [
    "../escape.py", "../../escape.py", "src/../../escape.py",
    "src/../../../etc/passwd",
])
def test_path_escape_blocked(ws, path):
    with pytest.raises(workspace.Denied):
        workspace.resolve(path)


def test_absolute_path_outside_blocked(ws, tmp_path):
    outside = tmp_path.parent / "somewhere-else.txt"
    with pytest.raises(workspace.Denied):
        workspace.resolve(str(outside))


@pytest.mark.parametrize("name", ["sitecustomize.py", "usercustomize.py",
                                  "src/sitecustomize.py"])
def test_python_startup_hooks_blocked(ws, name):
    """파이썬이 기동 시 자동 import 하는 파일은 실행 환경을 통째로 바꾼다."""
    with pytest.raises(workspace.Denied):
        workspace.resolve(name)


def test_inside_paths_allowed(ws):
    assert workspace.resolve("src/app.py").is_file()
    assert workspace.resolve("new/deep/file.txt").name == "file.txt"


@pytest.mark.parametrize("name", [".env", "id_rsa", "key.pem", "cert.key",
                                  ".npmrc", ".netrc"])
def test_secret_files_are_flagged(name):
    assert workspace.is_secret(name), f"{name} 이 비밀 파일로 인식되지 않는다"


def test_listing_hides_noise_and_flags_secrets(ws):
    (ws / "node_modules").mkdir()
    (ws / "node_modules" / "x.js").write_text("1", encoding="utf-8")
    rows = workspace.listdir(".", depth=2)
    kinds = {r["path"]: r["kind"] for r in rows}
    assert kinds.get("node_modules") == "skipped", "잡음 폴더가 펼쳐졌다"
    assert not any(r["path"].startswith("node_modules/") for r in rows)
    env = next(r for r in rows if r["path"] == ".env")
    assert env["secret"] is True


def test_workspace_is_process_wide(ws):
    """웹 요청은 매번 다른 스레드에서 온다. 스레드 로컬이면 폴더가 안 보인다."""
    import threading
    seen = {}
    t = threading.Thread(target=lambda: seen.update(root=workspace.current()))
    t.start(); t.join()
    assert seen["root"] == ws


# ── 권한 모드 ───────────────────────────────────────────────────────
# 재설계의 방어 축. 모드마다 실제로 다르게 동작해야 한다.

@pytest.fixture
def gate(monkeypatch):
    monkeypatch.setattr(approvals, "_pending", {}, raising=False)
    monkeypatch.setattr(approvals, "_events", {}, raising=False)
    monkeypatch.setattr(approvals, "TIMEOUT", 1)
    monkeypatch.setattr(approvals, "mode", "auto", raising=False)
    return approvals


def test_all_five_modes_exist(gate):
    assert set(gate.MODES) == {"auto", "manual", "accept_edits", "plan", "bypass"}


@pytest.mark.parametrize("mode, action, expect", [
    # 자동 — 되돌릴 수 있는 것만 통과
    ("auto", "move", "allow"), ("auto", "scroll", "allow"),
    ("auto", "write", "ask"), ("auto", "bash", "ask"), ("auto", "click", "ask"),
    # 수동 — 전부 물어봄
    ("manual", "move", "ask"), ("manual", "write", "ask"), ("manual", "bash", "ask"),
    # 편집 자동 수락 — 파일만 통과, 명령은 물어봄
    ("accept_edits", "write", "allow"), ("accept_edits", "edit", "allow"),
    ("accept_edits", "bash", "ask"), ("accept_edits", "click", "ask"),
    # 계획 — 변경은 전부 차단
    ("plan", "write", "block"), ("plan", "edit", "block"),
    ("plan", "bash", "block"), ("plan", "click", "block"),
    # 권한 무시 — 전부 통과
    ("bypass", "write", "allow"), ("bypass", "bash", "allow"),
    ("bypass", "click", "allow"),
])
def test_mode_gate_matrix(gate, monkeypatch, mode, action, expect):
    monkeypatch.setattr(gate, "mode", mode, raising=False)
    assert gate.gate(action) == expect, f"{mode} 모드에서 {action} 이 {expect} 여야 한다"


def test_plan_mode_raises_planmode(gate, monkeypatch):
    monkeypatch.setattr(gate, "mode", "plan", raising=False)
    with pytest.raises(gate.PlanMode):
        gate.request("write", {"path": "a.py", "content": "x"})


def test_manual_mode_denies_on_timeout(gate, monkeypatch):
    """승인이 없으면 실행 경로가 없어야 한다."""
    monkeypatch.setattr(gate, "mode", "manual", raising=False)
    with pytest.raises(gate.Denied):
        gate.request("write", {"path": "a.py", "content": "x"})


def test_approved_request_returns(gate, monkeypatch):
    import threading
    monkeypatch.setattr(gate, "mode", "manual", raising=False)
    monkeypatch.setattr(gate, "TIMEOUT", 5)

    def approve_soon():
        for _ in range(60):
            p = gate.pending()
            if p:
                gate.decide(p[0]["id"], "approve")
                return
            time.sleep(0.05)

    threading.Thread(target=approve_soon, daemon=True).start()
    assert gate.request("write", {"path": "a.py", "content": "x"})


def test_deny_all_releases_waiters(gate, monkeypatch):
    import threading
    monkeypatch.setattr(gate, "mode", "manual", raising=False)
    monkeypatch.setattr(gate, "TIMEOUT", 10)
    out = []

    def ask():
        try:
            gate.request("bash", {"command": "ls"})
            out.append("ran")
        except gate.Denied:
            out.append("denied")

    t = threading.Thread(target=ask, daemon=True)
    t.start()
    for _ in range(60):
        if gate.pending():
            break
        time.sleep(0.05)
    assert gate.deny_all("테스트") >= 1
    t.join(timeout=5)
    assert out == ["denied"]


# ── 어떤 모드에서도 막는 것 ─────────────────────────────────────────
@pytest.mark.parametrize("mode", ["auto", "manual", "accept_edits", "plan", "bypass"])
@pytest.mark.parametrize("text", [
    "sk-ant-abcdefgh12345678",
    "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ12345",
    "my password is hunter2",
    "비밀번호 1234",
    "4111 1111 1111 1111",
    "123-45-6789",
])
def test_credentials_never_typed_in_any_mode(gate, monkeypatch, mode, text):
    """권한 무시 모드에서도 자격 증명 입력만은 막는다.

    되돌릴 수 없는 일에 대해서는 '모든 권한 허용'이 의미를 갖지 않는다고 봤다.
    """
    monkeypatch.setattr(gate, "mode", mode, raising=False)
    called = []
    monkeypatch.setattr("app.screen.perform", lambda *a, **k: called.append(a))
    with pytest.raises(gate.Denied):
        gate.request("type", {"text": text})
    assert not called, f"{mode} 모드에서 금지된 입력이 실행됐다"


@pytest.mark.parametrize("mode", ["auto", "bypass"])
def test_system_shortcuts_blocked_in_any_mode(gate, monkeypatch, mode):
    monkeypatch.setattr(gate, "mode", mode, raising=False)
    monkeypatch.setattr("app.screen.perform", lambda *a, **k: "ok")
    with pytest.raises(gate.Denied):
        gate.request("key", {"keys": ["win", "r"]})


# ── 에이전트 도구 ───────────────────────────────────────────────────
@pytest.fixture
def tools(ws, gate, monkeypatch):
    from app.tools import agent_tools
    monkeypatch.setattr(gate, "mode", "bypass", raising=False)   # 승인 대기 없이
    return agent_tools


def test_read_refuses_secret_files(tools, ws):
    out = tools.read_file(".env")
    assert "거부됨" in out


def test_read_refuses_outside(tools):
    assert "거부됨" in tools.read_file("../../etc/passwd")


def test_edit_requires_unique_match(tools, ws):
    (ws / "src" / "dup.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    out = tools.edit_file("src/dup.py", "x = 1", "x = 2")
    assert "2번 나옵니다" in out, "여러 번 일치하는데 그대로 바꿨다"
    assert (ws / "src" / "dup.py").read_text(encoding="utf-8") == "x = 1\nx = 1\n"


def test_edit_reports_missing_text(tools):
    assert "없습니다" in tools.edit_file("src/app.py", "존재하지않는텍스트", "x")


def test_edit_applies_when_unique(tools, ws):
    assert "수정됨" in tools.edit_file("src/app.py", "VALUE = 1", "VALUE = 2")
    assert (ws / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_write_creates_file(tools, ws):
    assert "ok" in tools.write_file("src/new.py", "print(1)\n")
    assert (ws / "src" / "new.py").is_file()


def test_write_blocked_in_plan_mode(tools, gate, monkeypatch, ws):
    monkeypatch.setattr(gate, "mode", "plan", raising=False)
    out = tools.write_file("src/planned.py", "print(1)\n")
    assert "계획 모드" in out
    assert not (ws / "src" / "planned.py").exists(), "계획 모드인데 파일이 생겼다"


def test_command_scrubs_secrets_from_env(tools, monkeypatch):
    """생성 코드가 API 키를 읽지 못해야 한다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-CANARY-XYZ")
    out = tools.run_command(
        f'{sys.executable} -c "import os;print(os.environ.get(\'ANTHROPIC_API_KEY\'))"')
    assert "CANARY-XYZ" not in out
    assert "None" in out


def test_safe_commands_skip_gate_only_in_auto(tools, gate, monkeypatch):
    """수동 모드는 '항상 확인'이 약속이므로 예외를 두지 않는다."""
    monkeypatch.setattr(gate, "mode", "manual", raising=False)
    monkeypatch.setattr(gate, "TIMEOUT", 1)
    out = tools.run_command("git status")
    assert "거부" in out, "수동 모드인데 안전 명령이 게이트를 건너뛰었다"


# ── 보조 에이전트 ───────────────────────────────────────────────────
def test_roster_has_three_roles():
    from app.agents import subagents
    ids = {a["id"] for a in subagents.roster()}
    assert ids == {"planner", "reviewer", "tester"}


def test_reviewer_is_a_different_provider():
    """같은 모델끼리 검토하면 같은 실수를 함께 놓친다."""
    from app.agents import subagents
    by = {a["id"]: a["provider"] for a in subagents.roster()}
    assert by["reviewer"] == "gemini"
    assert by["planner"] == "claude"
    assert by["reviewer"] != by["planner"]


def test_planner_and_reviewer_cannot_write():
    from app.agents import subagents
    by = {a["id"]: a["writes"] for a in subagents.roster()}
    assert by["planner"] is False
    assert by["reviewer"] is False
    assert by["tester"] is True


def test_unknown_role_is_rejected():
    from app.agents import subagents
    assert "알 수 없는 역할" in subagents.call("해커", "무언가")


def test_reviewer_prompt_allows_saying_nothing_is_wrong():
    """이 문장이 빠지면 검증자가 무한히 트집을 잡아 루프가 안 끝난다."""
    from app.agents import subagents
    assert "억지로 만들지 말고" in subagents.ROLES["reviewer"]["system"]


# ── 비밀키 브로커 ───────────────────────────────────────────────────
@pytest.fixture
def broker(monkeypatch, tmp_path):
    from app import secrets_broker as sb
    monkeypatch.setattr(sb, "STORE_PATH", tmp_path / ".secrets.json")
    monkeypatch.setattr(sb, "_store", {}, raising=False)
    monkeypatch.setattr(sb, "_loaded", False, raising=False)
    return sb


def test_broker_removes_keys_from_environ(broker, monkeypatch):
    """키가 os.environ 에 남으면 세탁을 빠뜨린 코드 경로가 전부 유출구가 된다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fromenv")
    broker.init()
    assert broker.get("anthropic") == "sk-ant-fromenv"
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "GEMINI_API_KEY" not in os.environ


def test_broker_status_has_no_raw_key(broker):
    broker.set_key("gemini", "AIzaSECRETVALUE12345")
    assert "AIzaSECRETVALUE12345" not in json.dumps(broker.status(), ensure_ascii=False)


def test_broker_scrub_redacts(broker):
    broker.set_key("anthropic", "sk-ant-LEAKYVALUE999")
    out = broker.scrub("오류: sk-ant-LEAKYVALUE999 로 인증 실패")
    assert "sk-ant-LEAKYVALUE999" not in out and "[REDACTED]" in out


def test_broker_persist_roundtrip(broker):
    broker.set_key("anthropic", "sk-ant-persisted")
    path = broker.persist()
    broker._store.clear(); broker._loaded = False
    broker.init()
    assert broker.get("anthropic") == "sk-ant-persisted"
    broker.forget_stored()
    assert not path.exists()


def test_secret_files_are_gitignored():
    ignore = (config.ROOT / ".gitignore").read_text(encoding="utf-8")
    for name in (".secrets.json", "attachments/", "schedules.json"):
        assert name in ignore, f"{name} 이 커밋될 수 있다"


def test_env_example_is_not_gitignored():
    """`.env.*` 가 `.env.example` 까지 삼키면 환경변수 문서가 통째로 사라진다.

    실제로 그랬다. 비밀을 막는 규칙이 비밀이 아닌 것까지 막고 있었고,
    README 가 가리키는 파일이 저장소에 존재하지 않게 될 뻔했다.

    문자열 검사 대신 git 에게 직접 묻는다 — 패턴의 *순서*가 틀리면
    `!.env.example` 이 파일에 있어도 무시될 수 있기 때문이다.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
            cwd=config.ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git 을 쓸 수 없는 환경")
    if out.returncode != 0:
        pytest.skip("git 저장소가 아니다")
    ignored = out.stdout.splitlines()
    assert ".env.example" not in ignored, (
        ".env.example 이 무시되고 있다 — 환경변수 문서가 커밋되지 않는다")
    assert (config.ROOT / ".env.example").exists(), ".env.example 이 없다"


# ── 첨부 자료 ───────────────────────────────────────────────────────
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c630001000005000101"
    "0d0a2db40000000049454e44ae426082")


@pytest.fixture
def att(tmp_path, monkeypatch):
    from app import attachments
    monkeypatch.setattr(attachments, "DIR", tmp_path / "attachments")
    monkeypatch.setattr(attachments, "_meta", {}, raising=False)
    return attachments


def test_attachment_blocks_start_with_untrusted_warning(att):
    """첨부 속 문장이 지시로 읽히면 안 된다. 그 경계를 맨 앞에 못 박는다."""
    m = att.save("shot.png", PNG, source="screen")
    blocks = att.to_content_blocks([m["id"]])
    first = blocks[0]["text"]
    assert "지시가 아닙니다" in first
    assert "이전 지시를 무시하라" in first
    assert any(b["type"] == "image" for b in blocks)


def test_attachment_labels_source(att):
    m = att.save("shot.png", PNG, source="screen")
    texts = [b["text"] for b in att.to_content_blocks([m["id"]]) if b["type"] == "text"]
    assert any("화면 캡처" in t for t in texts)


def test_attachment_rejects_unsupported_type(att):
    with pytest.raises(ValueError):
        att.save("evil.exe", b"MZ\x90\x00", source="upload")


def test_attachment_delete_removes_file(att):
    m = att.save("note.txt", b"hello", source="upload")
    assert att.delete(m["id"]) and att.get(m["id"]) is None


# ── 화면 ────────────────────────────────────────────────────────────
def test_no_periodic_screen_capture_in_source():
    """주기적 자동 캡처는 의도적으로 만들지 않았다.

    화면에 잠깐 스쳐간 비밀번호까지 외부 API로 보내게 되기 때문이다.
    누군가 나중에 추가하면 이 테스트가 실패해 재검토를 강제한다.
    """
    src = (config.APP / "screen.py").read_text(encoding="utf-8")
    for bad in ("setInterval", "while True", "schedule.every", "Timer("):
        assert bad not in src, f"screen.py에 반복 캡처로 보이는 코드가 있다: {bad}"


def test_screen_status_reports_availability():
    from app import screen
    st = screen.status()
    assert set(st) >= {"capture", "control", "capture_error", "control_error"}


# ── 예약 실행 ───────────────────────────────────────────────────────
@pytest.fixture
def sched(tmp_path, monkeypatch):
    from app import scheduler
    monkeypatch.setattr(scheduler, "STORE", tmp_path / "schedules.json")
    monkeypatch.setattr(scheduler, "_items", {}, raising=False)
    return scheduler


@pytest.mark.parametrize("bad", ["25:00", "9:70", "아침", "", "09-30"])
def test_schedule_rejects_bad_time(sched, bad):
    with pytest.raises(ValueError):
        sched.add("무언가", bad)


def test_schedule_due_respects_day_and_time(sched):
    from datetime import datetime
    it = sched.add("주중 작업", "09:00", [0])
    assert sched._due(it, datetime(2026, 9, 7, 9, 0))       # 월
    assert not sched._due(it, datetime(2026, 9, 8, 9, 0))   # 화
    assert not sched._due(it, datetime(2026, 9, 7, 9, 1))


def test_schedule_does_not_fire_twice_in_same_minute(sched):
    from datetime import datetime
    it = sched.add("한 번만", "09:00")
    now = datetime(2026, 9, 7, 9, 0)
    fired = []
    sched.configure(lambda r: fired.append(r) or "main")
    sched._fire(it, now)
    assert not sched._due(it, now)
    assert fired == ["한 번만"]


def test_schedule_records_skip_reason(sched):
    from datetime import datetime
    it = sched.add("실패할 것", "09:00")
    sched.configure(lambda _: (_ for _ in ()).throw(RuntimeError("작업 폴더가 없습니다")))
    sched._fire(it, datetime(2026, 9, 7, 9, 0))
    assert "건너뜀" in it["last_note"]


# ── 협업 타임라인 ───────────────────────────────────────────────────
@pytest.fixture
def trace(tmp_path, monkeypatch):
    from app import timeline
    monkeypatch.setattr(config, "LOGS", tmp_path)
    rows = [
        {"type": "phase", "ts": 100.0, "run": "main", "name": "PLAN"},
        {"type": "phase", "ts": 102.0, "run": "main", "name": "IMPLEMENT"},
        {"type": "phase", "ts": 105.0, "run": "main", "name": "REVIEW"},
        {"type": "done", "ts": 106.0, "run": "main", "ok": True, "score": 100},
        {"type": "phase", "ts": 103.0, "run": "other", "name": "PLAN"},
    ]
    (tmp_path / "trace.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return timeline


def test_timeline_only_includes_its_own_run(trace):
    assert len([s for s in trace.build("main")["segments"] if s["phase"] == "PLAN"]) == 1


def test_timeline_counts_handoffs(trace):
    tl = trace.build("main")
    assert tl["handoffs"] and all(h["from"] != h["to"] for h in tl["handoffs"])


def test_timeline_survives_truncated_last_line(trace, tmp_path):
    """로그를 쓰는 도중에 읽으면 마지막 줄이 잘릴 수 있다."""
    p = tmp_path / "trace.jsonl"
    p.write_text(p.read_text(encoding="utf-8") + '\n{"type": "pha', encoding="utf-8")
    assert trace.build("main")["segments"]


# ── 이벤트 버스 ─────────────────────────────────────────────────────
def test_bus_history_is_bounded_per_run():
    """무한히 쌓이면 오래 켜둔 세션이 메모리를 먹는다.

    실행별로 나눠 보관하는 이유(§13): 한 덱에 전부 쌓으면 바쁜 실행 하나가
    다른 실행의 이력을 밀어내고, 조용한 프로젝트의 화면이 이유 없이 빈다.
    """
    from app import bus
    bus.bind("bounded-run")
    try:
        for i in range(bus.HISTORY_LIMIT + 50):
            bus.say("SYSTEM", str(i))
        assert len(bus.history("bounded-run")) == bus.HISTORY_LIMIT
    finally:
        bus.reset("bounded-run")
        bus.release()


def test_bus_tags_events_with_run():
    from app import bus
    bus.bind("t-run")
    bus.say("AGENT", "안녕")
    evs = bus.history("t-run")
    assert evs and all(e["run"] == "t-run" for e in evs)
    bus.reset("t-run")


# ── UI 불변식 ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def html():
    return (config.WEB / "index.html").read_text(encoding="utf-8")


def test_ui_has_no_external_deps(html):
    for bad in ("cdn.", "https://unpkg", 'src="http', "@import url(http"):
        assert bad not in html, f"UI에 외부 의존성이 들어왔다: {bad}"


@pytest.mark.parametrize("needle, why", [
    ('class="skip"',            "스킵 링크"),
    ("<main class=",            "main 랜드마크"),
    ('aria-label="에이전트와 계기판"', "좌측 레일 이름"),
    ("<h1",                     "h1 제목"),
    ('for="q"',                 "입력 라벨"),
    ('role="log"',              "대화 라이브 리전"),
    ('aria-live="polite"',      "라이브 리전 공손 모드"),
    ("@media (prefers-reduced-motion: reduce)", "모션 축소"),
    (":focus-visible",          "포커스 표시"),
    ('role="dialog"',           "다이얼로그 역할"),
    ('aria-modal="true"',       "모달 격리"),
    ("lastFocus.focus()",       "모달 닫을 때 포커스 복귀"),
])
def test_accessibility_preserved(html, needle, why):
    assert needle in html, f"접근성 기능이 사라졌다: {why}"


@pytest.mark.parametrize("needle, why", [
    ('id="mode-list"',   "권한 모드 선택"),
    ('id="open-ws"',     "작업 폴더 열기"),
    ('id="apv"',         "승인 패널"),
    ('id="att-screen"',  "화면 캡처"),
    ('id="tree"',        "파일 트리"),
    ('id="changed"',     "변경된 파일"),
    ("/api/send",        "대화 전송"),
    ("/api/permission",  "권한 모드 API"),
])
def test_core_ui_wired(html, needle, why):
    assert needle in html, f"UI 배선이 끊겼다: {why}"


def test_tool_logs_excluded_from_live_announcements(html):
    """툴 호출까지 낭독되면 대화를 따라갈 수 없다."""
    assert "if (kind === 'tool') el.setAttribute('aria-hidden','true')" in html


def test_low_contrast_token_not_reintroduced(html):
    """--faint:#3f5170 은 배경 대비 약 2.5:1로 WCAG AA 미달이었다."""
    assert "#3f5170" not in html
