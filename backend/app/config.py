"""전역 설정. 환경변수로 덮어쓸 수 있다.

## 경로 기준

모듈이 `backend/app/` 아래로 내려가면서 `__file__` 기준점이 바뀌었다.
런타임 산출물(logs·projects·비밀키·첨부)은 **저장소 루트**에 그대로 둔다 —
`.gitignore` 가 그 위치를 전제로 쓰여 있고, 위치를 옮기면 비밀 파일이
조용히 커밋될 수 있다.

## 가격표를 파일로 뺀 이유 (지시서 §14)

단가는 코드가 아니라 **사실**이다. 바뀔 때 코드를 고쳐 배포해야 한다면
그건 틀린 자리에 있는 것이다. `pricing.json` 에 두고 여기서 읽는다.
값이 검증되지 않았다는 사실도 파일에 같이 적어둔다 — 검증 안 된 단가로
계산한 원가는 근거가 아니라 추측이기 때문이다.
"""
import json
import os
from pathlib import Path

APP = Path(__file__).resolve().parent          # backend/app
BACKEND = APP.parent                           # backend
ROOT = BACKEND.parent                          # 저장소 루트

WEB = APP / "web"                              # 이전 제품의 단일 파일 UI
PROMPTS = BACKEND / "prompts"
PRICING_FILE = Path(os.getenv("PRICING_FILE", BACKEND / "pricing.json"))

PROJECTS = ROOT / "projects"     # 산출물이 프로젝트별로 쌓이는 저장소
LOGS = ROOT / "logs"

# --- 모델 ---
PM_MODEL = os.getenv("PM_MODEL", "claude-opus-5")
DEV_MODEL = os.getenv("DEV_MODEL", "claude-opus-5")
# Gemini 모델 ID는 시점에 따라 바뀐다. 실행 전 client.models.list()로 확인할 것.
QA_MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

MODEL_OF = {"PM": PM_MODEL, "DEV": DEV_MODEL, "QA": QA_MODEL}

# --- 안전장치 (지시서 §18) ---
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "40"))          # 전체 턴 상한
MAX_REWORK = int(os.getenv("MAX_REWORK", "3"))           # 태스크당 반려 허용 횟수
MAX_REPLANS = int(os.getenv("MAX_REPLANS", "3"))         # 전체 재기획 허용 횟수
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "20"))  # 에이전트 루프 상한
MAX_RETRY = int(os.getenv("MAX_RETRY", "5"))             # API 오류 재시도 상한

BUDGET_USD = float(os.getenv("BUDGET_USD", "5.0"))       # 누적 비용 상한(1회 실행)
MAX_PROJECT_COST = float(os.getenv("MAX_PROJECT_COST", "5.0"))
MAX_DAILY_COST = float(os.getenv("MAX_DAILY_COST", "50.0"))
MAX_USER_COST = float(os.getenv("MAX_USER_COST", "100.0"))

DEV_MAX_TOKENS = int(os.getenv("DEV_MAX_TOKENS", "32000"))
PM_MAX_TOKENS = 16000
QA_MAX_TOKENS = 16000

# --- 가격표 ($/1M tokens) — pricing.json 에서 읽는다 ---
_FALLBACK = {"claude-opus-5": (5.00, 25.00), "gemini-2.5-pro": (1.25, 10.00),
             "mock": (0.0, 0.0)}


def _load_pricing() -> tuple[dict[str, tuple[float, float]], dict[str, float], bool]:
    """(단가표, 크레딧 배수, 전부_검증됐는가)."""
    try:
        data = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_FALLBACK), {}, False
    models = data.get("models", {})
    prices = {name: (float(row["price"][0]), float(row["price"][1]))
              for name, row in models.items() if "price" in row}
    verified = all(row.get("verified") for row in models.values()) if models else False
    return (prices or dict(_FALLBACK)), data.get("credits", {}), verified


PRICES, CREDITS, PRICES_VERIFIED = _load_pricing()


def reload_pricing() -> None:
    """단가 파일을 다시 읽는다. 재배포 없이 단가를 고칠 수 있어야 한다."""
    global PRICES, CREDITS, PRICES_VERIFIED
    PRICES, CREDITS, PRICES_VERIFIED = _load_pricing()


def price_of(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return input_tokens / 1_000_000 * pin + output_tokens / 1_000_000 * pout


def credits_of(model: str) -> float:
    """지시서 §15. 모델별 크레딧 배수. 모르는 모델은 1배로 본다."""
    return float(CREDITS.get(model, 1.0))


# 호출 *전에* 예산을 검사하기 위한 1회 호출 최악 비용 추정치($).
# 사후 감지는 상한이 아니다 — DEV 한 번이 예산을 통째로 넘겨버릴 수 있다.
# 입력은 넉넉히 잡고, 출력은 max_tokens를 다 쓴다고 가정한다.
_WORST_INPUT = {"PM": 40_000, "DEV": 80_000, "QA": 80_000}
WORST_CASE = {
    role: price_of(MODEL_OF[role], _WORST_INPUT[role], out)
    for role, out in (("PM", PM_MAX_TOKENS), ("DEV", DEV_MAX_TOKENS),
                      ("QA", QA_MAX_TOKENS))
}


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
