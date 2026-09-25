"""크레딧 지갑과 요금제 (지시서 §15 · §16 · §17).

## 왜 크레딧인가

사용자에게 "$0.0347 를 썼습니다"라고 말하면, 그 숫자가 무엇에 쓰인
건지도 얼마가 남았는지도 감이 안 온다. 크레딧은 **우리 원가를 고정
배율로 환산한 눈금**이다 — 1 크레딧 = `config.CREDIT_USD` 달러어치 원가.

## 왜 배수가 아니라 원가로 차감하나

`pricing.json` 의 `credits` 배수는 "비싼 모델은 크레딧을 더 먹는다"를
**설명**하기 위한 것이다. 실제 차감을 그 배수로만 하면, 입력이 긴 작업과
출력이 긴 작업의 원가 차이가 통째로 사라진다. 배수는 화면에, 차감은
원가에.

## 왜 호출 *전에* 검사하나

잔액이 0 이 된 다음에 막으면 이미 쓴 것이다. 예산 상한(§18)과 같은
이유로, 다음 호출의 **최악 비용**을 미리 빼서 모자라면 시작하지 않는다.

## 이 파일이 저장소는 아니다

지금은 프로세스 메모리 + 디스크 파일이다. DAY 12 에 프로젝트 저장과
같은 자리로 옮긴다. 계정·결제는 이 제품의 범위 밖이고, 여기서는
**잔액이 실제로 줄고 실제로 막는가**만 성립시킨다.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

from app import config, lang
from app.usage import wallet_store

_lock = threading.RLock()

WALLET_FILE = config.data_dir() / ".credits.json"


class InsufficientCredits(RuntimeError):
    """잔액이 모자란다. 시작 전에 막는다."""

    def __init__(self, needed: float, balance: float):
        from app import lang
        super().__init__(lang.t("credits.short", needed=f"{needed:.1f}",
                                balance=f"{balance:.1f}"))
        self.needed = needed
        self.balance = balance


class DailyCostExceeded(RuntimeError):
    """오늘(UTC) 이미 쓴 실제 원가가 `config.MAX_DAILY_COST` 를 넘는다.

    요금제 상한(`_spend_guard`/`_guard` 의 `max_project_cost`)과는 별개다 —
    이건 프로젝트 하나가 아니라 **하루 전체**를 막는 안전장치다.
    """

    def __init__(self, projected: float, limit: float):
        from app import lang
        super().__init__(lang.t("cost.dailyExceeded", limit=f"{limit:.2f}",
                                projected=f"{projected:.2f}"))
        self.projected = projected
        self.limit = limit


class UserCostExceeded(RuntimeError):
    """이 사용자가 평생 쓴 실제 원가가 `config.MAX_USER_COST` 를 넘는다.

    크레딧 잔액이나 요금제와 무관하다 — 충전을 계속하면 크레딧은 늘 있지만,
    한 계정이 낼 수 있는 돈에는 그래도 바닥이 있어야 사고가 안 커진다.
    """

    def __init__(self, projected: float, limit: float):
        from app import lang
        super().__init__(lang.t("cost.userExceeded", limit=f"{limit:.2f}",
                                projected=f"{projected:.2f}"))
        self.projected = projected
        self.limit = limit


@dataclass
class Wallet:
    owner: str = "local"
    plan: str = "free"
    granted: float = 0.0        # 요금제로 받은 누적 크레딧
    spent: float = 0.0          # 실제로 쓴 크레딧
    topped_up: float = 0.0      # 추가 구매분
    byok_usd: float = 0.0       # 고객이 **자기 키로** 쓴 금액 (우리 청구 아님)
    renewed_at: float = field(default_factory=time.time)

    @property
    def balance(self) -> float:
        return round(self.granted + self.topped_up - self.spent, 4)

    def to_dict(self) -> dict:
        return {"owner": self.owner, "plan": self.plan, "granted": self.granted,
                "spent": self.spent, "topped_up": self.topped_up,
                "byok_usd": self.byok_usd, "renewed_at": self.renewed_at}


# ── 요금제 (§16) ────────────────────────────────────────────────────
def plans() -> dict:
    """**팔 수 있는** 요금제만. 숨긴 것(로컬 기본)은 빼고 내보낸다 —
    고를 수 없는 것을 요금제 화면에 놓으면 그건 요금제가 아니라 혼란이다.

    `_` 로 시작하는 항목도 뺀다. 그건 우리끼리 적어둔 근거이고(예: "결제
    없이 실제 키를 태우면 우리 돈이 나간다"), 고객이 읽을 문장이 아니다.
    고객에게 보일 한 줄은 `blurb` 에 따로 있다.
    """
    return {n: localized(p) for n, p in config.PLANS.items()
            if not p.get("hidden")}


def localized(row: dict) -> dict:
    """요금제 한 줄을 **이 요청의 언어로** 고른다 (DAY 22).

    이름과 설명은 서버가 가진 값이라 화면이 번역할 수 없다. 화면에
    `plan.starter` 같은 표를 또 두면 값이 두 곳에 살게 되고, 요금제를
    하나 추가할 때 두 곳을 고쳐야 한다. 서버는 이미 언어를 알고 있으니
    (`Accept-Language` → app/lang.py) 여기서 고른다.

    `_` 로 시작하는 항목은 뺀다. 그건 우리끼리 적어둔 근거이고
    (예: "결제 없이 실제 키를 태우면 우리 돈이 나간다") 고객이 읽을
    문장이 아니다.
    """
    from app import lang
    code = lang.current()
    out = {}
    for key, value in row.items():
        if key.startswith("_") or key.endswith(("_en", "_ja")):
            continue
        out[key] = row.get(f"{key}_{code}", value) if code != "ko" else value
    return out


def all_plans() -> dict:
    return dict(config.PLANS)


def default_plan() -> str:
    """새 지갑의 기본 요금제.

    SaaS 에서는 `none` — **무료 요금제가 없다.** 계정을 만든 직후에는
    아무것도 시작할 수 없고, 요금제를 골라야 한다. Mock 을 기본으로 주면
    없앤 무료 요금제를 이름만 바꿔 되살리는 것이다.

    로컬에서는 `local` — 거기서 돌리는 사람은 고객이 아니라 자기 키를
    꽂은 운영자 자신이고, 그 사람을 요금제로 막으면 요금제가 제품을 막는다.
    """
    from app import deploy
    if deploy.is_saas():
        return "none"
    return "local" if "local" in config.PLANS else "none"


def topups() -> dict:
    """충전 묶음 (DAY 19). 크레딧당 단가는 구독보다 **항상 비싸다** —
    싸지면 구독할 이유가 사라지고 무거운 사용자만 충전으로 남는다."""
    return {n: localized(t) for n, t in config.TOPUPS.items()}


def source_of(plan_name: str) -> str:
    """이 요금제가 **누구의 키로** 도는가. 값은 app/tenant.py 가 해석한다.

    여기서 기본값을 `platform` 으로 두는 이유: 기존 요금제 정의에는 이
    항목이 없었고, 없으면 지금까지의 동작(운영자 키)이 맞다. 다만 **모르는
    값**은 `tenant.source_of()` 가 mock 으로 떨어뜨린다 — 오타 하나가
    우리 키를 태우는 쪽으로 기울면 안 된다."""
    return str(plan(plan_name).get("source", "platform"))


def charges_credits(plan_name: str) -> bool:
    """크레딧을 깎는 요금제인가. 우리 키로 나간 비용만 깎는다."""
    return source_of(plan_name) == "platform"


def plan(name: str) -> dict:
    return config.PLANS.get(name) or config.PLANS.get("free") or {
        "label": name, "price_usd": 0, "credits": 0,
        "max_concurrent": 1, "max_project_cost": 0.5}


# ── 지갑 ────────────────────────────────────────────────────────────
#
# 지갑은 **파일이 아니라 SQLite** 에 있다(DAY 22 · usage/wallet_store.py).
# 차감이 읽고-고치고-쓰는 세 단계였을 때는, 두 실행이 동시에 끝나면 나중
# 것이 앞의 차감을 덮어써서 돈이 조용히 복구됐다. 이제 한 줄의 UPDATE 다.
def wallet(owner: str = "local") -> Wallet:
    row = wallet_store.get(owner)
    if row is None:
        # 옛 파일이 있으면 한 번 옮겨보고 다시 찾는다.
        wallet_store.migrate_from(WALLET_FILE)
        row = wallet_store.get(owner)
    if row is None:
        name = default_plan()
        row = wallet_store.create(owner, name,
                                  float(plan(name).get("credits", 0)))
    return Wallet(
        owner=owner, plan=row.get("plan", default_plan()),
        granted=float(row.get("granted", 0)), spent=float(row.get("spent", 0)),
        topped_up=float(row.get("topped_up", 0)),
        byok_usd=float(row.get("byok_usd", 0)),
        renewed_at=float(row.get("renewed_at", 0)))


def set_plan(owner: str, name: str) -> Wallet:
    """요금제를 바꾼다 — 올리면 **차이만** 더 주고, 내리면 아무것도 안 준다.

    한 기간에 받는 크레딧은 그동안 고른 요금제 중 가장 큰 것의 몫까지다
    (`wallet_store.add_plan`). DAY 22 까지는 새 요금제를 고를 때마다 그 몫을
    통째로 더해서, 요금제를 바꿀 때마다 잔액이 올랐다. 이미 쓴 것은 쓴
    것이다 — 잔액을 새로 세팅하지 않는다.
    """
    if name not in config.PLANS:
        raise ValueError(lang.t("plan.unknown", name=name))
    if config.PLANS[name].get("hidden"):
        # 숨긴 요금제로 **바꾸는** 길을 열어두면, 로컬 기본값(크레딧 10만)이
        # SaaS 에서 한 번의 요청으로 얻어진다.
        raise ValueError(lang.t("plan.notSelectable", name=name))
    wallet(owner)                       # 없으면 만든다
    allowance = {k: float(v.get("credits", 0) or 0)
                 for k, v in config.PLANS.items()}
    wallet_store.add_plan(owner, name, allowance)
    return wallet(owner)


def top_up(owner: str, credits: float) -> Wallet:
    if credits <= 0:
        raise ValueError(lang.t("plan.badTopup"))
    wallet(owner)
    wallet_store.add_topup(owner, credits)
    return wallet(owner)


def balance(owner: str = "local") -> float:
    return wallet(owner).balance


def usd_to_credits(usd: float) -> float:
    return usd / config.CREDIT_USD if config.CREDIT_USD else 0.0


def credits_to_usd(credits: float) -> float:
    return credits * config.CREDIT_USD


def reserve(owner: str, usd: float) -> None:
    """이 작업의 최악 원가만큼 잔액이 있는지 **시작 전에** 본다.

    실제로 깎지는 않는다. 깎아두고 나중에 돌려주면, 실행이 죽었을 때
    돌려줄 사람이 없다. 대신 `charge()` 가 실제 사용량으로 깎는다.
    """
    w = wallet(owner)
    # 우리 키로 나가는 비용이 아니면 깎을 것도 막을 것도 없다 (DAY 19).
    # 무료(Mock)는 원가가 0 이고, BYOK 는 고객이 자기 키로 직접 낸다.
    # 여기서 거르지 않으면, 크레딧 0 인 두 요금제가 **시작조차 못 한다.**
    if not charges_credits(w.plan):
        return
    need = usd_to_credits(usd)
    have = balance(owner)
    if need > have:
        raise InsufficientCredits(need, have)


def charge(owner: str, usd: float) -> float:
    """실제로 쓴 만큼 깎는다. 남은 잔액을 돌려준다.

    잔액보다 많이 썼으면 **음수로 둔다.** 0 에서 멈추면 얼마나 초과했는지
    기록이 사라지고, 다음 달에 그만큼 덜 받아야 한다는 사실도 사라진다.
    """
    w = wallet(owner)
    # 일일 상한은 청구 방식과 무관하게 **실제로 나간 돈**을 본다 — 크레딧
    # 이든 BYOK 든, 우리가 감당해야 할 API 호출이 일어난 건 같다.
    if usd:
        wallet_store.add_daily_cost(owner, usd)
    if not charges_credits(w.plan):
        # 고객 키로 나간 돈은 **기록만** 한다. 청구는 제공자가 고객에게
        # 직접 한다. 기록까지 버리면 고객은 자기가 얼마를 썼는지 우리
        # 화면에서 볼 수 없고, 그러면 비용 상한도 설명할 수 없다.
        wallet_store.add_byok_usd(owner, usd)
        return wallet(owner).balance
    # **읽지 않고 더한다.** 읽고-고치고-쓰면 두 실행이 동시에 끝났을 때
    # 나중 것이 앞의 차감을 덮어쓰고, 돈이 조용히 복구된다.
    wallet_store.add_spent(owner, usd_to_credits(usd))
    return wallet(owner).balance


def daily_cost_usd(owner: str) -> float:
    """오늘(UTC) 이미 쓴 실제 원가(달러)."""
    return wallet_store.daily_cost(owner)


def lifetime_cost_usd(owner: str) -> float:
    """이 사용자가 평생 낸 실제 원가(달러). 청구 방식과 무관하다.

    플랫폼 청구분은 `spent`(크레딧)를 달러로 환산한 값이 곧 원가이고
    (크레딧 = 원가 / CREDIT_USD 로 만들어지므로), BYOK 청구분은
    `byok_usd` 에 이미 달러로 쌓여 있다. 둘을 더하면 청구 방식과 무관한
    "이 계정 때문에 실제로 나간 돈" 전체가 된다.
    """
    w = wallet(owner)
    return credits_to_usd(w.spent) + w.byok_usd


def check_global_caps(owner: str, about_to_spend_usd: float) -> None:
    """일일·평생 누적 상한(§18 의 마지막 방벽). 요금제 상한과 별개로 늘 본다.

    프로젝트 비용 상한(`max_project_cost`)은 프로젝트 **하나**를 막는다.
    이건 그 위에 있는 두 번째 벽이다 — 여러 프로젝트를 연달아 돌려
    하루치를, 또는 계정 하나가 평생 낼 수 있는 돈을 넘기는 사고를 막는다.
    한도를 0 으로 두면(운영자가 끈 것으로 본다) 검사하지 않는다.
    """
    if config.MAX_DAILY_COST > 0:
        projected = daily_cost_usd(owner) + about_to_spend_usd
        if projected > config.MAX_DAILY_COST:
            raise DailyCostExceeded(projected, config.MAX_DAILY_COST)
    if config.MAX_USER_COST > 0:
        projected = lifetime_cost_usd(owner) + about_to_spend_usd
        if projected > config.MAX_USER_COST:
            raise UserCostExceeded(projected, config.MAX_USER_COST)


def refund(owner: str, credits: float) -> float:
    wallet(owner)
    wallet_store.refund(owner, credits)
    return wallet(owner).balance


def status(owner: str = "local") -> dict:
    w = wallet(owner)
    p = localized(plan(w.plan))
    return {
        "owner": w.owner,
        "plan": w.plan,
        "plan_label": p.get("label", w.plan),
        "balance": w.balance,
        "granted": round(w.granted, 2),
        "spent": round(w.spent, 2),
        "topped_up": round(w.topped_up, 2),
        # BYOK 요금제의 고객은 잔액이 아니라 **자기 카드에서 나간 금액**을
        # 봐야 한다. 크레딧만 보여주면 0 으로 고정된 숫자만 남는다.
        "byok_usd": round(w.byok_usd, 4),
        "source": source_of(w.plan),
        "charges_credits": charges_credits(w.plan),
        "credit_usd": config.CREDIT_USD,
        "balance_usd": round(credits_to_usd(w.balance), 4),
        "max_concurrent": p.get("max_concurrent", 1),
        "max_project_cost": p.get("max_project_cost", 0.5),
        # 프로젝트 상한 위의 두 번째 벽(§18). 0 이면 운영자가 끈 것 —
        # 화면에는 그 경우 None 을 보내 "상한이 없다"를 그대로 말한다.
        "daily_cost_usd": round(daily_cost_usd(w.owner), 4),
        "max_daily_cost": config.MAX_DAILY_COST if config.MAX_DAILY_COST > 0 else None,
        "lifetime_cost_usd": round(lifetime_cost_usd(w.owner), 4),
        "max_user_cost": config.MAX_USER_COST if config.MAX_USER_COST > 0 else None,
        # 단가가 검증되지 않았으면 이 숫자들은 근거가 아니라 추측이다.
        "prices_verified": config.PRICES_VERIFIED,
        "prices_verified_on": config.PRICES_VERIFIED_ON,
    }


# ── 원가 관리 (§17) ────────────────────────────────────────────────
# 원가는 판매가의 몇 % 이하여야 하는가 (§17).
#
# DAY 19 에 0.50 → 0.35 로 조였다. 0.50 을 지키던 숫자(프로 41.4% ·
# 비즈니스 45.5%)에는 **API 원가만** 들어 있었다. 여기에 결제 수수료
# (2.9% + $0.30) · 서버 · 환불 · 지원 · 모델 단가 인상 여지를 더하면
# 실질은 49% 근처로 벽에 붙는다. 벽에 붙은 값은 여유가 아니라 우연이다.
MAX_COST_RATIO = 0.35


def margin_report() -> dict:
    """요금제별로 §17 을 실제 숫자로 검사한다.

    "원가는 판매가의 50% 이하"는 구호가 아니라 계산이다. 요금제가 주는
    크레딧을 **전부 쓴** 경우가 우리 최대 원가이므로, 그 값과 구독료를
    비교한다.

    단가가 검증되지 않았으면 결과에 그 사실을 실어 보낸다 — 검증 안 된
    단가로 계산한 마진은 근거가 아니라 추측이다.
    """
    rows = []
    for name, p in config.PLANS.items():
        if p.get("hidden"):
            continue            # 팔지 않는 것은 마진을 따지지 않는다
        price = float(p.get("price_usd", 0))
        src = str(p.get("source", "platform"))
        # 우리 키로 나가지 않는 요금제의 **모델 원가는 0 이다.** BYOK 는
        # 고객이 직접 내고, Mock 은 아무 데도 가지 않는다. 크레딧을
        # 달러로 환산해 원가라고 부르면 있지도 않은 비용이 생긴다.
        worst_cost = (credits_to_usd(float(p.get("credits", 0)))
                      if src == "platform" else 0.0)
        ratio = (worst_cost / price) if price > 0 else None
        note = ""
        if price == 0:
            note = "무료 요금제 — 비율이 아니라 **한 달 최대 손실**로 본다"
        elif src == "byok":
            note = ("고객 키 — 모델 원가는 0 이다. 다만 **인프라·지원 원가는 "
                    "0 이 아니다**. 이 비율은 그것까지 말해주지 않는다")
        rows.append({
            "plan": name,
            "label": p.get("label", name),
            "price_usd": price,
            "credits": p.get("credits", 0),
            "source": src,
            "worst_cost_usd": round(worst_cost, 2),
            "cost_ratio": round(ratio, 3) if ratio is not None else None,
            # 무료 요금제는 판매가가 0 이라 비율이 정의되지 않는다.
            # '통과'로 적으면 거짓말이 되므로 따로 표시한다.
            "ok": (ratio is not None and ratio <= MAX_COST_RATIO),
            "note": note,
        })
    paid = [r for r in rows if r["price_usd"] > 0]

    # 충전 묶음도 같은 자로 잰다. 여기가 새면 요금제를 아무리 맞춰도
    # 무거운 사용자가 전부 충전으로 빠지면서 마진이 통째로 무너진다.
    sub_rate = min((float(p.get("price_usd", 0)) / float(p.get("credits", 1))
                    for p in config.PLANS.values()
                    if float(p.get("price_usd", 0)) > 0
                    and float(p.get("credits", 0)) > 0), default=0.0)
    topups = []
    for name, t in config.TOPUPS.items():
        price = float(t.get("price_usd", 0))
        credits = float(t.get("credits", 0))
        cost = credits_to_usd(credits)
        rate = (price / credits) if credits else 0.0
        topups.append({
            "topup": name, "label": t.get("label", name),
            "price_usd": price, "credits": credits,
            "worst_cost_usd": round(cost, 2),
            "cost_ratio": round(cost / price, 3) if price else None,
            "usd_per_credit": round(rate, 5),
            "ok": bool(price and cost / price <= MAX_COST_RATIO),
            # 구독보다 싼 충전은 요금제를 스스로 무너뜨린다.
            "dearer_than_subscription": rate > sub_rate,
        })

    return {
        "max_cost_ratio": MAX_COST_RATIO,
        "plans": rows,
        "topups": topups,
        "cheapest_subscription_usd_per_credit": round(sub_rate, 5),
        "all_topups_ok": all(t["ok"] and t["dearer_than_subscription"]
                             for t in topups) if topups else False,
        "all_paid_plans_ok": all(r["ok"] for r in paid) if paid else False,
        # 무료 요금제는 없앴다(DAY 19). 0 이 아니라 **없다**는 사실을
        # 그대로 내보낸다 — 0 으로 적으면 "손실 없는 무료 요금제가 있다"로
        # 읽힌다.
        "has_free_plan": any(r["price_usd"] == 0 for r in rows),
        "free_plan_max_loss_usd": next(
            (r["worst_cost_usd"] for r in rows if r["price_usd"] == 0), 0.0),
        "prices_verified": config.PRICES_VERIFIED,
        "prices_verified_on": config.PRICES_VERIFIED_ON,
    }


# ── 옛 파일 ─────────────────────────────────────────────────────────
#
# `.credits.json` 은 DAY 22 이전의 저장 방식이다. 이제 읽기만 한다 —
# 처음 켤 때 한 번 SQLite 로 옮기고, 그 뒤로는 아무도 쓰지 않는다.
# 지우지는 않는다: 지우는 코드는 되돌릴 수 없고, 옮기다 무언가 틀렸을 때
# 원본이 있어야 한다.


def reset() -> None:
    """테스트용. 지갑을 비운다."""
    wallet_store.clear()
    wallet_store.reset_migration()
