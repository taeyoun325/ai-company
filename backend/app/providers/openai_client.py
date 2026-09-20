"""OpenAI 클라이언트 — 작가(Writer) 직원이 쓴다.

키는 환경이 아니라 브로커에서 온다. 브로커가 기동 시 환경변수에서 키를 꺼내
지웠기 때문에, 여기서 os.environ 을 읽으면 아무것도 없다.
"""
from app import secrets_broker

_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=secrets_broker.require("openai"))
    return _client


def reset_client() -> None:
    global _client
    _client = None


def list_models() -> list[str]:
    """실제로 쓸 수 있는 모델 ID를 조회한다. 설정 화면이 이 목록으로 고르게 한다."""
    return sorted({m.id for m in client().models.list()})
