"""로그인 횟수 제한이 믿는 주소 (DAY 27).

Cloud Run 앞에서 실제로 잰 X-Forwarded-For 모양으로 시험한다.
"""
from types import SimpleNamespace

import pytest

from app.api import auth

HOSTING = "66.249.64.0/19"


def _req(xff: str, client: str = "169.254.1.1"):
    return SimpleNamespace(headers={"x-forwarded-for": xff},
                           client=SimpleNamespace(host=client))


@pytest.fixture
def saas(monkeypatch):
    monkeypatch.setenv("DEPLOY_MODE", "saas")


def test_without_setting_keeps_old_behaviour(saas, monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    assert auth._client_ip(_req("6.6.6.6, 121.168.117.18")) == "6.6.6.6"


def test_forged_value_is_ignored_on_direct_path(saas, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", HOSTING)
    assert auth._client_ip(_req("6.6.6.6,121.168.117.18")) == "121.168.117.18"


def test_hosting_proxy_is_skipped(saas, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", HOSTING)
    assert auth._client_ip(_req("121.168.117.18,66.249.82.103")) == "121.168.117.18"


def test_bad_cidr_and_garbage_hosts_do_not_crash(saas, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "nonsense, " + HOSTING)
    assert auth._client_ip(_req("121.168.117.18, junk")) == "junk"


def test_proxy_ranges_can_come_from_a_file(saas, monkeypatch, tmp_path):
    """Hosting 은 여러 대역에서 접속한다(실측: 66.249.82.x · 192.178.14.x)."""
    f = tmp_path / "proxies.txt"
    f.write_text("# google services\n66.249.64.0/19\n192.178.0.0/15\n", encoding="utf-8")
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_FILE", str(f))
    auth._read_cidr_file.cache_clear()
    assert auth._client_ip(_req("121.168.117.18,192.178.14.2")) == "121.168.117.18"
    assert auth._client_ip(_req("121.168.117.18,66.249.82.40")) == "121.168.117.18"
    assert auth._client_ip(_req("6.6.6.6,121.168.117.18")) == "121.168.117.18"
