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
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config, usage                                   # noqa: E402
from app.agents import roles                                     # noqa: E402
from app.usage import credits, wallet_store                      # noqa: E402


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
    """SaaS 에서 계정을 만든 직후에는 **아무 요금제도 없다.** 무료 요금제를
    없앴으므로 결제 전에는 아무것도 시작할 수 없다.

    로컬에서 돌리는 사람은 고객이 아니라 자기 키를 꽂은 운영자다. 그
    사람까지 요금제로 막으면 요금제가 제품을 막는다."""
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    assert credits.default_plan() == "none"
    monkeypatch.setenv("DEPLOY_MODE", "local")
    assert credits.default_plan() == "local"


def test_there_is_no_free_plan():
    """Mock 전용 무료는 우리 돈이 나가지는 않지만, 가입한 사람이 받는 것이
    '대본이 지어낸 산출물'이다. 그건 체험이 아니라 오해를 파는 것이다."""
    sellable = credits.plans()
    assert "free" not in sellable
    assert all(p["price_usd"] > 0 for p in sellable.values()), (
        "판매가 0 인 요금제가 있다 — 무료 요금제를 없앤 의미가 사라진다")
    assert credits.margin_report()["has_free_plan"] is False


def test_no_plan_cannot_be_chosen_either():
    assert "none" not in credits.plans()
    with pytest.raises(ValueError):
        credits.set_plan("someone", "none")


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


# ── 일일·평생 누적 상한(§18 의 두 번째 벽) ────────────────────────
def test_charge_adds_to_todays_cost_regardless_of_billing_method():
    """일일 상한은 청구 방식과 무관하게 **실제 원가**를 본다."""
    assert credits.daily_cost_usd("local") == 0.0
    credits.charge("local", 0.10)
    assert credits.daily_cost_usd("local") == pytest.approx(0.10)
    credits.charge("local", 0.05)
    assert credits.daily_cost_usd("local") == pytest.approx(0.15)


def test_daily_cost_resets_after_utc_midnight():
    """날짜가 바뀌면 어제 쓴 돈은 오늘의 상한과 무관하다."""
    credits.charge("local", 1.0)
    assert credits.daily_cost_usd("local") == pytest.approx(1.0)
    # 하루 전 자정으로 되돌려 "어제 쓴 것"처럼 만든다.
    yesterday = wallet_store._utc_midnight(time.time()) - 3600
    with wallet_store._lock, wallet_store.conn() as c:
        c.execute("UPDATE wallets SET daily_reset_at = ? WHERE owner = ?",
                  (yesterday, "local"))
    assert credits.daily_cost_usd("local") == 0.0
    credits.charge("local", 0.5)
    assert credits.daily_cost_usd("local") == pytest.approx(0.5), \
        "어제 쓴 금액이 새 날의 합계에 섞였다"


def test_lifetime_cost_counts_platform_and_byok_spend_together():
    assert credits.lifetime_cost_usd("local") == 0.0
    credits.charge("local", 0.20)                 # 플랫폼 청구 (크레딧 차감)
    wallet_store.add_byok_usd("local", 0.30)       # 고객 자기 키 (기록만)
    assert credits.lifetime_cost_usd("local") == pytest.approx(0.50)


def test_check_global_caps_passes_when_under_both_limits():
    credits.check_global_caps("local", 0.01)       # 예외가 나면 실패


def test_check_global_caps_blocks_when_daily_cap_would_be_exceeded(monkeypatch):
    monkeypatch.setattr(config, "MAX_DAILY_COST", 1.0)
    credits.charge("local", 0.90)
    with pytest.raises(credits.DailyCostExceeded):
        credits.check_global_caps("local", 0.20)


def test_check_global_caps_blocks_when_lifetime_cap_would_be_exceeded(monkeypatch):
    monkeypatch.setattr(config, "MAX_USER_COST", 1.0)
    credits.charge("local", 0.90)
    with pytest.raises(credits.UserCostExceeded):
        credits.check_global_caps("local", 0.20)


