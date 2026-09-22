"""프로젝트 1건의 실제 원가를 재고, 요금제의 크레딧 수를 검산한다.

    python scripts/measure_costs.py --runs 10          # 실제 키로 10건
    python scripts/measure_costs.py --runs 3 --mock    # 키 없이 배선 확인

## 왜 이 스크립트가 있나

`STATUS.md` 에 이렇게 적혀 있다: "**이 표의 분모를 아직 모른다.** 프로젝트
1건의 실제 원가를 한 번도 재본 적이 없다." 화면의 "월 N건"은 호출 20~40회
× $0.03~0.15 라는 **추정**에서 나온 숫자다.

키가 들어오는 날 할 일은 정해져 있다 — 10건을 돌려 중앙값·p90 을 뽑고
크레딧 수를 확정하는 것. 그 일을 그날 처음 설계하면, 하필 돈이 나가는
중에 스크립트를 쓰게 된다. 그래서 미리 만들어 두고 **Mock 으로 배선까지
확인해 둔다**(`--mock`). 그날은 `--runs 10` 한 줄이면 된다.

## Mock 으로 재면 숫자는 가짜다

`--mock` 이 확인해 주는 것은 "원가가 잡히고, 분포가 계산되고, 요금제와
대조된다"는 **배선**이지 금액이 아니다. Mock 의 단가는 대본용이다. 그래서
Mock 으로 돌린 결과에는 줄마다 그렇게 적는다 — 숫자만 옮겨 적는 사고를
막는 유일한 방법은 숫자 옆에 적어두는 것이다.

## 돈을 쓴다

`--mock` 없이 돌리면 프로젝트를 통째로 여러 번 돌린다. 기본값이 3건인
이유이고, 시작 전에 예상 상한을 보여주고 한 번 묻는다.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# 윈도우 기본 콘솔은 cp949 다. 여기서 쓰는 ✓ 하나에 스크립트가 통째로
# 죽는다(UnicodeEncodeError) — 하필 **키를 꽂은 날 제일 먼저 돌리는 것**이
# 그렇게 된다. 출력만 utf-8 로 돌려놓는다. 실패해도 넘어간다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass



from app import config                                  # noqa: E402
from app.orchestrator import engine                     # noqa: E402
from app.providers import registry                      # noqa: E402
from app.usage import credits                           # noqa: E402

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

# 재는 데 쓰는 요구사항. 서로 다른 모양이어야 한 종류의 일만 재지 않는다.
REQUIREMENTS = [
    "사칙연산 계산기 모듈과 사용법 문서를 만들어주세요",
    "CSV 파일을 읽어 열별 합계를 내는 도구를 만들어주세요",
    "문자열을 슬러그로 바꾸는 함수와 테스트를 만들어주세요",
    "간단한 할 일 목록 저장소(메모리)와 사용법 문서를 만들어주세요",
    "온도 단위를 변환하는 모듈과 결과 화면 명세를 만들어주세요",
]


def line(mark: str, color: str, text: str) -> None:
    print(f"{color}{mark}{OFF} {text}")


def percentile(values: list[float], q: float) -> float:
    """중앙값·p90. 표본이 적을 때 라이브러리마다 다른 답을 내므로 직접 센다."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def measure(n: int, mock: bool) -> list[dict]:
    """프로젝트를 n 건 돌리고 건당 원가를 모은다."""
    from app import usage

    out: list[dict] = []
    for i in range(n):
        requirement = REQUIREMENTS[i % len(REQUIREMENTS)]
        started = time.time()
        slug = engine.start(requirement)
        while engine.is_running(slug):
            time.sleep(0.2)
        totals = usage.totals(slug)
        out.append({
            "slug": slug,
            "requirement": requirement,
            "usd": float(totals.get("cost", 0.0)),
            "calls": int(totals.get("calls", 0)),
            "seconds": round(time.time() - started, 1),
        })
        tag = f"{DIM}(mock){OFF}" if mock else ""
        line("·", DIM, f"{i + 1}/{n}  ${out[-1]['usd']:.4f}  "
                       f"{out[-1]['calls']} calls  {out[-1]['seconds']}s {tag}")
    return out


