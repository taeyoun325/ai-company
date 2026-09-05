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
