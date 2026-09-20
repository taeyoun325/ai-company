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

from app import config

_lock = threading.RLock()

WALLET_FILE = config.ROOT / ".credits.json"


class InsufficientCredits(RuntimeError):
    """잔액이 모자란다. 시작 전에 막는다."""

    def __init__(self, needed: float, balance: float):
        super().__init__(
            f"크레딧이 부족합니다 — 이 작업의 최대 예상치 {needed:.1f} 크레딧, "
            f"잔액 {balance:.1f} 크레딧")
        self.needed = needed
        self.balance = balance


@dataclass
class Wallet:
    owner: str = "local"
    plan: str = "free"
    granted: float = 0.0        # 요금제로 받은 누적 크레딧
    spent: float = 0.0          # 실제로 쓴 크레딧
    topped_up: float = 0.0      # 추가 구매분
    renewed_at: float = field(default_factory=time.time)

    @property
    def balance(self) -> float:
        return round(self.granted + self.topped_up - self.spent, 4)

    def to_dict(self) -> dict:
        return {"owner": self.owner, "plan": self.plan, "granted": self.granted,
                "spent": self.spent, "topped_up": self.topped_up,
                "renewed_at": self.renewed_at}


_wallets: dict[str, Wallet] = {}


# ── 요금제 (§16) ────────────────────────────────────────────────────
def plans() -> dict:
    return dict(config.PLANS)


def plan(name: str) -> dict:
    return config.PLANS.get(name) or config.PLANS.get("free") or {
        "label": name, "price_usd": 0, "credits": 0,
        "max_concurrent": 1, "max_project_cost": 0.5}


# ── 지갑 ────────────────────────────────────────────────────────────
def wallet(owner: str = "local") -> Wallet:
    with _lock:
        w = _wallets.get(owner)
        if w is None:
            _load()
            w = _wallets.get(owner)
        if w is None:
            w = Wallet(owner=owner)
            w.granted = float(plan(w.plan).get("credits", 0))
            _wallets[owner] = w
            _save()
        return w


def set_plan(owner: str, name: str) -> Wallet:
    """요금제를 바꾸면 그 달치 크레딧을 새로 준다.

    바뀐 요금제의 크레딧을 **더해주지** 않고 새로 세팅하지도 않는 이유:
    이미 쓴 것은 쓴 것이다. 남은 잔액은 그대로 두고 새 요금제의 몫만
    더한다. 요금제를 오가며 크레딧을 무한히 받는 길을 막는다.
    """
    if name not in config.PLANS:
        raise ValueError(f"없는 요금제: {name}")
    with _lock:
        w = wallet(owner)
        w.plan = name
        w.granted += float(plan(name).get("credits", 0))
        w.renewed_at = time.time()
        _save()
        return w


def top_up(owner: str, credits: float) -> Wallet:
    if credits <= 0:
        raise ValueError("0 이하를 충전할 수 없습니다")
    with _lock:
        w = wallet(owner)
        w.topped_up += credits
        _save()
        return w


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
    need = usd_to_credits(usd)
    have = balance(owner)
    if need > have:
        raise InsufficientCredits(need, have)


def charge(owner: str, usd: float) -> float:
    """실제로 쓴 만큼 깎는다. 남은 잔액을 돌려준다.

    잔액보다 많이 썼으면 **음수로 둔다.** 0 에서 멈추면 얼마나 초과했는지
    기록이 사라지고, 다음 달에 그만큼 덜 받아야 한다는 사실도 사라진다.
    """
    with _lock:
        w = wallet(owner)
        w.spent += usd_to_credits(usd)
        _save()
        return w.balance


def refund(owner: str, credits: float) -> float:
    with _lock:
        w = wallet(owner)
        w.spent = max(0.0, w.spent - credits)
        _save()
        return w.balance


def status(owner: str = "local") -> dict:
    w = wallet(owner)
    p = plan(w.plan)
    return {
        "owner": w.owner,
        "plan": w.plan,
        "plan_label": p.get("label", w.plan),
        "balance": w.balance,
        "granted": round(w.granted, 2),
        "spent": round(w.spent, 2),
        "topped_up": round(w.topped_up, 2),
        "credit_usd": config.CREDIT_USD,
        "balance_usd": round(credits_to_usd(w.balance), 4),
        "max_concurrent": p.get("max_concurrent", 1),
        "max_project_cost": p.get("max_project_cost", 0.5),
        # 단가가 검증되지 않았으면 이 숫자들은 근거가 아니라 추측이다.
        "prices_verified": config.PRICES_VERIFIED,
        "prices_verified_on": config.PRICES_VERIFIED_ON,
    }


# ── 원가 관리 (§17) ────────────────────────────────────────────────
MAX_COST_RATIO = 0.50        # 원가는 판매가의 50% 이하여야 한다


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
        price = float(p.get("price_usd", 0))
        worst_cost = credits_to_usd(float(p.get("credits", 0)))
        ratio = (worst_cost / price) if price > 0 else None
        rows.append({
            "plan": name,
            "label": p.get("label", name),
            "price_usd": price,
            "credits": p.get("credits", 0),
            "worst_cost_usd": round(worst_cost, 2),
            "cost_ratio": round(ratio, 3) if ratio is not None else None,
            # 무료 요금제는 판매가가 0 이라 비율이 정의되지 않는다.
            # '통과'로 적으면 거짓말이 되므로 따로 표시한다.
            "ok": (ratio is not None and ratio <= MAX_COST_RATIO),
            "note": ("무료 요금제 — 비율이 아니라 **한 달 최대 손실**로 본다"
                     if price == 0 else ""),
        })
    paid = [r for r in rows if r["price_usd"] > 0]
    return {
        "max_cost_ratio": MAX_COST_RATIO,
        "plans": rows,
        "all_paid_plans_ok": all(r["ok"] for r in paid) if paid else False,
        "free_plan_max_loss_usd": next(
            (r["worst_cost_usd"] for r in rows if r["price_usd"] == 0), 0.0),
        "prices_verified": config.PRICES_VERIFIED,
        "prices_verified_on": config.PRICES_VERIFIED_ON,
    }


# ── 영속화 ──────────────────────────────────────────────────────────
def _save() -> None:
    try:
        WALLET_FILE.write_text(
            json.dumps({k: v.to_dict() for k, v in _wallets.items()},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # 저장 실패가 실행을 막지는 않는다. 다만 메모리의 잔액은 살아 있다.
        pass


def _load() -> None:
    try:
        data = json.loads(WALLET_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for owner, row in data.items():
        if not isinstance(row, dict):
            continue
        _wallets[owner] = Wallet(
            owner=owner, plan=row.get("plan", "free"),
            granted=float(row.get("granted", 0)),
            spent=float(row.get("spent", 0)),
            topped_up=float(row.get("topped_up", 0)),
            renewed_at=float(row.get("renewed_at", time.time())))


def reset() -> None:
    """테스트용. 메모리의 지갑을 비운다."""
    with _lock:
        _wallets.clear()
