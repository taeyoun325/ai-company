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

# 이전 제품의 단일 파일 UI. DAY 17 에 legacy/ 로 옮겼다 — 백엔드 루트에
# 또 하나의 화면이 떠 있으면 "어느 쪽이 진짜인가"를 매번 헷갈린다.
# 지우지 않은 이유는 설계 기록이고, 그 불변식을 지키는 테스트가 있어서다.
WEB = BACKEND / "legacy" / "web"
PROMPTS = BACKEND / "prompts"
PRICING_FILE = Path(os.getenv("PRICING_FILE", BACKEND / "pricing.json"))

PROJECTS = Path(os.getenv("PROJECTS_DIR") or ROOT / "projects")
LOGS = Path(os.getenv("LOGS_DIR") or ROOT / "logs")


def data_dir() -> Path:
    """DB 와 비밀 파일이 사는 곳 (DAY 16).

    컨테이너에서는 이 폴더 하나만 볼륨으로 빼면 상태가 전부 보존된다.
    `DATA_DIR` 이 없으면 저장소 루트를 쓴다 — 로컬 개발의 기존 동작 그대로다.

    함수인 이유: 테스트가 `config.ROOT` 를 임시 폴더로 바꿔 끼운다.
    모듈 로드 시점에 한 번 계산해두면 그 교체가 반영되지 않는다.
    """
    d = Path(os.getenv("DATA_DIR") or ROOT)
    d.mkdir(parents=True, exist_ok=True)
    return d

# --- 모델 카탈로그 (지시서 §7) ---
# 단가와 같은 이유로 코드 밖에 둔다: 모델 ID는 **사실**이고, 시점에 따라 바뀐다.
MODELS_FILE = Path(os.getenv("MODELS_FILE", BACKEND / "models.json"))

_CATALOG_FALLBACK = {
    "claude": {"default": "claude-opus-5", "models": []},
    "gemini": {"default": "gemini-2.5-pro", "models": []},
    "openai": {"default": "gpt-5", "models": []},
}


def _load_catalog() -> dict:
    try:
        data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_CATALOG_FALLBACK)
    return data.get("providers") or dict(_CATALOG_FALLBACK)


CATALOG = _load_catalog()


def default_model(provider: str) -> str:
    row = CATALOG.get(provider) or _CATALOG_FALLBACK.get(provider, {})
    return row.get("default", "")


def models_of(provider: str) -> list[dict]:
    row = CATALOG.get(provider) or {}
    return list(row.get("models", []))


def reload_catalog() -> None:
    """모델 파일을 다시 읽는다. 재배포 없이 모델을 갈아끼울 수 있어야 한다."""
    global CATALOG
    CATALOG = _load_catalog()


# --- 모델 (환경변수가 카탈로그 기본값을 덮는다) ---
PM_MODEL = os.getenv("PM_MODEL") or default_model("claude")
DEV_MODEL = os.getenv("DEV_MODEL") or default_model("claude")
# Gemini 모델 ID는 시점에 따라 바뀐다. 실행 전 client.models.list()로 확인할 것.
QA_MODEL = os.getenv("QA_MODEL") or default_model("gemini")
WRITER_MODEL = os.getenv("WRITER_MODEL") or default_model("openai")
DESIGNER_MODEL = os.getenv("DESIGNER_MODEL") or default_model("gemini")

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


_DEFAULT_CACHE = (0.1, 1.25)


def _load_pricing():
    """단가 파일을 읽는다. 없거나 깨졌으면 내장 기본값으로 버틴다.

    기동을 막지 않는 이유: 단가 파일 하나 때문에 서버가 안 뜨면, 단가를
    고치다 오타 한 번에 서비스가 내려간다. 대신 검증 여부를 남겨서
    화면이 "이 숫자는 검증되지 않았다"고 말할 수 있게 한다.
    """
    try:
        data = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_FALLBACK), {}, {}, False, "", {}
    models = data.get("models", {})
    prices, cache = {}, {}
    dflt = data.get("cache_defaults", {})
    dflt_pair = (float(dflt.get("read", _DEFAULT_CACHE[0])),
                 float(dflt.get("write", _DEFAULT_CACHE[1])))
    for name, row in models.items():
        if "price" not in row:
            continue
        prices[name] = (float(row["price"][0]), float(row["price"][1]))
        c = row.get("cache")
        cache[name] = (float(c[0]), float(c[1])) if c else dflt_pair
    verified = all(row.get("verified") for row in models.values()) if models else False
    return ((prices or dict(_FALLBACK)), cache, data.get("credits", {}), verified,
            data.get("verified_on", ""), data.get("plans", {}))


(PRICES, CACHE_RATES, CREDITS, PRICES_VERIFIED,
 PRICES_VERIFIED_ON, PLANS) = _load_pricing()

CREDIT_USD = 0.01           # 1 크레딧이 몇 달러어치 원가인가 (§15)


def _load_credit_usd() -> float:
    try:
        return float(json.loads(PRICING_FILE.read_text(encoding="utf-8"))
                     .get("credit_usd", 0.01))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0.01


CREDIT_USD = _load_credit_usd()


def reload_pricing() -> None:
    """단가 파일을 다시 읽는다. 재배포 없이 단가를 고칠 수 있어야 한다."""
    global PRICES, CACHE_RATES, CREDITS, PRICES_VERIFIED, PRICES_VERIFIED_ON
    global PLANS, CREDIT_USD
    (PRICES, CACHE_RATES, CREDITS, PRICES_VERIFIED,
     PRICES_VERIFIED_ON, PLANS) = _load_pricing()
    CREDIT_USD = _load_credit_usd()


def price_of(model: str, input_tokens: int, output_tokens: int,
             cached_tokens: int = 0, cache_written: int = 0) -> float:
    """이 호출의 **우리 원가**($).

    캐시를 보통 입력처럼 계산하지 않는다. 캐시 읽기는 입력의 0.1배,
    쓰기는 1.25배다(공식 단가, DAY 11 확인). 캐시분을 입력 단가로 더하면
    원가를 실제보다 크게 잡는데, 안전한 쪽으로 틀린 숫자도 틀린 숫자다 —
    §17 마진(원가 ≤ 판매가의 50%)을 그 숫자로 판단하면 팔 수 있는 가격을
    못 판다.

    모르는 모델은 0 이 아니라 **가장 비싼 모델**로 친다. 0 으로 두면
    예산 상한(§18)이 그 모델에는 걸리지 않는다. 모르면 비싸게 잡는 편이
    안전하다.
    """
    pin, pout = PRICES.get(model) or _max_price()
    cread, cwrite = CACHE_RATES.get(model, _DEFAULT_CACHE)
    return (input_tokens * pin
            + output_tokens * pout
            + cached_tokens * pin * cread
            + cache_written * pin * cwrite) / 1_000_000


def _max_price() -> tuple[float, float]:
    known = [v for k, v in PRICES.items() if k != "mock"]
    return max(known, key=lambda p: p[1]) if known else (0.0, 0.0)


def is_priced(model: str) -> bool:
    """단가를 아는 모델인가. 화면과 설정이 이것으로 거른다."""
    return model in PRICES


def credits_of(model: str) -> float:
    """지시서 §15. 모델별 크레딧 배수(화면 설명용). 모르는 모델은 1배로 본다.

    실제 차감은 이 배수가 아니라 원가 기반이다 — `app/usage/credits.py` 참조.
    배수만으로 차감하면 입력·출력 비율이 다른 작업에서 어긋난다.
    """
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
