"""API 표면 테스트.

키 없이 서버가 뜨고, 화면이 필요한 것을 내려주는지만 본다.
에이전트 동작은 여기서 보지 않는다 — 그건 DAY 5 이후의 일이다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from fastapi.testclient import TestClient                       # noqa: E402

from app import main                                            # noqa: E402
from app.providers import registry                              # noqa: E402


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.reset()
    yield
    registry.reset()


def test_server_boots_without_any_key(client):
    """키가 없어도 떠야 한다. 안 그러면 키를 맨 마지막에 넣는 방침 자체가
    성립하지 않는다."""
    assert client.get("/api/state").status_code == 200


def test_state_reports_provider_status(client):
    st = client.get("/api/state").json()
    assert "providers" in st, "화면이 Mock 여부를 알 방법이 없다"
    assert "mode" in st["providers"]


def test_providers_endpoint_shape(client):
    body = client.get("/api/providers").json()
    assert body["mode"] in registry.MODES
    assert isinstance(body["providers"], list) and body["providers"]
    row = body["providers"][0]
    for field in ("name", "model", "key", "mock", "fallbacks"):
        assert field in row, f"{field} 가 빠지면 화면이 상태를 못 그린다"


def test_providers_marked_mock_when_no_key(client, monkeypatch):
    from app.providers.claude import ClaudeProvider
    monkeypatch.setenv("PROVIDER_MODE", "auto")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: False)
    registry.reset()
    body = client.get("/api/providers").json()
    assert body["all_mock"] is True
    assert body["any_real"] is False


def test_index_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and r.content


def test_stream_route_is_registered():
    """SSE 경로가 살아 있는지 확인한다 (§13).

    연결을 실제로 열지 않는다. `/api/stream` 은 끝나지 않는 스트림이라
    TestClient 로 열면 닫을 때 서버 제너레이터가 큐에서 대기 중이라
    테스트가 그대로 멈춘다. 실제로 겪었다.
    """
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/stream" in paths


def test_settings_exposes_model_catalog(client):
    """설정 화면이 고를 수 있는 모델 목록을 내려받지 못하면,
    사용자는 모델 ID 를 손으로 타이핑해야 한다."""
    body = client.get("/api/settings").json()
    assert set(body["catalog"]) >= {"claude", "gemini", "openai"}
    for name, row in body["catalog"].items():
        assert row["default"], f"{name} 기본 모델이 비어 있다"


def test_state_reports_cross_check(client):
    """구현자와 검증자가 같은 회사면 교차검증 전제가 사라진다 (§8).
    화면이 그 사실을 말할 수 있어야 한다."""
    assert "cross_check" in client.get("/api/state").json()["providers"]


def test_model_change_rejects_model_without_price(client):
    """단가를 모르는 모델은 비용이 0 으로 잡힌다. 0 은 공짜가 아니라
    모른다는 뜻이고, 예산 상한이 그 모델에는 걸리지 않는다."""
    r = client.post("/api/settings/model",
                    json={"provider": "claude", "model": "단가없는모델"})
    assert r.status_code == 400


def test_model_change_rejects_unknown_provider(client):
    r = client.post("/api/settings/model",
                    json={"provider": "없는회사", "model": "claude-opus-5"})
    assert r.status_code == 400


def test_model_change_applies(client):
    from app import config
    before = config.default_model("claude")
    try:
        r = client.post("/api/settings/model",
                        json={"provider": "claude", "model": "claude-sonnet-5"})
        assert r.status_code == 200
        assert config.default_model("claude") == "claude-sonnet-5"
    finally:
        config.CATALOG["claude"]["default"] = before
        registry.reset()


def test_manual_flow_over_http(client, tmp_path, monkeypatch):
    """MANUAL 이 HTTP 로도 같은 규칙을 지키는지 (§11)."""
    from app import config
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    registry.reset()

    slug = client.post("/api/manual", json={"requirement": "계산기"}).json()["slug"]
    r = client.post(f"/api/manual/{slug}/instruct",
                    json={"employee": "developer", "message": "사칙연산을 구현해주세요"})
    assert r.status_code == 200
    assert r.json()["files"] == ["src/calc.py"]

    st = client.get(f"/api/manual/{slug}").json()
    assert "src/calc.py" in st["files"]
    assert st["busy"] is None


def test_manual_rejects_unknown_employee(client, tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = client.post("/api/manual", json={"requirement": "계산기"}).json()["slug"]
    r = client.post(f"/api/manual/{slug}/instruct",
                    json={"employee": "없는직원", "message": "안녕"})
    assert r.status_code == 404


def test_employees_endpoint_lists_five(client):
    body = client.get("/api/employees").json()
    assert len(body["employees"]) == 5
    assert body["planner"] and body["verifier"]


def test_employee_detail_exposes_its_instructions(client):
    """무엇을 시켰는지 CEO 가 볼 수 없으면, 결과가 왜 그런지도 알 수 없다."""
    row = client.get("/api/employees/analyst").json()
    assert row["system"].strip()
    assert row["worst_case_usd"] >= 0


def test_unknown_employee_is_404(client):
    assert client.get("/api/employees/없는사람").status_code == 404


def test_employee_model_change_rejects_unpriced_model(client):
    r = client.post("/api/employees/developer/model", json={"model": "모르는모델"})
    assert r.status_code == 400


def test_state_carries_employees(client):
    st = client.get("/api/state").json()
    assert len(st["employees"]) == 5
    assert "mock" in st["employees"][0], "Mock 여부가 화면까지 전달되어야 한다"


def test_keys_endpoint_accepts_openai(client):
    r = client.post("/api/settings/keys", json={"openai": ""})
    assert r.status_code == 200
    assert "openai" in r.json()["keys"]
