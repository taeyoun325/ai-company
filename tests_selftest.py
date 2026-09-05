"""자가 회귀 테스트 — 개선 루프가 매 회차 끝에 돌린다.

여기 있는 것들은 '고쳐도 되는 동작'이 아니라 '깨지면 안 되는 불변식'이다.
특히 신뢰 경계와 비밀키 격리는 한 번 무너지면 나머지 검증이 전부 무의미해진다.

    python -m pytest tests_selftest.py -q
"""
import json
import os
import re
import time
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import config          # noqa: E402
import runner          # noqa: E402
import store           # noqa: E402
from tools import fs   # noqa: E402


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("테스트 프로젝트")
    fs.use(slug)
    fs.write("src/app.py", "VALUE = 1\n", "DEV")
    fs.write("tests/test_app.py", "from app import VALUE\n\ndef test_v():\n    assert VALUE == 1\n", "QA")
    return slug


# ── 신뢰 경계: 구현자는 검증기를 고칠 수 없다 ─────────────────────
@pytest.mark.parametrize("path", [
    "tests/test_app.py",          # 남의 영역
    "tests/test_new.py",
])
def test_dev_cannot_write_tests(project, path):
    with pytest.raises(fs.Denied):
        fs.write(path, "def test_x(): assert True\n", "DEV")


def test_dev_cannot_read_tests(project):
    with pytest.raises(fs.Denied):
        fs.read("tests/test_app.py", "DEV")


def test_dev_listing_hides_tests(project):
    assert fs.listdir("DEV") == ["src/app.py"]


def test_qa_cannot_write_src(project):
    with pytest.raises(fs.Denied):
        fs.write("src/sneak.py", "x = 1\n", "QA")


@pytest.mark.parametrize("name", [
    "src/conftest.py", "src/pytest.ini", "src/pyproject.toml",
    "src/setup.cfg", "src/sitecustomize.py", "src/usercustomize.py",
])
def test_config_files_are_forbidden_everywhere(project, name):
    """pytest나 파이썬이 자동으로 읽어들이는 파일은 실행 환경을 바꿀 수 있다."""
    with pytest.raises(fs.Denied):
        fs.write(name, "# evil\n", "DEV")


@pytest.mark.parametrize("path", ["../escape.py", "../../escape.py", "src/../../escape.py"])
def test_path_escape_blocked(project, path):
    with pytest.raises(fs.Denied):
        fs.write(path, "x", "DEV")


def test_meta_file_not_writable(project):
    with pytest.raises(fs.Denied):
        fs.write(store.META, "{}", "SYSTEM")


# ── 비밀키 격리 ────────────────────────────────────────────────────
def test_env_scrubbing_removes_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-x")
    monkeypatch.setenv("MY_SECRET_TOKEN", "t")
    monkeypatch.setenv("HARMLESS_VAR", "ok")
    env = runner._clean_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "GEMINI_API_KEY" not in env
    assert "MY_SECRET_TOKEN" not in env
    assert env["HARMLESS_VAR"] == "ok"
    assert env["PYTHONNOUSERSITE"] == "1"   # usercustomize.py 자동 import 차단
    assert "PYTHONPATH" not in env


