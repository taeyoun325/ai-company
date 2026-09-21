"""고객 키와 테넌트 자세 (DAY 19 · app/byok.py · app/tenant.py).

## 이 파일이 지키려는 것

요금제가 셋일 때는 돈만 달랐다. BYOK 를 붙이면 **호출 경로가** 요금제마다
달라지고, 그 분기가 틀리면 셋 중 하나가 조용히 일어난다:

1. 결제하지 않은 사용자가 **우리 키**를 태운다.
2. BYOK 고객의 모델 요금을 **우리가** 낸다.
3. 고객 A 의 키로 고객 B 의 호출이 나간다.

셋 다 청구서나 사고 보고서로만 드러난다. 화면에는 아무 일도 안 난 것처럼
보인다. 그래서 여기서 잡는다.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import byok, secrets_broker, tenant                    # noqa: E402
from app.providers import registry                              # noqa: E402
from app.usage import credits                                   # noqa: E402

A = "a@example.com"
B = "b@example.com"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BYOK_SECRET", "test-kek")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    byok.reset()
    credits.reset()
    # 운영자 키가 있는 상태로 둔다. "없어서 안 샌 것"은 증명이 아니다.
    monkeypatch.setitem(secrets_broker._store, "anthropic", "sk-operator-XXXXXXXX")
    monkeypatch.setitem(secrets_broker._store, "gemini", "gem-operator-XXXXXXXX")
    yield
    byok.reset()
    credits.reset()


def _give_keys(owner: str, tag: str = "a") -> None:
    byok.set_key(owner, "anthropic", f"sk-ant-{tag * 12}")
    byok.set_key(owner, "gemini", f"AIza-{tag * 12}")


# ── 저장 ────────────────────────────────────────────────────────────
def test_stored_file_has_no_plaintext_key():
    """백업·스냅샷·디스크 교체가 전부 유출 경로가 된다."""
    _give_keys(A)
    raw = byok.store_path().read_text(encoding="utf-8")
    assert "sk-ant-aaaaaaaaaaaa" not in raw
    assert A not in raw, "파일 안에 이메일이 그대로 적혀 있다"
    assert json.loads(raw), "저장은 됐어야 한다"


def test_key_cannot_be_moved_to_another_tenant():
    """암호문을 옮겨 붙이는 것으로 남의 키를 쓰지 못한다."""
    _give_keys(A)
    blob = json.loads(byok.store_path().read_text(encoding="utf-8"))
    stolen = next(iter(blob.values()))["anthropic"]
    blob[byok._oid(B)] = {"anthropic": stolen}
    byok.store_path().write_text(json.dumps(blob), encoding="utf-8")
    byok.reset()
    assert byok.keys_of(B) == {}, "다른 테넌트 자리에서 복호화가 됐다"
    assert byok.keys_of(A), "원래 주인은 계속 읽을 수 있어야 한다"


def test_unreadable_key_is_treated_as_missing(monkeypatch):
    """KEK 가 바뀌면 복호화는 실패한다. 그때 예외가 화면까지 올라가면
    사용자는 키를 **다시 넣을 수도 없다.**"""
    _give_keys(A)
    monkeypatch.setenv("BYOK_SECRET", "다른-값")
    byok.reset()
    assert byok.keys_of(A) == {}
    assert byok.status(A)["ready"] is False


# ── 자세 ────────────────────────────────────────────────────────────
def test_byok_posture_never_falls_back_to_operator_keys():
    """여기서 새면, 할인 요금제를 판 자리에서 우리가 모델 값을 낸다."""
    credits.set_plan(A, "byok")
    byok.set_key(A, "anthropic", "sk-ant-mine-0123456789")
    with tenant.bind(A):
        assert secrets_broker.get("anthropic") == "sk-ant-mine-0123456789"
        # 고객이 넣지 않은 제공자는 **없는 것**이다. 운영자 키로 넘어가지 않는다.
        assert secrets_broker.get("gemini") is None
    assert secrets_broker.get("anthropic") == "sk-operator-XXXXXXXX"


def test_unplanned_account_never_reaches_a_real_key(monkeypatch):
    """결제하지 않은 사용자가 우리 키를 태우는 경로를 여기서 끊는다.

    실행은 `require_runnable` 이 이미 거부한다. 키까지 끊는 것은 방어를
    겹치기 위해서다 — 게이트를 빠뜨린 경로가 하나라도 생기면 그 경로가
    곧 무료 이용권이 된다.
    """
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    credits.reset()
    assert credits.wallet(A).plan == "none"
    with pytest.raises(tenant.NoPlan):
        tenant.require_runnable(A)
    with tenant.bind(A):
        assert registry.mode() == "mock"
        assert secrets_broker.get("anthropic") is None


def test_byok_posture_does_not_fall_back_to_mock():
    """Mock 으로 떨어지면 고객은 대본이 지어낸 글을 자기 AI 의 결과로 받는다."""
    credits.set_plan(A, "byok")
    _give_keys(A)
    with tenant.bind(A):
        assert registry.mode() == "real"


def test_paid_plan_uses_operator_keys():
    credits.set_plan(A, "pro")
    with tenant.bind(A):
        assert secrets_broker.get("anthropic") == "sk-operator-XXXXXXXX"


def test_one_tenants_key_does_not_leak_into_another():
    _give_keys(A, "a")
    _give_keys(B, "b")
    credits.set_plan(A, "byok")
    credits.set_plan(B, "byok")
    with tenant.bind(A):
        mine = secrets_broker.get("anthropic")
    with tenant.bind(B):
        theirs = secrets_broker.get("anthropic")
    assert mine != theirs
    assert byok.keys_of(A)["anthropic"] == mine


def test_run_is_refused_when_byok_keys_are_missing():
    """중간에 터지면 절반쯤 만들어진 프로젝트와 '왜 멈췄는지 모르겠는'
    화면이 남는다. 시작 전에 거부한다."""
    credits.set_plan(A, "byok")
    with pytest.raises(tenant.KeysMissing):
        tenant.require_runnable(A)
    _give_keys(A)
    tenant.require_runnable(A)                  # 예외가 나면 실패


def test_cross_check_needs_two_companies_worth_of_keys():
    """구현자와 검증자가 같은 회사면 교차검증(§8)이라는 전제가 사라진다.
    우리 키에 요구하는 기준을 고객 키에도 똑같이 요구한다."""
    byok.set_key(A, "anthropic", "sk-ant-only-0123456789")
    assert byok.ready(A) is False
    assert "gemini" in byok.missing(A)


# ── 새어나가지 않는가 ───────────────────────────────────────────────
def test_customer_key_is_scrubbed_from_messages():
    """남의 키가 우리 로그에 남으면, 사고는 우리 것이 아닌데 책임은
    우리 것이 된다."""
    credits.set_plan(A, "byok")
    _give_keys(A)
    key = byok.keys_of(A)["anthropic"]
    with tenant.bind(A):
        assert key not in secrets_broker.scrub(f"AuthenticationError: {key}")


def test_status_never_returns_the_raw_key():
    _give_keys(A)
    blob = json.dumps(byok.status(A), ensure_ascii=False)
    assert byok.keys_of(A)["anthropic"] not in blob
    assert "…" in blob, "마스크조차 없으면 사용자는 뭘 넣었는지 모른다"


def test_provider_client_is_cached_per_key(monkeypatch):
    """전역 클라이언트 하나를 물려쓰면, 먼저 온 요청이 만든 클라이언트로
    다음 테넌트의 호출이 나간다."""
    from app.providers import anthropic_client
    anthropic_client.reset_client()
    _give_keys(A, "a")
    _give_keys(B, "b")
    credits.set_plan(A, "byok")
    credits.set_plan(B, "byok")
    with tenant.bind(A):
        first = anthropic_client.client()
    with tenant.bind(B):
        second = anthropic_client.client()
    assert first is not second
    with tenant.bind(A):
        assert anthropic_client.client() is first, "키가 같으면 재사용해야 한다"
    anthropic_client.reset_client()
