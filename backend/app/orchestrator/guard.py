"""비용 상한 검사 — AUTO 와 MANUAL 이 같은 규칙을 쓴다.

## 왜 따로 뺐나

`engine._spend_guard` 와 `manual._guard` 가 거의 같은 코드였다. 상한을
하나 더 넣을 때마다(§18) 두 곳을 고쳐야 했고, 하나만 고치면 그 쪽만
상한을 지키는 길이 생긴다. 검사 자체를 한 곳에 두면 그런 틈이 없다.

## 이 파일의 내력 (DAY 25)

같은 기능(일·평생 누적 상한)을 두 세션이 동시에 다른 설계로 만들었다.
하나는 `credits.check_global_caps` 로 커밋됐고(8ad568d), 이 파일은
존재하지 않는 `wallet_store.spent_today` 를 부르는 채로 커밋되지 않고
남았다. 커밋된 쪽을 진실로 두고, 이 파일에서 살릴 가치가 있던 두 가지만
옮겼다:

1. **검사를 한 곳에 모은다** — 위의 이유.
2. **아직 청구되지 않은 몫도 센다.** 실행은 끝날 때 한 번에 청구된다
   (`engine._run_bound` 의 finally). 그 사이에는 `daily_cost_usd` 에도
   잔액에도 이번 실행이 쓴 돈이 안 보인다 — 그래서 한 실행 안에서
   호출이 쌓이면 일일 상한과 잔액을 **실제로 넘긴 뒤에야** 안다.

## 동시에 도는 호출 (DAY 25 · 병렬 태스크)

태스크를 병렬로 돌리면 "지금 막 부르려는 호출" 이 하나가 아니다. 두
직원이 같은 순간에 "남은 예산 ≥ 내 최악 비용" 을 확인하고 둘 다 부르면
둘을 합친 만큼 넘친다. 그래서 **이미 나가 있는 호출의 최악 비용**
(`inflight`)을 함께 더한다. 예약을 거는 쪽은 `engine._Budget` 이다.
"""
from __future__ import annotations

from app import config, lang, usage
from app.usage import credits


class SpendLimit(RuntimeError):
    """예산 상한(라운드 · 프로젝트 · 일 · 평생 · 크레딧) 중 하나에 닿았다."""


def project_limit(owner: str) -> float:
    """요금제 상한과 전역 하드 상한 중 **작은 쪽**.

    전역 상한은 요금제를 잘못 적어도 사고가 나지 않게 하는 마지막
    방벽이므로, 요금제가 그것을 넘어설 수 있으면 방벽이 아니다.
    """
    return min(config.MAX_PROJECT_COST,
               float(credits.plan(credits.wallet(owner).plan)
                     .get("max_project_cost", config.MAX_PROJECT_COST)))


def check_spend(slug: str, owner: str, about_to_spend: float, *,
                rounds: int | None = None, unbilled: float = 0.0,
                inflight: float = 0.0,
                cost_key: str = "stop.cost") -> None:
    """호출 *전에* 검사한다. 사후 감지는 예산 상한이 아니라 예산 부고다.

    - `about_to_spend` — 이번 호출의 최악 비용.
    - `unbilled` — 이 실행(또는 MANUAL 지시)이 이미 썼지만 아직 지갑에
      청구되지 않은 돈. 일일·평생 상한과 잔액 검사에 더한다.
    - `inflight` — 동시에 나가 있는 다른 호출들의 최악 비용 합.
    - `cost_key` — 프로젝트 상한 문장. MANUAL 은 "지시를 멈춘다"는
      다른 문장을 쓴다(할 일이 다르다 — AUTO 는 실행이 멈춘다).
    """
    if rounds is not None and rounds > config.MAX_ROUNDS:
        raise SpendLimit(lang.t("stop.rounds", n=config.MAX_ROUNDS))

    ahead = about_to_spend + inflight
    projected = usage.total_cost(slug) + ahead
    limit = project_limit(owner)
    if projected > limit:
        raise SpendLimit(lang.t(cost_key, limit=limit,
                                projected=f"{projected:.2f}"))

    # 크레딧 — 상한은 사고를 막는 장치이고, 크레딧은 **사용자가 산 만큼**
    # 이라 둘은 다르다. 청구는 요금제가 우리 키일 때만 한다(BYOK·Mock 은
    # 크레딧을 깎지 않으므로 여기서 막을 이유도 없다).
    if credits.charges_credits(credits.wallet(owner).plan):
        need = credits.usd_to_credits(unbilled + ahead)
        have = credits.balance(owner)
        if need > have:
            raise SpendLimit(lang.t("stop.credits", left=f"{have:.1f}"))

    # 프로젝트 상한 위의 두 번째 벽(§18) — 일일·평생 누적 원가.
    try:
        credits.check_global_caps(owner, unbilled + ahead)
    except (credits.DailyCostExceeded, credits.UserCostExceeded) as e:
        raise SpendLimit(str(e)) from e