@pytest.mark.slow
def test_generated_code_cannot_read_api_key(project, monkeypatch):
    """실제로 pytest를 띄워서 키가 새는지 본다. 가장 중요한 테스트."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-LEAK-CANARY")
    fs.write("tests/test_leak.py",
             "import os\n\n"
             "def test_leak():\n"
             "    print('SAW:', os.environ.get('ANTHROPIC_API_KEY'))\n"
             "    assert os.environ.get('ANTHROPIC_API_KEY') is None\n", "QA")
    r = runner.run(fs.root())
    assert "LEAK-CANARY" not in r["output"]
    assert r["ok"], f"키가 자식 프로세스에 노출됨: {r['output']}"


# ── 완성도 산출 ────────────────────────────────────────────────────
def test_score_excludes_qa_pass_rate():
    """QA가 관대할수록 점수가 오르면 순환논리다. 그 경로가 없어야 한다."""
    from orchestrator import Score
    s = Score()
    s.total_tasks, s.done_tasks = 2, 1
    s.tests_ran, s.tests_pass = True, True
    s.reviews, s.passes = 10, 10
    high = s.value()
    s.reviews, s.passes = 10, 1        # QA가 훨씬 엄격해져도
    assert s.value() == high, "검수 통과율이 점수에 새어들어가고 있다"


def test_final_score_is_acceptance_criteria_ratio():
    from orchestrator import Score
    s = Score()
    s.total_tasks = s.done_tasks = 3
    s.tests_pass = True
    s.ac_total, s.ac_met = 4, 3
    assert s.value() == 75


def test_score_is_zero_at_start():
    from orchestrator import Score
    assert Score().value() == 0


# ── 예산 가드 ──────────────────────────────────────────────────────
def test_budget_checked_before_the_call(monkeypatch):
    """사후 감지는 상한이 아니다. 호출 전에 최악 비용을 더해서 막아야 한다."""
    import orchestrator
    import usage
    usage.reset()
    monkeypatch.setattr(config, "BUDGET_USD", 0.01)
    with pytest.raises(orchestrator.Stop):
        orchestrator._spend_guard(1, config.WORST_CASE["DEV"])


def test_round_limit(monkeypatch):
    import orchestrator
    monkeypatch.setattr(config, "MAX_ROUNDS", 5)
    with pytest.raises(orchestrator.Stop):
        orchestrator._spend_guard(6, 0.0)


def test_worst_case_estimates_are_positive():
    assert all(v > 0 for v in config.WORST_CASE.values())


# ── 태스크 지문 ────────────────────────────────────────────────────
def test_task_signature_changes_when_meaning_changes():
    """재기획으로 같은 id에 다른 내용이 와도 완료로 착각하면 안 된다."""
    from orchestrator import _sig
    from schemas import Task
    a = Task(id="t1", title="A", deps=[], files=["src/a.py"], covers=["ac1"], done_when="x")
    b = Task(id="t1", title="B", deps=[], files=["src/a.py"], covers=["ac1"], done_when="x")
    same = Task(id="t1", title="A", deps=[], files=["src/a.py"], covers=["ac1"], done_when="x")
    assert _sig(a) != _sig(b)
    assert _sig(a) == _sig(same)


# ── 저장소 ─────────────────────────────────────────────────────────
def test_tool_artifacts_excluded_from_outputs(project):
    root = store.dir_of(project)
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    files = store.files_of(project)
    assert "pytest.ini" not in files
    assert not any("__pycache__" in f for f in files)
    assert set(files) == {"src/app.py", "tests/test_app.py"}


def test_meta_survives_updates(project):
    store.save_meta(project, {"score": 42})
    store.save_meta(project, {"status": "done"})
    m = store.meta(project)
    assert m["score"] == 42 and m["status"] == "done"
    assert m["requirement"] == "테스트 프로젝트"


# ── UI 불변식 ──────────────────────────────────────────────────────
def test_ui_is_a_single_file_with_no_external_deps():
    html = (config.ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for bad in ("cdn.", "https://unpkg", "src=\"http", "@import url(http"):
        assert bad not in html, f"UI에 외부 의존성이 들어왔다: {bad}"


def test_ui_has_required_elements():
    """루프가 UI를 고치다가 배선을 끊는 일을 막는다."""
    html = (config.ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for ident in ("id=\"log\"", "id=\"agents\"", "id=\"board\"", "id=\"repos\"",
                  "id=\"files\"", "id=\"arc\"", "/api/stream", "/api/start"):
        assert ident in html, f"UI에서 {ident} 가 사라졌다"


# ── 접근성 불변식 ──────────────────────────────────────────────────
# 루프가 UI를 계속 고치므로, 되돌아가기 쉬운 것들을 못으로 박아둔다.
@pytest.fixture(scope="module")
def html():
    return (config.ROOT / "web" / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("needle, why", [
    ('class="skip"',                    "스킵 링크"),
    ("<main class=",                    "main 랜드마크"),
    ('aria-label="진행 상황 계기판"',      "좌측 레일 이름"),
    ('aria-label="산출물과 저장소"',       "우측 레일 이름"),
    ("<h1 class=",                      "h1 제목"),
    ('for="q"',                         "입력 라벨"),
    ('role="log"',                      "대화 로그 라이브 리전"),
    ('aria-live="polite"',              "라이브 리전 공손 모드"),
    ('role="status"',                   "단계 상태 리전"),
    ("@media (prefers-reduced-motion: reduce)", "모션 축소"),
    (":focus-visible",                  "포커스 표시"),
    ('role="dialog"',                   "모달 역할"),
    ('aria-modal="true"',               "모달 격리"),
    ("lastFocus.focus()",               "모달 닫을 때 포커스 복귀"),
])
def test_accessibility_features_present(html, needle, why):
    assert needle in html, f"접근성 기능이 사라졌다: {why} ({needle})"


def test_low_contrast_token_not_reintroduced(html):
    """--faint:#3f5170 은 배경 대비 약 2.5:1로 WCAG AA 미달이었다."""
    assert "#3f5170" not in html, "대비가 낮은 옛 --faint 색이 되돌아왔다"


