"""전역 설정. 환경변수로 덮어쓸 수 있다."""
import os
from pathlib import Path

ROOT = Path(__file__).parent
PROJECTS = ROOT / "projects"     # 제작한 프로그램이 프로젝트별로 쌓이는 저장소
LOGS = ROOT / "logs"
PROMPTS = ROOT / "prompts"

# --- 모델 ---
PM_MODEL = os.getenv("PM_MODEL", "claude-opus-5")
DEV_MODEL = os.getenv("DEV_MODEL", "claude-opus-5")
# Gemini 모델 ID는 시점에 따라 바뀐다. 실행 전 client.models.list()로 확인할 것.
QA_MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

MODEL_OF = {"PM": PM_MODEL, "DEV": DEV_MODEL, "QA": QA_MODEL}

# --- 안전장치 ---
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "40"))      # 전체 턴 상한
MAX_REWORK = int(os.getenv("MAX_REWORK", "3"))       # 태스크당 QA 반려 허용 횟수
MAX_REPLANS = int(os.getenv("MAX_REPLANS", "3"))     # 전체 재기획 허용 횟수
BUDGET_USD = float(os.getenv("BUDGET_USD", "5.0"))   # 누적 비용 상한
DEV_MAX_TOKENS = int(os.getenv("DEV_MAX_TOKENS", "32000"))
PM_MAX_TOKENS = 16000
QA_MAX_TOKENS = 16000

# --- 가격표 ($/1M tokens) ---
# Gemini 단가는 근사치다. 정확한 비용이 필요하면 실제 단가로 고칠 것.
PRICES = {
    "claude-opus-5":   (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-2.5-pro":  (1.25, 10.00),
}


def price_of(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return input_tokens / 1_000_000 * pin + output_tokens / 1_000_000 * pout


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