def report(rows: list[dict], mock: bool) -> int:
    usd = [r["usd"] for r in rows]
    calls = [r["calls"] for r in rows]
    if not usd:
        line("✗", RED, "잰 것이 없습니다.")
        return 1

    median = percentile(usd, 0.5)
    p90 = percentile(usd, 0.9)
    warn = f"  {YELLOW}← Mock 이므로 금액은 가짜다{OFF}" if mock else ""

    print()
    line("=", DIM, f"표본 {len(usd)}건")
    line(" ", OFF, f"중앙값  ${median:.4f}{warn}")
    line(" ", OFF, f"p90     ${p90:.4f}")
    line(" ", OFF, f"최대    ${max(usd):.4f}")
    line(" ", OFF, f"호출 수 중앙값 {int(percentile([float(c) for c in calls], 0.5))}회")

    # 요금제와 대조한다. 여기가 이 스크립트의 목적이다 — 숫자를 뽑는 것이
    # 아니라 **크레딧 수가 그 숫자 위에 서 있는지** 보는 것.
    print()
    line("=", DIM, "요금제 검산 (p90 기준 · 월 몇 건인가)")
    for name, plan in config.PLANS.items():
        if plan.get("hidden"):
            continue
        price = float(plan.get("price_usd", 0))
        granted = float(plan.get("credits", 0))
        if not price or not granted:
            continue
        runs = granted * config.CREDIT_USD / p90 if p90 else 0
        ratio = (granted * config.CREDIT_USD) / price if price else 0
        ok = ratio <= credits.MAX_COST_RATIO
        line("✓" if ok else "✗", GREEN if ok else RED,
             f"{name:<10} ${price:>3.0f} / {granted:>5.0f}cr  "
             f"→ 월 {runs:>5.1f}건  원가비율 {ratio:.1%}"
             f" (상한 {credits.MAX_COST_RATIO:.0%})")

    print()
    if mock:
        line("!", YELLOW,
             "Mock 으로 잰 값이다. 배선은 확인됐지만 **금액은 아무 의미가 "
             "없다.** 키를 꽂고 --runs 10 으로 다시 재라.")
        return 0
    line("→", DIM,
         "이 숫자를 pricing.json 의 크레딧 수에 반영하고, STATUS.md 의 "
         "'가격은 실측 위에 있지 않다' 를 고쳐라.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="프로젝트 1건의 실제 원가 측정")
    ap.add_argument("--runs", type=int, default=3, help="돌릴 프로젝트 수")
    ap.add_argument("--mock", action="store_true",
                    help="Mock 으로 배선만 확인한다 (돈을 쓰지 않는다)")
    ap.add_argument("--yes", action="store_true", help="확인 질문을 건너뛴다")
    args = ap.parse_args()

    if args.mock:
        import os
        os.environ["PROVIDER_MODE"] = "mock"
        registry.reset()
    else:
        st = registry.status()
        if st.get("all_mock"):
            line("✗", RED,
                 "키가 없어 전부 Mock 입니다. 재도 의미가 없습니다 — "
                 "키를 넣거나 --mock 을 붙이세요.")
            return 1
        # 돈이 나가는 쪽은 한 번 묻는다. 예상 상한은 요금제 검사에 쓰는
        # '최악 원가'와 같은 자를 쓴다.
        worst = max(r["worst_cost_usd"] for r in credits.margin_report()["plans"])
        line("!", YELLOW,
             f"실제 모델로 {args.runs}건을 돌립니다. 건당 최악 ${worst:.2f} "
             f"기준 최대 ${worst * args.runs:.2f} 까지 나갈 수 있습니다.")
        if not args.yes and input("계속할까요? [y/N] ").strip().lower() != "y":
            return 1

    rows = measure(args.runs, args.mock)
    return report(rows, args.mock)


if __name__ == "__main__":
    raise SystemExit(main())