def test_decorative_glyphs_are_hidden(html):
    """아바타·아이콘 문자는 장식이다. 스크린 리더가 읽으면 소음이 된다."""
    assert 'class="av" aria-hidden="true"' in html
    assert '<div class="bar" aria-hidden="true">' in html


def test_tool_logs_excluded_from_live_announcements(html):
    """툴 호출까지 낭독되면 대화를 따라갈 수 없다."""
    assert "const quiet = (kind === 'tool')" in html
    assert "el.setAttribute('aria-hidden', 'true')" in html


# ── 비밀키 브로커 (B1) ─────────────────────────────────────────────
@pytest.fixture
def broker(monkeypatch, tmp_path):
    import secrets_broker as sb
    monkeypatch.setattr(sb, "STORE_PATH", tmp_path / ".secrets.json")
    monkeypatch.setattr(sb, "_store", {}, raising=False)
    monkeypatch.setattr(sb, "_loaded", False, raising=False)
    return sb


def test_broker_removes_keys_from_environ(broker, monkeypatch):
    """키가 os.environ에 남아 있으면 세탁을 빠뜨린 코드 경로가 전부 유출구가 된다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fromenv")
    broker.init()
    assert broker.get("anthropic") == "sk-ant-fromenv"
    assert "ANTHROPIC_API_KEY" not in os.environ, "키가 환경에 그대로 남아 있다"
    assert "GEMINI_API_KEY" not in os.environ


def test_broker_masks_never_exposes_raw(broker):
    broker.set_key("anthropic", "sk-ant-abcdefghijklmnop")
    masked = broker.mask("anthropic")
    assert "abcdefghijkl" not in masked
    assert masked.startswith("sk-ant") and masked.endswith("mnop")


def test_broker_status_has_no_raw_key(broker):
    broker.set_key("gemini", "AIzaSECRETVALUE12345")
    blob = json.dumps(broker.status(), ensure_ascii=False)
    assert "AIzaSECRETVALUE12345" not in blob, "status()가 원문 키를 노출한다"


def test_broker_scrub_redacts_keys_from_text(broker):
    broker.set_key("anthropic", "sk-ant-LEAKYVALUE999")
    out = broker.scrub("오류: sk-ant-LEAKYVALUE999 로 인증 실패")
    assert "sk-ant-LEAKYVALUE999" not in out
    assert "[REDACTED]" in out


def test_broker_require_raises_when_missing(broker):
    with pytest.raises(RuntimeError):
        broker.require("anthropic")


def test_broker_persist_roundtrip(broker):
    broker.set_key("anthropic", "sk-ant-persisted")
    path = broker.persist()
    assert path.exists()
    broker._store.clear()
    broker._loaded = False
    broker.init()
    assert broker.get("anthropic") == "sk-ant-persisted"
    broker.forget_stored()
    assert not path.exists()


def test_secrets_file_is_gitignored():
    ignore = (config.ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".secrets.json" in ignore, "키 저장 파일이 커밋될 수 있다"


# ── 설정 화면 (C1) ─────────────────────────────────────────────────
@pytest.mark.parametrize("needle, why", [
    ('id="cfg-open"',                "설정 열기 버튼"),
    ('aria-labelledby="cfg-title"',  "설정 다이얼로그 이름"),
    ('type="password" id="k-anthropic"', "키 입력이 password 타입"),
    ('id="qa-model"',                "검증자 모델 선택"),
    ('.modal[data-open="1"]',        "열린 모달 전부 포커스 트랩"),
])
def test_settings_ui_present(html, needle, why):
    assert needle in html, f"설정 화면 요소가 사라졌다: {why}"


def test_settings_ui_clears_key_inputs_on_close(html):
    """입력한 키를 DOM에 남겨두지 않는다."""
    assert "$('k-anthropic').value = ''; $('k-gemini').value = '';" in html


# ── 파일 이력과 diff (B2) ──────────────────────────────────────────
def test_overwrite_creates_history(project):
    """에이전트는 파일을 통째로 덮어쓴다. 이전 내용이 남아야 diff를 볼 수 있다."""
    fs.write("src/app.py", "VALUE = 2\n", "DEV")
    vers = store.versions(project, "src/app.py")
    past = [v for v in vers if v["version"] != 0]
    assert len(past) == 1, "덮어쓰기 전 내용이 이력에 안 남았다"
    assert store.version_text(project, "src/app.py", past[0]["version"]) == "VALUE = 1\n"
    assert store.version_text(project, "src/app.py", 0) == "VALUE = 2\n"


def test_identical_write_makes_no_history(project):
    """같은 내용을 다시 써도 버전이 늘면 이력이 잡음으로 가득 찬다."""
    fs.write("src/app.py", "VALUE = 1\n", "DEV")
    past = [v for v in store.versions(project, "src/app.py") if v["version"] != 0]
    assert past == []


def test_diff_marks_added_and_removed_lines(project):
    fs.write("src/app.py", "VALUE = 1\nEXTRA = 9\n", "DEV")
    rows = store.diff(project, "src/app.py", 1, 0)
    kinds = {r["kind"] for r in rows}
    assert "add" in kinds
    assert any(r["kind"] == "add" and "EXTRA = 9" in r["text"] for r in rows)


def test_history_not_listed_as_output(project):
    """.history/ 는 산출물이 아니다."""
    fs.write("src/app.py", "VALUE = 3\n", "DEV")
    assert not any(".history" in f for f in store.files_of(project))


@pytest.mark.parametrize("needle, why", [
    ('id="vedit"',    "편집 textarea"),
    ('id="vdiff"',    "diff 패널"),
    ('role="tablist"', "편집/변경내역 탭"),
    ('id="vver"',     "비교 버전 선택"),
    ('id="vsave"',    "저장 버튼"),
])
def test_editor_ui_present(html, needle, why):
    assert needle in html, f"편집기 요소가 사라졌다: {why}"


# ── 미리보기 (B3) ──────────────────────────────────────────────────
def test_preview_iframe_is_not_given_same_origin(html):
    """allow-scripts 와 allow-same-origin 을 함께 주면 샌드박스가 무의미해진다.

    생성된 코드가 부모 문서에 접근할 수 있게 되므로 이 조합은 절대 안 된다.
    """
    m = re.search(r"setAttribute\('sandbox',\s*'([^']*)'\)", html)
    assert m, "미리보기 iframe에 sandbox 속성이 없다"
    tokens = m.group(1).split()
    assert "allow-scripts" in tokens
    assert "allow-same-origin" not in tokens, \
        "allow-scripts 와 allow-same-origin 을 함께 주면 격리가 뚫린다"


@pytest.mark.parametrize("needle, why", [
    ('id="pv-modal"', "미리보기 다이얼로그"),
    ('id="pv-open"',  "미리보기 열기 버튼"),
    ('id="pv-run"',   "진입점 실행 버튼"),
])
def test_preview_ui_present(html, needle, why):
    assert needle in html, f"미리보기 요소가 사라졌다: {why}"


def test_entry_point_detection(project):
    import runner
    d = store.dir_of(project)
    assert runner.find_entry(d) == "src/app.py"       # 유일한 .py
    fs.write("src/main.py", "print(1)\n", "DEV")
    assert runner.find_entry(d) == "src/main.py"      # main.py 우선
    assert runner.find_html(d) is None
    fs.write("src/index.html", "<p>hi</p>\n", "DEV")
    assert runner.find_html(d) == "src/index.html"


@pytest.mark.slow
def test_run_entry_is_isolated_like_pytest(project, monkeypatch):
    """미리보기 실행도 키를 못 봐야 한다. 격리가 한쪽만 되면 의미가 없다."""
    import runner
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-PREVIEW-CANARY")
    fs.write("src/main.py",
             "import os\nprint('KEY=', os.environ.get('ANTHROPIC_API_KEY'))\n", "DEV")
    r = runner.run_entry(store.dir_of(project), "src/main.py")
    assert "PREVIEW-CANARY" not in r["output"]
    assert "KEY= None" in r["output"]


# ── 동시 실행 격리 (B4) ────────────────────────────────────────────
# 전역 상태 하나로 두면 두 프로젝트가 서로를 덮어쓴다.
# 실행 하나가 스레드 하나이므로 스레드 로컬로 가른다.

def test_fs_current_project_is_per_thread(tmp_path, monkeypatch):
    """두 스레드가 서로 다른 프로젝트를 가리켜야 한다."""
    import threading
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    a = store.new_project("가")
    b = store.new_project("나")
    seen = {}

    def work(slug, key):
        fs.use(slug)
        time.sleep(0.05)              # 서로 겹치도록
        seen[key] = fs.slug()

    t1 = threading.Thread(target=work, args=(a, "a"))
    t2 = threading.Thread(target=work, args=(b, "b"))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert seen["a"] == a and seen["b"] == b, f"fs 컨텍스트가 섞였다: {seen}"


def test_fs_requires_use_in_each_thread(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    fs.use(store.new_project("메인"))
    err = []

    def work():
        try:
            fs.slug()
        except RuntimeError as e:
            err.append(str(e))

    t = threading.Thread(target=work)
    t.start(); t.join()
    assert err, "다른 스레드가 메인 스레드의 프로젝트를 물려받았다"


def test_usage_is_counted_per_run():
    """실행별로 따로 세지 않으면 예산 상한이 엉뚱하게 걸린다."""
    import usage
    usage.bind("run-a")
    usage.record("DEV", "claude-opus-5", 1000, 500)
    a_cost = usage.total_cost("run-a")

    usage.bind("run-b")
    usage.record("DEV", "claude-opus-5", 2000, 1000)

    assert usage.total_cost("run-a") == a_cost, "다른 실행의 사용량이 섞였다"
    assert usage.total_cost("run-b") > a_cost
    assert usage.agents_of("run-a")["DEV"]["input"] == 1000
    assert usage.agents_of("run-b")["DEV"]["input"] == 2000
    usage.drop("run-a"); usage.drop("run-b")


def test_bus_tags_events_with_run():
    import bus
    bus.bind("run-x")
    bus.say("PM", "안녕")
    evs = bus.history("run-x")
    assert evs and all(e["run"] == "run-x" for e in evs)
    bus.reset("run-x")


def test_bus_reset_only_clears_its_own_run():
    """한 실행을 새로 시작해도 다른 실행의 기록이 날아가면 안 된다."""
    import bus
    bus.bind("run-keep")
    bus.say("PM", "남아야 함")
    bus.bind("run-wipe")
    bus.say("PM", "지워질 것")
    bus.reset("run-wipe")
    assert bus.history("run-keep"), "다른 실행 기록까지 지워졌다"
    assert not bus.history("run-wipe")
    bus.reset("run-keep")


def test_bus_history_is_bounded():
    """무한히 쌓이면 오래 켜둔 세션이 메모리를 먹는다."""
    import bus
    assert bus._history.maxlen == bus.HISTORY_LIMIT


def test_concurrency_limit_is_enforced(monkeypatch, tmp_path):
    import orchestrator
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(orchestrator, "MAX_CONCURRENT", 0)
    with pytest.raises(RuntimeError):
        orchestrator.start("한도 초과", mock=True)


@pytest.mark.parametrize("needle, why", [
    ('id="ws" role="tablist"', "작업공간 탭 바"),
    ("const runs = new Map()", "실행별 상태 보관"),
    ("function switchTo(slug)", "탭 전환"),
    ("const showing = (ev.run === curSlug)", "활성 탭만 렌더"),
])
def test_workspace_tabs_present(html, needle, why):
    assert needle in html, f"작업공간 요소가 사라졌다: {why}"


def test_completion_summary_survives_tab_switch(html):
    """renderDone(d, false) 는 아무것도 안 그려서 탭을 옮기면 요약이 사라졌다."""
    assert "renderDone(d, append)" not in html, "append 분기가 되살아났다"
    assert "if (r.done) renderDone(r.done);" in html


# ── 첨부 자료 (B7) ─────────────────────────────────────────────────
@pytest.fixture
def att(tmp_path, monkeypatch):
    import attachments
    monkeypatch.setattr(attachments, "DIR", tmp_path / "attachments")
    monkeypatch.setattr(attachments, "_meta", {}, raising=False)
    return attachments


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")


def test_attachment_blocks_start_with_untrusted_warning(att):
    """첨부 속 문장이 지시로 읽히면 안 된다. 그 경계를 맨 앞에 못 박는다."""
    m = att.save("shot.png", PNG, source="screen")
    blocks = att.to_content_blocks([m["id"]])
    assert blocks[0]["type"] == "text"
    first = blocks[0]["text"]
    assert "지시가 아닙니다" in first
    assert "이전 지시를 무시하라" in first      # 대표적인 주입 문구를 예시로 경고
    assert any(b["type"] == "image" for b in blocks)


def test_attachment_labels_source(att):
    m = att.save("shot.png", PNG, source="screen")
    texts = [b["text"] for b in att.to_content_blocks([m["id"]]) if b["type"] == "text"]
    assert any("화면 캡처" in t for t in texts)


def test_attachment_rejects_unsupported_type(att):
    with pytest.raises(ValueError):
        att.save("evil.exe", b"MZ\x90\x00", source="upload")


def test_attachment_rejects_oversized(att, monkeypatch):
    monkeypatch.setattr(att, "MAX_BYTES", 10)
    with pytest.raises(ValueError):
        att.save("big.txt", b"x" * 100, source="upload")


def test_attachment_delete_removes_file(att):
    m = att.save("note.txt", b"hello", source="upload")
    assert att.get(m["id"])
    assert att.delete(m["id"])
    assert att.get(m["id"]) is None


def test_attachments_are_gitignored():
    ignore = (config.ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "attachments/" in ignore, "사용자의 화면 캡처가 커밋될 수 있다"


# ── 화면 조작 승인 게이트 (B7) ─────────────────────────────────────
# 이 블록이 이 기능의 안전을 지탱한다. 하나라도 깨지면 기능을 꺼야 한다.

@pytest.fixture
def apv(monkeypatch):
    import approvals
    monkeypatch.setattr(approvals, "_pending", {}, raising=False)
    monkeypatch.setattr(approvals, "_events", {}, raising=False)
    monkeypatch.setattr(approvals, "auto_approve_low_risk", False, raising=False)
    monkeypatch.setattr(approvals, "TIMEOUT", 1)
    return approvals


@pytest.mark.parametrize("text", [
    "sk-ant-abcdefgh12345678",
    "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ12345",
    "my password is hunter2",
    "비밀번호 1234",
    "4111 1111 1111 1111",
    "123-45-6789",
])
def test_credentials_are_never_typed(apv, text, monkeypatch):
    """자격 증명·민감 번호는 어떤 승인으로도 입력하지 않는다."""
    called = []
    monkeypatch.setattr("screen.perform", lambda *a, **k: called.append(a))
    with pytest.raises(apv.Denied):
        apv.request("type", {"text": text})
    assert not called, "금지된 입력이 실행됐다"


def test_action_waits_for_approval_and_denies_on_timeout(apv, monkeypatch):
    """승인이 없으면 실행 경로가 없어야 한다."""
    called = []
    monkeypatch.setattr("screen.perform", lambda *a, **k: called.append(a))
    with pytest.raises(apv.Denied):
        apv.request("click", {"x": 10, "y": 10})    # TIMEOUT=1 이라 거부됨
    assert not called, "승인 없이 실행됐다"


def test_approved_action_executes(apv, monkeypatch):
    import threading
    done = []
    monkeypatch.setattr("screen.perform", lambda a, **k: done.append(a) or "ok")
    monkeypatch.setattr(apv, "TIMEOUT", 5)

    def approve_soon():
        for _ in range(50):
            p = apv.pending()
            if p:
                apv.decide(p[0]["id"], "approve")
                return
            time.sleep(0.05)

    threading.Thread(target=approve_soon, daemon=True).start()
    apv.request("click", {"x": 5, "y": 5})
    assert done == ["click"]


def test_auto_approve_never_covers_click_or_type(apv, monkeypatch):
    """자동 승인은 되돌릴 수 있는 것에만. 클릭·입력은 항상 물어봐야 한다."""
    monkeypatch.setattr("screen.perform", lambda *a, **k: "ok")
    apv.set_auto_approve(True)
    try:
        assert "click" not in apv.LOW_RISK
        assert "type" not in apv.LOW_RISK
        with pytest.raises(apv.Denied):      # 자동 승인이 켜져도 클릭은 대기 후 타임아웃
            apv.request("click", {"x": 1, "y": 1})
    finally:
        apv.set_auto_approve(False)


def test_deny_all_releases_waiters(apv, monkeypatch):
    """비상 정지가 대기 중인 행동을 모두 풀어줘야 한다."""
    import threading
    monkeypatch.setattr("screen.perform", lambda *a, **k: "ok")
    monkeypatch.setattr(apv, "TIMEOUT", 10)
    result = []

    def ask():
        try:
            apv.request("click", {"x": 1, "y": 1})
            result.append("ran")
        except apv.Denied:
            result.append("denied")

    t = threading.Thread(target=ask, daemon=True)
    t.start()
    for _ in range(50):
        if apv.pending():
            break
        time.sleep(0.05)
    assert apv.deny_all("테스트") >= 1
    t.join(timeout=5)
    assert result == ["denied"]


def test_system_shortcuts_blocked(apv, monkeypatch):
    monkeypatch.setattr("screen.perform", lambda *a, **k: "ok")
    with pytest.raises(apv.Denied):
        apv.request("key", {"keys": ["win", "r"]})


# ── 화면 UI ────────────────────────────────────────────────────────
@pytest.mark.parametrize("needle, why", [
    ('id="att-screen"', "화면 캡처 버튼"),
    ('id="apv"',        "승인 대기 패널"),
    ('id="apv-stop"',   "비상 정지 버튼"),
    ("ev.type === 'approval'", "승인 이벤트 라우팅"),
])
def test_screen_ui_present(html, needle, why):
    assert needle in html, f"화면 기능 요소가 사라졌다: {why}"


def test_no_periodic_screen_capture_in_source():
    """주기적 자동 캡처는 의도적으로 만들지 않았다.

    화면에 잠깐 스쳐간 비밀번호까지 외부 API로 보내게 되기 때문이다.
    누군가 나중에 추가하면 이 테스트가 실패해 재검토를 강제한다.
    """
    src = (config.ROOT / "screen.py").read_text(encoding="utf-8")
    for bad in ("setInterval", "while True", "schedule.every", "Timer("):
        assert bad not in src, f"screen.py에 반복 캡처로 보이는 코드가 있다: {bad}"


# ── 협업 타임라인 (B5) ─────────────────────────────────────────────
@pytest.fixture
def trace(tmp_path, monkeypatch):
    """가짜 trace.jsonl 을 만들어 타임라인 계산만 검증한다."""
    import timeline
    monkeypatch.setattr(config, "LOGS", tmp_path)
    rows = [
        {"type": "phase", "ts": 100.0, "run": "r1", "name": "PLAN", "detail": ""},
        {"type": "phase", "ts": 102.0, "run": "r1", "name": "WRITE_TESTS"},
        {"type": "phase", "ts": 104.0, "run": "r1", "name": "IMPLEMENT"},
        {"type": "phase", "ts": 107.0, "run": "r1", "name": "REVIEW"},
        {"type": "message", "ts": 108.0, "run": "r1", "agent": "QA",
         "kind": "verdict", "text": "**반려 (major)** — 고쳐라"},
        {"type": "phase", "ts": 109.0, "run": "r1", "name": "IMPLEMENT"},
        {"type": "phase", "ts": 111.0, "run": "r1", "name": "REVIEW"},
        {"type": "message", "ts": 112.0, "run": "r1", "agent": "QA",
         "kind": "verdict", "text": "**통과** — 좋다"},
        {"type": "done", "ts": 113.0, "run": "r1", "ok": True, "score": 100},
        # 다른 실행의 줄 — 섞이면 안 된다
        {"type": "phase", "ts": 105.0, "run": "r2", "name": "PLAN"},
    ]
    (tmp_path / "trace.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return timeline


def test_timeline_only_includes_its_own_run(trace):
    tl = trace.build("r1")
    assert all(s["phase"] != "PLAN" or s["nth"] == 1 for s in tl["segments"])
    assert len([s for s in tl["segments"] if s["phase"] == "PLAN"]) == 1


def test_timeline_assigns_phases_to_owners(trace):
    tl = trace.build("r1")
    owners = {s["phase"]: s["agent"] for s in tl["segments"]}
    assert owners["PLAN"] == "PM"
    assert owners["WRITE_TESTS"] == "QA"
    assert owners["IMPLEMENT"] == "DEV"
    assert owners["REVIEW"] == "QA"


def test_timeline_numbers_repeated_phases(trace):
    """같은 단계가 반복되면 몇 번째인지 보여야 재작업이 눈에 보인다."""
    tl = trace.build("r1")
    impls = [s["nth"] for s in tl["segments"] if s["phase"] == "IMPLEMENT"]
    assert impls == [1, 2]


def test_timeline_marks_rework(trace):
    tl = trace.build("r1")
    kinds = [m["kind"] for m in tl["markers"]]
    assert "fail" in kinds and "pass" in kinds and "done" in kinds
    assert trace.summary("r1")["reworks"] == 1


def test_timeline_counts_handoffs(trace):
    tl = trace.build("r1")
    assert tl["handoffs"], "에이전트가 바뀌는 지점을 못 잡았다"
    assert all(h["from"] != h["to"] for h in tl["handoffs"])


def test_timeline_survives_truncated_last_line(trace, tmp_path):
    """로그를 쓰는 도중에 읽으면 마지막 줄이 잘릴 수 있다."""
    path = tmp_path / "trace.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '\n{"type": "pha',
                    encoding="utf-8")
    tl = trace.build("r1")
    assert tl["segments"], "잘린 줄 하나에 타임라인 전체가 무너졌다"


def test_timeline_empty_for_unknown_run(trace):
    assert trace.build("없는실행")["segments"] == []


# ── 예약 실행 (B6) ─────────────────────────────────────────────────
@pytest.fixture
def sched(tmp_path, monkeypatch):
    import scheduler
    monkeypatch.setattr(scheduler, "STORE", tmp_path / "schedules.json")
    monkeypatch.setattr(scheduler, "_items", {}, raising=False)
    return scheduler


def test_schedule_add_and_list(sched):
    it = sched.add("리포트 만들기", "09:30", [0, 2, 4])
    assert it["at"] == "09:30" and it["days"] == [0, 2, 4]
    assert len(sched.listing()) == 1


@pytest.mark.parametrize("bad", ["25:00", "9:70", "아침", "", "09-30"])
def test_schedule_rejects_bad_time(sched, bad):
    with pytest.raises(ValueError):
        sched.add("무언가", bad)


def test_schedule_rejects_empty_requirement(sched):
    with pytest.raises(ValueError):
        sched.add("   ", "09:00")


def test_schedule_due_respects_day_and_time(sched):
    from datetime import datetime
    it = sched.add("주중 작업", "09:00", [0])          # 월요일만
    mon = datetime(2026, 9, 7, 9, 0)                   # 월
    tue = datetime(2026, 9, 8, 9, 0)                   # 화
    assert sched._due(it, mon)
    assert not sched._due(it, tue)
    assert not sched._due(it, datetime(2026, 9, 7, 9, 1))


def test_schedule_does_not_fire_twice_in_same_minute(sched):
    from datetime import datetime
    it = sched.add("한 번만", "09:00")
    now = datetime(2026, 9, 7, 9, 0)
    assert sched._due(it, now)
    fired = []
    sched.configure(lambda r: fired.append(r) or "slug-1")
    sched._fire(it, now)
    assert not sched._due(it, now), "같은 분에 두 번 발화한다"
    assert fired == ["한 번만"]


def test_schedule_records_skip_reason(sched):
    from datetime import datetime
    it = sched.add("실패할 것", "09:00")

    def boom(_):
        raise RuntimeError("API 키가 없어 예약을 실행하지 않았습니다")

    sched.configure(boom)
    sched._fire(it, datetime(2026, 9, 7, 9, 0))
    assert "건너뜀" in it["last_note"] and "키" in it["last_note"]


def test_schedule_disabled_never_due(sched):
    from datetime import datetime
    it = sched.add("꺼진 것", "09:00", enabled=False)
    assert not sched._due(it, datetime(2026, 9, 7, 9, 0))


def test_schedules_are_gitignored():
    ignore = (config.ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "schedules.json" in ignore


@pytest.mark.parametrize("needle, why", [
    ('id="tl-modal"',  "타임라인 다이얼로그"),
    ('id="tl-open"',   "타임라인 열기 버튼"),
    ('id="sch-modal"', "예약 다이얼로그"),
    ('id="sch-open"',  "예약 열기 버튼"),
])
def test_timeline_and_schedule_ui_present(html, needle, why):
    assert needle in html, f"요소가 사라졌다: {why}"
