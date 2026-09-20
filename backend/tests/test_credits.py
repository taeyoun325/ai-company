"""사용량 · 크레딧 · 원가 (지시서 §14 §15 §16 §17).

## 이 파일이 지키려는 것

1. **단가가 검증되어 있다.** DAY 11 에 공식 문서와 대조했다. 검증 안 된
   단가로 계산한 마진은 근거가 아니라 추측이고, 그 위에 요금제를 정하면
   장사가 산수가 아니라 소원이 된다.
2. **잔액이 실제로 줄고 실제로 막는다.** 0 이 된 다음에 막는 것은 막는
   게 아니다.
3. **§17 이 계산으로 성립한다.** "원가는 판매가의 50% 이하"를 숫자로 본다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config, usage                                   # noqa: E402
from app.agents import roles                                     # noqa: E402
from app.usage import credits                                    # noqa: E402


@pytest.fixture(autouse=True)
def _wallet(tmp_path, monkeypatch):
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    credits.reset()
    usage.bind("test-credits")
    yield
    usage.drop("test-credits")
    credits.reset()


# ── 단가 (§14) ─────────────────────────────────────────────────────
def test_prices_are_verified():
    """DAY 11 이전에는 verified=false 였다. 검증 안 된 단가로 계산한
    원가는 근거가 아니라 추측이다."""
    assert config.PRICES_VERIFIED is True
    assert config.PRICES_VERIFIED_ON, "언제 대조했는지가 없으면 언제 다시 볼지 모른다"


def test_every_employee_model_is_priced():
    for e in roles.EMPLOYEES.values():
        assert config.is_priced(e.model), f"{e.id} 의 모델 {e.model} 단가가 없다"


def test_unknown_model_is_priced_as_the_most_expensive():
    """모르는 모델을 0 으로 두면 예산 상한이 그 모델에는 안 걸린다.
    모르면 비싸게 잡는 편이 안전하다."""
    unknown = config.price_of("듣도보도못한모델", 1_000_000, 1_000_000)
    cheapest = config.price_of("gpt-5-mini", 1_000_000, 1_000_000)
    assert unknown > cheapest > 0


def test_cache_read_is_cheaper_than_plain_input():
    """캐시 읽기를 보통 입력처럼 계산하면 원가를 실제보다 크게 잡는다.
    안전한 쪽으로 틀린 숫자도 틀린 숫자다 — §17 판단이 어긋난다."""
    plain = config.price_of("claude-opus-5", 1_000_000, 0)
    cached = config.price_of("claude-opus-5", 0, 0, cached_tokens=1_000_000)
    assert 0 < cached < plain
    assert cached == pytest.approx(plain * 0.1)


def test_cache_write_is_more_expensive_than_plain_input():
    plain = config.price_of("claude-opus-5", 1_000_000, 0)
    written = config.price_of("claude-opus-5", 0, 0, cache_written=1_000_000)
    assert written == pytest.approx(plain * 1.25)


def test_opus_5_price_matches_the_official_table():
    """공식 단가: 입력 $5 / 출력 $25 per MTok (DAY 11 대조)."""
    assert config.PRICES["claude-opus-5"] == (5.00, 25.00)


def test_usage_records_credits_alongside_cost():
    usage.record("developer", "claude-opus-5", 1_000_000, 0)
    row = usage.agents_of()["developer"]
    assert row["cost"] == pytest.approx(5.0)
    assert row["credits"] == pytest.approx(5.0 / config.CREDIT_USD)


# ── 지갑 (§15) ─────────────────────────────────────────────────────
def test_new_wallet_gets_its_plan_credits():
    w = credits.wallet("someone")
    assert w.plan == "free"
    assert w.balance == credits.plan("free")["credits"]


def test_charge_reduces_balance():
    before = credits.balance()
    credits.charge("local", 0.10)          # $0.10 = 10 크레딧
    assert credits.balance() == pytest.approx(before - 10.0)


def test_charge_can_go_negative():
    """0 에서 멈추면 얼마나 초과했는지 기록이 사라진다."""
    credits.charge("local", 1000.0)
    assert credits.balance() < 0


def test_reserve_blocks_before_spending():
    """잔액이 0 이 된 다음에 막으면 이미 쓴 것이다."""
    credits.charge("local", credits.credits_to_usd(credits.balance()))
    with pytest.raises(credits.InsufficientCredits):
        credits.reserve("local", 1.0)


def test_reserve_passes_when_affordable():
    credits.reserve("local", 0.01)          # 예외가 나면 실패


def test_top_up_increases_balance():
    before = credits.balance()
    credits.top_up("local", 500)
    assert credits.balance() == pytest.approx(before + 500)


def test_top_up_rejects_non_positive():
    with pytest.raises(ValueError):
        credits.top_up("local", 0)


def test_plan_change_adds_credits_without_wiping_spend():
    """요금제를 오가며 크레딧을 무한히 받는 길을 막는다.
    이미 쓴 것은 쓴 것이다."""
    credits.charge("local", 0.50)           # 50 크레딧 사용
    spent_before = credits.wallet("local").spent
    credits.set_plan("local", "pro")
    w = credits.wallet("local")
    assert w.spent == pytest.approx(spent_before), "쓴 기록이 지워졌다"
    assert w.granted == pytest.approx(
        credits.plan("free")["credits"] + credits.plan("pro")["credits"])


def test_unknown_plan_is_rejected():
    with pytest.raises(ValueError):
        credits.set_plan("local", "없는요금제")


def test_wallet_survives_a_restart(tmp_path, monkeypatch):
    """프로세스가 죽었다고 크레딧이 되살아나면 그건 무료 요금제다."""
    credits.charge("local", 0.30)
    spent = credits.wallet("local").spent
    credits.reset()                          # 메모리를 비운다 = 재기동
    assert credits.wallet("local").spent == pytest.approx(spent)


# ── 요금제와 원가 (§16 §17) ────────────────────────────────────────
def test_every_plan_can_afford_one_developer_call():
    """개발자 호출 한 번의 최악 비용보다 상한이 작으면, 그 요금제는
    첫 구현 단계에서 항상 멈춘다. 시작조차 못 하는 요금제는 요금제가 아니다."""
    from app.agents import employee
    worst = employee.worst_case_cost("developer")
    for name, p in config.PLANS.items():
        assert p["max_project_cost"] >= worst, (
            f"{name} 요금제의 상한 ${p['max_project_cost']} 가 "
            f"개발자 한 번(${worst:.2f})보다 작다")


def test_paid_plans_meet_the_cost_ratio():
    """§17 — 원가는 판매가의 50% 이하. 구호가 아니라 계산이다."""
    r = credits.margin_report()
    assert r["all_paid_plans_ok"], [
        (p["plan"], p["cost_ratio"]) for p in r["plans"] if not p["ok"]]


def test_margin_report_does_not_call_the_free_plan_ok():
    """무료 요금제는 판매가가 0 이라 비율이 정의되지 않는다.
    '통과'로 적으면 거짓말이 된다."""
    free = next(p for p in credits.margin_report()["plans"] if p["plan"] == "free")
    assert free["ok"] is False
    assert free["cost_ratio"] is None
    assert free["note"]


def test_margin_report_carries_the_verification_flag():
    """검증 안 된 단가로 계산한 마진은 근거가 아니라 추측이다.
    그 사실이 보고서에 같이 실려야 한다."""
    assert "prices_verified" in credits.margin_report()


def test_free_plan_max_loss_is_stated():
    r = credits.margin_report()
    assert r["free_plan_max_loss_usd"] > 0, "무료 요금제의 최대 손실이 0 일 수 없다"


def test_credit_is_worth_what_the_file_says():
    assert credits.credits_to_usd(100) == pytest.approx(100 * config.CREDIT_USD)
    assert credits.usd_to_credits(1.0) == pytest.approx(1.0 / config.CREDIT_USD)


def test_status_exposes_what_the_screen_needs():
    st = credits.status()
    for field in ("balance", "plan", "plan_label", "credit_usd", "balance_usd",
                  "max_concurrent", "max_project_cost", "prices_verified"):
        assert field in st, f"{field} 가 없으면 화면이 잔액을 설명할 수 없다"
