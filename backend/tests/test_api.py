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
