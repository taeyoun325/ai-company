"""OpenAI 클라이언트 — 작가(Writer) 직원이 쓴다.

키는 환경이 아니라 브로커에서 온다. 브로커가 기동 시 환경변수에서 키를 꺼내
지웠기 때문에, 여기서 os.environ 을 읽으면 아무것도 없다.
"""
import hashlib

from app import secrets_broker

# 클라이언트는 **키마다** 하나씩 둔다 (DAY 19 · BYOK).
#
# 예전에는 전역에 하나였다. 그 상태에서 고객이 자기 키를 쓰기 시작하면,
# 먼저 온 요청이 만든 클라이언트를 다음 테넌트가 그대로 물려쓴다 —
# 고객 A 의 키로 고객 B 의 호출이 나간다. 캐시 키를 해시로 두면 그
# 사고가 구조적으로 불가능해지고, 딕셔너리 키가 덤프돼도 키는 아니다.
_clients: dict = {}


def _fp(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def client():
    from openai import OpenAI
    key = secrets_broker.require("openai")
    fp = _fp(key)
    if fp not in _clients:
        _clients[fp] = OpenAI(api_key=key)
    return _clients[fp]


def reset_client() -> None:
    _clients.clear()


def list_models() -> list[str]:
    """실제로 쓸 수 있는 모델 ID를 조회한다. 설정 화면이 이 목록으로 고르게 한다."""
    return sorted({m.id for m in client().models.list()})