def test_check_global_caps_is_off_when_the_limit_is_zero(monkeypatch):
    """0 은 운영자가 끈 것으로 본다 — 검사 자체를 건너뛴다."""
    monkeypatch.setattr(config, "MAX_DAILY_COST", 0.0)
    monkeypatch.setattr(config, "MAX_USER_COST", 0.0)
    credits.charge("local", 10_000.0)
    credits.check_global_caps("local", 10_000.0)   # 예외가 나면 실패


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
    # 한 기간에 받는 것은 고른 요금제 중 가장 큰 몫까지다 (DAY 26).
    assert w.granted == pytest.approx(max(
        credits.plan(credits.default_plan())["credits"],
        credits.plan("pro")["credits"]))


def _fresh_saas_wallet(owner: str):
    """요금제를 아직 안 고른 SaaS 계정(`none`, 0 크레딧)에서 시작한다."""
    from app.usage import wallet_store
    wallet_store.create(owner, "none", 0.0)
    assert credits.wallet(owner).granted == 0


def test_switching_plans_does_not_keep_adding_credits():
    """사용자 신고 (DAY 26): 요금제를 바꿀 때마다 크레딧이 계속 올랐다.
    스타터 → 프로 → 비즈니스 → 스타터 → 프로 … 를 몇 번을 눌러도, 받는 것은
    가장 큰 요금제(비즈니스)의 몫까지다."""
    owner = "switcher"
    _fresh_saas_wallet(owner)
    top = credits.plan("business")["credits"]
    for _ in range(3):
        for name in ("starter", "pro", "business", "byok", "starter", "pro"):
            credits.set_plan(owner, name)
            assert credits.wallet(owner).granted <= top, name
    w = credits.wallet(owner)
    assert w.granted == pytest.approx(top)
    assert w.plan == "pro"


def test_upgrading_adds_only_the_difference():
    owner = "upgrader"
    _fresh_saas_wallet(owner)
    credits.set_plan(owner, "starter")
    assert credits.wallet(owner).granted == pytest.approx(
        credits.plan("starter")["credits"])
    credits.set_plan(owner, "pro")
    assert credits.wallet(owner).granted == pytest.approx(
        credits.plan("pro")["credits"]), "올리면 차이만 받아야 한다 (스타터 몫이 겹쳐 쌓였다)"


def test_downgrading_adds_nothing_and_keeps_the_balance():
    owner = "downgrader"
    _fresh_saas_wallet(owner)
    credits.set_plan(owner, "business")
    credits.charge(owner, 1.0)
    before = credits.wallet(owner).balance
    credits.set_plan(owner, "starter")
    after = credits.wallet(owner)
    assert after.balance == pytest.approx(before), "내렸는데 잔액이 바뀌었다"
    assert after.plan == "starter"


def test_unknown_plan_is_rejected():
    with pytest.raises(ValueError):
        credits.set_plan("local", "없는요금제")


def test_wallet_survives_a_restart():
    """프로세스가 죽었다고 크레딧이 되살아나면 그건 무료 요금제다.

    DAY 22 부터 지갑은 파일이 아니라 SQLite 에 있다. 연결을 닫는 것이
    프로세스가 죽는 것에 가깝다 — 메모리에 남은 사본이 없어진다."""
    from app.usage import wallet_store

    credits.charge("local", 0.30)
    spent = credits.wallet("local").spent
    assert spent > 0
    wallet_store.close()                     # 연결을 끊는다 = 재기동
    assert credits.wallet("local").spent == pytest.approx(spent)


def test_two_charges_do_not_overwrite_each_other():
    """읽고-고치고-쓰면 두 실행이 동시에 끝났을 때 나중 것이 앞의 차감을
    덮어쓴다. 돈이 조용히 복구되고, 아무도 눈치채지 못한다."""
    credits.set_plan("racer", "business")
    before = credits.balance("racer")
    for _ in range(10):
        credits.charge("racer", 0.10)        # 각 10 크레딧
    assert credits.balance("racer") == pytest.approx(before - 100.0)


