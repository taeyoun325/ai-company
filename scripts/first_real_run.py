"""최초 실물 호출 — 키를 꽂은 날 제일 먼저 돌리는 것.

    python scripts/first_real_run.py            # 제공자별 최소 호출 1번씩
    python scripts/first_real_run.py --company  # 실제 직원들로 작은 프로젝트 하나

## 왜 따로 스크립트인가

이 제품의 최대 리스크는 "실제 모델로 한 번도 돌려본 적이 없다"였다.
방침상 키가 맨 마지막에 들어오므로, 그 순간 확인해야 할 것이 정해져 있다:

  1. 키가 실제로 유효한가
  2. 어댑터가 실제 응답을 우리 모양으로 옮기는가 (§7)
  3. 사용량이 실제로 잡히는가 (§14)
  4. 스트리밍 조각이 실제로 흘러나오는가 (§13)

이걸 앱을 띄워서 눈으로 확인하면, 무엇이 틀렸는지 알아내는 데 시간이
걸린다. 여기서는 **실패가 어느 줄에서 났는지**가 바로 보인다.

## 돈을 쓴다

작은 호출이지만 공짜가 아니다. `max_tokens` 를 64 로 묶고, 요약 끝에
쓴 돈을 적는다. `--company` 는 프로젝트 하나를 통째로 돌리므로 훨씬
비싸다 — 기본값이 아닌 이유다.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config, secrets_broker, usage           # noqa: E402
from app.providers import registry                      # noqa: E402
from app.providers.base import GenerateRequest, ProviderError  # noqa: E402

SYSTEM = "당신은 점검용 조수입니다. 한 문장으로만 답하세요."
ASK = "연결 확인 중입니다. '연결됨'이라고만 답해 주세요."

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def line(mark: str, color: str, text: str) -> None:
    print(f"{color}{mark}{OFF} {text}")


def check_provider(name: str) -> bool:
    p = registry.get(name)
    if registry.is_mock(name):
        line("·", DIM, f"{name}: 키가 없어 Mock 입니다 — 건너뜁니다")
        return True

    # 1) 한 번 호출
    t0 = time.time()
    try:
        req = GenerateRequest.ask(SYSTEM, ASK, max_tokens=64, agent="SYSTEM")
        r = p.generate(req)
    except ProviderError as e:
        line("✗", RED, f"{name}: 호출 실패 — {type(e).__name__}: {e}")
        return False
    took = time.time() - t0

    if not r.text.strip():
        # 빈 응답을 성공으로 넘기면, 위에서 "모델이 할 말이 없었다"로 읽는다.
        line("✗", RED, f"{name}: 빈 응답을 돌려줬습니다 (stop={r.stop_reason})")
        return False

    line("✓", GREEN,
         f"{name}: {r.model} · {took:.1f}초 · "
         f"입력 {r.usage.input_tokens} / 출력 {r.usage.output_tokens} 토큰")
    print(f"   {DIM}{r.text.strip()[:100]}{OFF}")

    # 2) 사용량이 실제로 잡히는가 (§14)
    if r.usage.input_tokens == 0 and r.usage.output_tokens == 0:
        line("!", YELLOW,
             f"{name}: 응답은 왔는데 사용량이 0 입니다. 어댑터의 usage 해석이 "
             f"틀렸을 수 있습니다 — 이대로면 비용이 0 으로 잡혀 예산 상한이 "
             f"걸리지 않습니다.")

    # 3) 스트리밍 (§13)
    try:
        chunks = []
        for i, c in enumerate(p.stream(req)):
            chunks.append(c)
            if i > 200:
                break
        if "".join(chunks).strip():
            line("✓", GREEN, f"{name}: 스트리밍 {len(chunks)}조각")
        else:
            line("!", YELLOW, f"{name}: 스트리밍이 빈 글을 냈습니다")
    except ProviderError as e:
        line("!", YELLOW, f"{name}: 스트리밍 실패 — {type(e).__name__}: {e}")

    return True


def run_company() -> bool:
    """실제 직원들로 작은 프로젝트 하나. 비싸다."""
    from app import bus
    from app.database import store
    from app import orchestrator

    print(f"\n{DIM}── 실제 직원으로 프로젝트 하나 ──{OFF}")
    slug = orchestrator.start("두 수를 더하는 함수 하나와 그 사용법 한 줄을 만들어주세요")
    last = 0
    while orchestrator.is_running(slug):
        for ev in bus.replay(slug, last):
            last = ev["id"]
            if ev["type"] == "phase":
                print(f"{DIM}  [{ev['name']}] {ev.get('detail', '')}{OFF}")
            elif ev["type"] == "message" and ev.get("kind") in ("say", "verdict"):
                print(f"  {ev['agent']}: {ev['text'][:120]}")
        time.sleep(0.3)

    m = store.meta(slug)
    ok = m.get("status") == "done"
    line("✓" if ok else "✗", GREEN if ok else RED,
         f"프로젝트 {m.get('status')} · 완성도 {m.get('score')}% · "
         f"${m.get('cost', 0):.4f} · 파일 {len(store.files_of(slug))}개")
    if not ok:
        print(f"   {DIM}{m.get('stopped_reason', '')}{OFF}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="최초 실물 호출 점검")
    ap.add_argument("--company", action="store_true",
                    help="실제 직원들로 작은 프로젝트 하나를 돌린다 (비쌈)")
    args = ap.parse_args()

    secrets_broker.init()
    usage.bind("preflight")

    print(f"{DIM}── 키 ──{OFF}")
    for name, (env_var, label) in secrets_broker.KEYS.items():
        masked = secrets_broker.mask(name)
        line("✓" if masked else "·", GREEN if masked else DIM,
             f"{label}: {masked or '없음'}")

    if not any(secrets_broker.has(n) for n in secrets_broker.KEYS):
        print(f"\n{YELLOW}키가 하나도 없습니다.{OFF} 이 스크립트는 실제 호출을 "
              f"확인하는 것이라 할 일이 없습니다.\n설정 화면이나 환경변수로 "
              f"키를 넣고 다시 실행하세요.")
        return 1

    print(f"\n{DIM}── 제공자 ──{OFF}")
    ok = all([check_provider(n) for n in registry.names()])

    if args.company:
        ok = run_company() and ok

    t = usage.totals("preflight")
    print(f"\n{DIM}── 합계 ──{OFF}")
    print(f"호출 {t['calls']}회 · 입력 {t['input']} / 출력 {t['output']} 토큰 · "
          f"${t['cost']:.4f}")
    if not config.PRICES_VERIFIED:
        print(f"{YELLOW}단가가 검증되지 않았습니다 — 위 비용은 추측입니다.{OFF}")

    print()
    if ok:
        line("✓", GREEN, "실제 모델 호출이 성공했습니다. "
                         "이 제품의 최대 미검증 리스크가 사라졌습니다.")
    else:
        line("✗", RED, "실패한 제공자가 있습니다. 위의 실패 줄을 보세요.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
