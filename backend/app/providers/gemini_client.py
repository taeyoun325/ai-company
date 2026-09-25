"""Gemini 클라이언트 — 검증자(reviewer)가 쓴다.

키는 환경이 아니라 브로커에서 온다. 브로커가 기동 시 환경변수에서 키를 꺼내
지웠기 때문에, 여기서 os.environ 을 읽으면 아무것도 없다.
"""
import hashlib
from app import secrets_broker

_clients: dict = {}


def _fp(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def client():
    """genai 는 기본으로 재시도하지 않는다(`retry_options=None`). 그대로 둔다 —
    재시도는 `base.AIProvider.generate` 한 곳에서만 한다."""
    from google import genai
    from app import config
    key = secrets_broker.require("gemini")
    base = config.base_url("gemini")
    fp = _fp(key + "|" + (base or ""))
    if fp not in _clients:
        # genai 의 timeout 은 **밀리초**다. 초로 넣으면 0.6초에 끊긴다.
        opts = {"timeout": int(config.PROVIDER_TIMEOUT * 1000)}
        if base:
            opts["base_url"] = base
        _clients[fp] = genai.Client(api_key=key, http_options=opts)
    return _clients[fp]


def reset_client() -> None:
    _clients.clear()

# 클라이언트는 **키마다** 하나씩 둔다 (DAY 19 · BYOK).
#
# 예전에는 전역에 하나였다. 그 상태에서 고객이 자기 키를 쓰기 시작하면,
# 먼저 온 요청이 만든 클라이언트를 **다음 테넌트가 그대로 물려쓴다** —
# 고객 A 의 키로 고객 B 의 호출이 나간다. 캐시 키를 실제 API 키로 두면
# 그 사고가 구조적으로 불가능해진다. 키 자체는 캐시 키로 쓰지 않고
# 해시를 쓴다 — 예외 메시지나 덤프에 딕셔너리 키가 찍혀도 키가 아니다.


def list_models() -> list[str]:
    """실제로 쓸 수 있는 모델 ID를 조회한다.

    config.QA_MODEL 의 기본값은 추측이다. 설정 화면에서 이 목록으로 고르게 한다.
    """
    out = []
    for m in client().models.list():
        name = getattr(m, "name", "") or ""
        mid = name.split("/")[-1] if "/" in name else name
        actions = getattr(m, "supported_actions", None) or []
        if mid and (not actions or "generateContent" in actions):
            out.append(mid)
    return sorted(set(out))
