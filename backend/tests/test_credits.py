"""사용량 · 크레딧 · 원가 (지시서 §14 §15 §16 §17).

## 이 파일이 지키려는 것

1. **단가가 검증되어 있다.** DAY 11 에 공식 문서와 대조했다. 검증 안 된
   단가로 계산한 마진은 근거가 아니라 추측이고, 그 위에 요금제를 정하면
   장사가 산수가 아니라 소원이 된다.
2. **잔액이 실제로 줄고 실제로 막는다.** 0 이 된 다음에 막는 것은 막는
   게 아니다.
3. **§17 이 계산으로 성립한다.** "원가는 판매가의 정해진 비율 이하"를
   숫자로 본다 (DAY 19 에 0.50 → 0.35).
4. **누구의 키로 도는지가 돈과 맞물려 있다** (DAY 19). 우리 키로 나간
   비용만 크레딧을 깎는다. BYOK 는 고객이 직접 내고, 무료는 Mock 이라
   아무 데도 가지 않는다. 이 셋이 어긋나면 청구서로만 드러난다.
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
    assert w.plan == credits.default_plan()
    assert w.balance == credits.plan(w.plan)["credits"]


def test_default_plan_depends_on_where_this_runs(monkeypatch):
    """로컬에서 돌리는 사람은 고객이 아니라 자기 키를 꽂은 운영자다.
    그 사람을 무료 요금제(Mock 전용)에 가두면 요금제가 제품을 막는다."""
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    assert credits.default_plan() == "free"
    monkeypatch.setenv("DEPLOY_MODE", "local")
    assert credits.default_plan() == "local"


def test_local_plan_cannot_be_chosen(monkeypatch):
    """숨긴 요금제로 바꾸는 길이 열려 있으면, 로컬 기본값(크레딧 10만)이
    SaaS 에서 요청 한 번으로 얻어진다."""
    assert "local" not in credits.plans(), "팔지 않는 것이 요금제 목록에 있다"
    with pytest.raises(ValueError):
        credits.set_plan("someone", "local")


def test_charge_reduces_balance():
    before = credits.balance()
    credits.charge("local", 0.10)          # $0.10 = 10 크레딧
    assert credits.balance() == pytest.approx(before - 10.0)


def test_charge_can_go_negative():
    """0 에서 멈추면 얼마나 초과했는지 기록이 사라진다."""
    credits.charge("local", 10_000.0)
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
        credits.plan(credits.default_plan())["credits"]
        + credits.plan("pro")["credits"])


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
    """§17 — 원가는 판매가의 정해진 비율 이하. 구호가 아니라 계산이다."""
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


def test_free_plan_costs_us_nothing_because_it_never_calls_a_model():
    """DAY 18 까지 무료 요금제는 월 150 크레딧($1.50)을 **우리 키로** 줬다.
    이메일 인증이 없는 상태에서 그건 스크립트 한 줄에 열린 지갑이다.
    DAY 19 에 Mock 전용으로 바꿨고, 그러면 최대 손실은 정확히 0 이다."""
    r = credits.margin_report()
    free = next(p for p in r["plans"] if p["plan"] == "free")
    assert free["source"] == "mock", "무료 요금제가 실제 모델을 부른다"
    assert free["credits"] == 0
    assert r["free_plan_max_loss_usd"] == 0


# ── 누구의 키로 도는가 (§16 · DAY 19) ──────────────────────────────
def test_byok_plan_does_not_spend_credits():
    """고객이 자기 키로 낸 돈을 우리가 또 크레딧으로 받으면 이중 청구다."""
    credits.set_plan("byok-user", "byok")
    before = credits.balance("byok-user")
    credits.charge("byok-user", 3.0)
    assert credits.balance("byok-user") == before
    assert credits.status("byok-user")["byok_usd"] == pytest.approx(3.0)


def test_byok_plan_starts_even_with_zero_credits():
    """크레딧 0 인 요금제가 잔액 검사에 걸려 **시작조차 못 하면**
    그건 요금제가 아니다."""
    credits.set_plan("byok-user", "byok")
    credits.reserve("byok-user", 5.0)            # 예외가 나면 실패


def test_free_plan_starts_even_with_zero_credits():
    credits.set_plan("free-user", "free")
    credits.reserve("free-user", 5.0)            # Mock 은 원가가 0 이다


def test_paid_plan_still_spends_credits():
    """면제가 새어나가 유료 요금제까지 공짜가 되면 아무도 모른다."""
    credits.set_plan("pro-user", "pro")
    before = credits.balance("pro-user")
    credits.charge("pro-user", 0.10)
    assert credits.balance("pro-user") == pytest.approx(before - 10.0)
    assert credits.status("pro-user")["byok_usd"] == 0


def test_unknown_source_is_not_treated_as_ours():
    """요금제 파일의 오타 하나가 **우리 키를 태우는 쪽**으로 기울면 안 된다."""
    from app import tenant
    monkey = dict(config.PLANS["pro"])
    monkey["source"] = "platfrom"                 # 오타
    config.PLANS["typo-plan"] = monkey
    try:
        assert tenant.source_of("typo-plan") == "mock"
    finally:
        config.PLANS.pop("typo-plan")


# ── 충전 (§16 · DAY 19) ────────────────────────────────────────────
def test_topups_are_dearer_per_credit_than_any_subscription():
    """충전이 구독보다 싸지면 구독할 이유가 사라지고, 가장 무거운
    사용자만 충전으로 남는다."""
    r = credits.margin_report()
    assert r["topups"], "충전 묶음이 하나도 없다"
    for t in r["topups"]:
        assert t["dearer_than_subscription"], (
            f"{t['topup']} 충전이 구독보다 싸다 "
            f"(${t['usd_per_credit']}/크레딧)")


def test_topups_meet_the_cost_ratio():
    r = credits.margin_report()
    assert r["all_topups_ok"], [(t["topup"], t["cost_ratio"])
                                for t in r["topups"] if not t["ok"]]


def test_credit_is_worth_what_the_file_says():
    assert credits.credits_to_usd(100) == pytest.approx(100 * config.CREDIT_USD)
    assert credits.usd_to_credits(1.0) == pytest.approx(1.0 / config.CREDIT_USD)


def test_status_exposes_what_the_screen_needs():
    st = credits.status()
    for field in ("balance", "plan", "plan_label", "credit_usd", "balance_usd",
                  "max_concurrent", "max_project_cost", "prices_verified"):
        assert field in st, f"{field} 가 없으면 화면이 잔액을 설명할 수 없다"