def test_the_old_file_is_moved_in_once(tmp_path, monkeypatch):
    """옛 파일이 두 번 읽히면 잔액이 두 배가 된다."""
    import json

    from app.usage import wallet_store

    legacy = tmp_path / "credits.json"
    legacy.write_text(json.dumps({
        "old-user": {"plan": "pro", "granted": 900, "spent": 100,
                     "topped_up": 0, "byok_usd": 0, "renewed_at": 0},
    }), encoding="utf-8")
    monkeypatch.setattr(credits, "WALLET_FILE", legacy)
    credits.reset()

    assert credits.wallet("old-user").granted == 900
    assert credits.wallet("old-user").spent == 100

    wallet_store.reset_migration()           # 다시 읽으려 시도해도
    assert credits.wallet("old-user").granted == 900, "잔액이 두 배가 됐다"


def test_moving_the_old_file_does_not_delete_it(tmp_path, monkeypatch):
    """지우는 코드는 되돌릴 수 없다. 옮기다 틀렸을 때 원본이 있어야 한다."""
    import json

    legacy = tmp_path / "credits.json"
    legacy.write_text(json.dumps({"u": {"plan": "pro", "granted": 10}}),
                      encoding="utf-8")
    monkeypatch.setattr(credits, "WALLET_FILE", legacy)
    credits.reset()
    credits.wallet("u")
    assert legacy.exists()


# ── 요금제와 원가 (§16 §17) ────────────────────────────────────────
def test_every_plan_can_afford_one_developer_call():
    """개발자 호출 한 번의 최악 비용보다 상한이 작으면, 그 요금제는
    첫 구현 단계에서 항상 멈춘다. 시작조차 못 하는 요금제는 요금제가 아니다."""
    from app.agents import employee
    worst = employee.worst_case_cost("developer")
    # 팔지 않는 것(로컬 기본·요금제 미선택)은 뺀다. 요금제 미선택은 상한이
    # 0 인 것이 **정상**이다 — 그 상태에서는 아무것도 시작할 수 없다.
    for name, p in credits.plans().items():
        assert p["max_project_cost"] >= worst, (
            f"{name} 요금제의 상한 ${p['max_project_cost']} 가 "
            f"개발자 한 번(${worst:.2f})보다 작다")


def test_paid_plans_meet_the_cost_ratio():
    """§17 — 원가는 판매가의 정해진 비율 이하. 구호가 아니라 계산이다."""
    r = credits.margin_report()
    assert r["all_paid_plans_ok"], [
        (p["plan"], p["cost_ratio"]) for p in r["plans"] if not p["ok"]]


def test_margin_report_would_not_call_a_zero_price_plan_ok():
    """판매가 0 인 요금제는 비율이 정의되지 않는다. '통과'로 적으면
    거짓말이 된다. 지금은 그런 요금제가 없지만, 다시 생기면 이 규칙이
    살아 있어야 한다 — 검사 자체를 지우면 다음에 조용히 통과한다."""
    import copy
    saved = copy.deepcopy(config.PLANS)
    config.PLANS["gift"] = {"label": "선물", "price_usd": 0, "credits": 150,
                            "max_concurrent": 1, "max_project_cost": 1.5,
                            "source": "platform"}
    try:
        row = next(p for p in credits.margin_report()["plans"]
                   if p["plan"] == "gift")
        assert row["ok"] is False
        assert row["cost_ratio"] is None
        assert row["note"]
    finally:
        config.PLANS.clear()
        config.PLANS.update(saved)


def test_margin_report_carries_the_verification_flag():
    """검증 안 된 단가로 계산한 마진은 근거가 아니라 추측이다.
    그 사실이 보고서에 같이 실려야 한다."""
    assert "prices_verified" in credits.margin_report()


def test_every_sellable_plan_is_paid():
    """DAY 18 까지 무료 요금제는 월 150 크레딧($1.50)을 **우리 키로** 줬다.
    이메일 인증이 없는 상태에서 그건 스크립트 한 줄에 열린 지갑이다.
    DAY 19 에 Mock 전용으로 바꿨다가, 같은 날 아예 없앴다 — 결제해야만
    쓸 수 있다."""
    r = credits.margin_report()
    assert r["plans"], "팔 요금제가 하나도 없다"
    assert all(p["price_usd"] > 0 for p in r["plans"])
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


