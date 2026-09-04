"""자가 회귀 테스트 — 개선 루프가 매 회차 끝에 돌린다.

여기 있는 것들은 '고쳐도 되는 동작'이 아니라 '깨지면 안 되는 불변식'이다.
특히 신뢰 경계와 비밀키 격리는 한 번 무너지면 나머지 검증이 전부 무의미해진다.

    python -m pytest tests_selftest.py -q
"""
import os
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
