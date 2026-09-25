"""프로젝트별 권한 조정 (DAY 25).

## 이 파일이 지키려는 것

1. **조정이 실제로 걸린다.** 작가에게 src/ 쓰기를 주면 작가가 src/ 에 쓸
   수 있어야 하고, 그 프로젝트에서만이어야 한다.
2. **바닥은 누구도 못 푼다.** 검증자 외의 tests/ 쓰기, 검증자의 산출물
   쓰기, 검증자의 읽기 축소, 전략가의 쓰기.
3. **위험은 확인 없이 켜지지 않는다.** 구현자의 tests/ 읽기.
4. **API 가 같은 규칙을 쓴다.** 실행 중에는 못 바꾼다.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config                                         # noqa: E402
from app.agents import permissions, roles                       # noqa: E402
from app.database import store                                   # noqa: E402
from app.tools import project_fs as pfs                          # noqa: E402
from app.usage import credits                                    # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    credits.reset()
    yield
    pfs.release()
    credits.reset()


def _project(overrides=None, ack=False) -> str:
    slug = store.new_project("권한 실험")
    store.save_meta(slug, {"status": "stopped"})
    if overrides is not None:
        clean, risks = permissions.validate(overrides, acknowledge_risk=ack)
        store.save_meta(slug, {"permissions": {"overrides": clean, "risks": risks}})
    pfs.use(slug)
    return slug


# ── 기본값은 그대로 ─────────────────────────────────────────────────
def test_without_overrides_the_employee_table_rules():
    _project()
    with pytest.raises(pfs.Denied):
        pfs.write("src/a.py", "x = 1\n", "writer")
    with pytest.raises(pfs.Denied):
        pfs.read("tests/test_a.py", "developer")


# ── 조정이 걸린다 ───────────────────────────────────────────────────
def test_granting_a_write_area_lets_the_employee_write_there():
    _project({"writer": {"writes": ["docs", "src"]}})
    pfs.write("src/notes.py", "# 작가가 씀\n", "writer")
    assert "src/notes.py" in pfs.listdir("SYSTEM")


def test_overrides_are_per_project():
    _project({"writer": {"writes": ["docs", "src"]}})
    _project()                                  # 다른 프로젝트
    with pytest.raises(pfs.Denied):
        pfs.write("src/notes.py", "x\n", "writer")


def test_revoking_a_read_area_hides_it():
    _project({"developer": {"reads": ["src"]}})
    pfs.write("design/screen.md", "# 화면\n", "SYSTEM")
    assert "design/screen.md" not in pfs.snapshot("developer")


def test_write_implies_read():
    """쓸 수 있는 곳을 못 읽으면 전문을 다시 쓰라는 요구가 곧 지우라는 것이 된다."""
    only_design = _project({"designer": {"reads": ["design"]}})
    _, reads = permissions.effective(only_design, "designer")
    assert "docs" not in reads
    slug = _project({"designer": {"writes": ["design", "docs"], "reads": ["design"]}})
    _, reads = permissions.effective(slug, "designer")
    assert "docs" in reads


# ── 바닥 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("overrides", [
    {"developer": {"writes": ["src", "tests"]}},
    {"writer": {"writes": ["tests"]}},
    {"analyst": {"writes": ["tests", "src"]}},
    {"analyst": {"reads": ["tests", "src"]}},
    {"strategist": {"writes": ["docs"]}},
    {"developer": {"writes": ["secrets"]}},
    {"nobody": {"reads": ["src"]}},
    {"developer": {"writes": "src"}},
])
def test_the_floor_cannot_be_lowered(overrides):
    with pytest.raises(permissions.PolicyError):
        permissions.validate(overrides, acknowledge_risk=True)


def test_hand_edited_meta_still_cannot_let_an_implementer_write_tests():
    """검사를 건너뛰고 메타 파일을 손으로 고쳐도 판정 기준은 안전해야 한다."""
    slug = _project()
    store.save_meta(slug, {"permissions": {"overrides": {
        "developer": {"writes": ["src", "tests"]}}}})
    with pytest.raises(pfs.Denied):
        pfs.write("tests/test_x.py", "def test_x(): pass\n", "developer")


# ── 위험 ────────────────────────────────────────────────────────────
def test_letting_an_implementer_read_tests_needs_acknowledgement():
    with pytest.raises(permissions.RiskNotAcknowledged):
        permissions.validate({"developer": {"reads": ["src", "tests"]}})
    clean, risks = permissions.validate(
        {"developer": {"reads": ["src", "tests"]}}, acknowledge_risk=True)
    assert risks == [permissions.RISK_TESTS_VISIBLE]


def test_acknowledged_risk_actually_shows_tests_to_the_developer():
    _project({"developer": {"reads": ["src", "docs", "design", "tests"]}}, ack=True)
    pfs.write("tests/test_calc.py", "def test_a(): pass\n", roles.VERIFIER)
    assert "tests/test_calc.py" in pfs.snapshot("developer")


def test_table_marks_locked_and_risky_cells():
    rows = {r["id"]: r for r in permissions.table(None)}
    assert "tests" in rows["developer"]["locked"]["writes"]
    assert "tests" in rows["developer"]["risky"]["reads"]
    assert set(rows["analyst"]["locked"]["reads"]) == set(roles.AREAS)
    assert rows["strategist"]["locked"]["writes"] == list(roles.AREAS)


# ── API ─────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_api_round_trip(client):
    slug = _project()
    r = client.put(f"/api/projects/{slug}/permissions",
                   json={"overrides": {"writer": {"writes": ["docs", "src"]}}})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["table"] if x["id"] == "writer")
    assert "src" in row["effective"]["writes"] and row["overridden"]
    assert client.get(f"/api/projects/{slug}/permissions").json()["overrides"]


def test_api_rejects_the_floor_with_400_and_unacknowledged_risk_with_409(client):
    slug = _project()
    r = client.put(f"/api/projects/{slug}/permissions",
                   json={"overrides": {"developer": {"writes": ["tests"]}}})
    assert r.status_code == 400
    r = client.put(f"/api/projects/{slug}/permissions",
                   json={"overrides": {"developer": {"reads": ["src", "tests"]}}})
    assert r.status_code == 409
    r = client.put(f"/api/projects/{slug}/permissions",
                   json={"overrides": {"developer": {"reads": ["src", "tests"]}},
                         "acknowledge_risk": True})
    assert r.status_code == 200
    assert r.json()["risks"] == ["tests_visible"]


def test_api_refuses_changes_while_running(client, monkeypatch):
    from app import orchestrator
    slug = _project()
    monkeypatch.setattr(orchestrator, "is_running", lambda s=None: True)
    r = client.put(f"/api/projects/{slug}/permissions",
                   json={"overrides": {"writer": {"writes": ["docs", "src"]}}})
    assert r.status_code == 409


def test_start_run_validates_gates_and_permissions_before_spending(client):
    r = client.post("/api/runs", json={"requirement": "x", "gates": ["later"]})
    assert r.status_code == 400
    r = client.post("/api/runs", json={
        "requirement": "x",
        "permissions": {"developer": {"writes": ["tests"]}}})
    assert r.status_code == 400
    assert not store.list_projects(), "거절된 요청이 프로젝트를 만들었다"