def test_plan_must_be_chosen_before_anything_starts(monkeypatch):
    """무료 요금제가 없으므로 계정을 만든 직후에는 아무것도 못 한다.
    Mock 으로 돌려주지 않는다 — 그건 없앤 무료 요금제를 이름만 바꿔
    되살리는 것이다."""
    from app import tenant
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    credits.reset()
    assert credits.wallet("newcomer").plan == "none"
    with pytest.raises(tenant.NoPlan):
        tenant.require_runnable("newcomer")


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


# ── 요금제 이름은 서버가 언어에 맞춰 보낸다 (DAY 22) ───────────────
def test_plan_labels_follow_the_request_language():
    """이름과 설명은 서버가 가진 값이라 화면이 번역할 수 없다. 화면에
    같은 표를 또 두면 값이 두 곳에 살게 되고, 요금제를 하나 추가할 때
    두 곳을 고쳐야 한다."""
    from app import lang
    with lang.bind("en"):
        assert credits.plans()["pro"]["label"] == "Pro"
    with lang.bind("ja"):
        assert credits.plans()["pro"]["label"] == "プロ"
    with lang.bind("ko"):
        assert credits.plans()["pro"]["label"] == "프로"


def test_language_variants_do_not_leak_to_the_screen():
    """`label_en` 같은 원본이 그대로 나가면 화면이 그걸 보여줄 수도 있고,
    무엇보다 한 요금제가 세 개의 이름을 가진 것처럼 보인다."""
    for row in credits.plans().values():
        assert not any(k.endswith(("_en", "_ja")) for k in row)
    for row in credits.topups().values():
        assert not any(k.endswith(("_en", "_ja")) for k in row)


def test_internal_notes_never_reach_the_screen():
    for row in credits.plans().values():
        assert not any(k.startswith("_") for k in row)


# ── 크레딧이 뭘 사주는지 (DAY 22 · docs/market.md 1순위) ───────────
def test_costs_are_not_called_measured_until_there_are_enough(tmp_path, monkeypatch):
    """없는 데이터를 그럴듯한 숫자로 채우는 것이 제일 나쁜 거짓말이다."""
    from app.database import index, store
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    index.close()

    r = index.project_costs()
    assert r["measured"] is False and r["samples"] == 0

    for i in range(index.MIN_SAMPLES):
        slug = store.new_project(f"실측 표본 {i}")
        store.save_meta(slug, {"status": "done", "cost": 1.0 + i, "mock": False})
        index.upsert(store.meta(slug))

    r = index.project_costs()
    assert r["measured"] is True
    assert r["samples"] == index.MIN_SAMPLES
    assert r["median_usd"] > 0


def test_mock_projects_are_not_counted(tmp_path, monkeypatch):
    """Mock 원가는 0 이다. 섞으면 '프로젝트 한 건에 0원'이 되고,
    그 숫자로 요금제를 고른 사람은 첫 달에 놀란다."""
    from app.database import index, store
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    index.close()

    for i in range(6):
        slug = store.new_project(f"대본 {i}")
        store.save_meta(slug, {"status": "done", "cost": 0.0, "mock": True})
        index.upsert(store.meta(slug))

    assert index.project_costs()["measured"] is False


def test_median_is_not_dragged_by_one_disaster(tmp_path, monkeypatch):
    """평균은 재작업 열 번짜리 사고 하나에 끌려간다. 사용자가 알고 싶은
    것은 '보통 얼마'와 '나쁠 때 얼마'다."""
    from app.database import index, store
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    index.close()

    for cost in (1.0, 1.0, 1.0, 1.0, 50.0):
        slug = store.new_project(f"비용 {cost}")
        store.save_meta(slug, {"status": "done", "cost": cost, "mock": False})
        index.upsert(store.meta(slug))

    r = index.project_costs()
    assert r["median_usd"] == 1.0, "중앙값이 사고에 끌려갔다"
    assert r["p90_usd"] > r["median_usd"], "나쁠 때가 보통보다 커야 한다"
