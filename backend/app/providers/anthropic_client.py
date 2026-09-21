"""Anthropic 호출 공통부: 구조화 출력 + 프롬프트 캐싱 + 사용량 집계 + 재시도."""
import hashlib
import time
from typing import TypeVar

import anthropic

from app import bus
from app import secrets_broker
from app import usage

T = TypeVar("T")
_clients: dict[str, anthropic.Anthropic] = {}


def _fp(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def client() -> anthropic.Anthropic:
    """키는 환경이 아니라 브로커에서 온다. 환경에는 이미 남아 있지 않다."""
    key = secrets_broker.require("anthropic")
    fp = _fp(key)
    if fp not in _clients:
        _clients[fp] = anthropic.Anthropic(api_key=key)
    return _clients[fp]


def reset_client() -> None:
    """설정 화면에서 키가 바뀌면 다음 호출에 새 클라이언트를 만든다."""
    _clients.clear()

# 클라이언트는 **키마다** 하나씩 둔다 (DAY 19 · BYOK).
#
# 예전에는 전역에 하나였다. 그 상태에서 고객이 자기 키를 쓰기 시작하면,
# 먼저 온 요청이 만든 클라이언트를 **다음 테넌트가 그대로 물려쓴다** —
# 고객 A 의 키로 고객 B 의 호출이 나간다. 캐시 키를 실제 API 키로 두면
# 그 사고가 구조적으로 불가능해진다. 키 자체는 캐시 키로 쓰지 않고
# 해시를 쓴다 — 예외 메시지나 덤프에 딕셔너리 키가 찍혀도 키가 아니다.


def _bill(agent: str, model: str, u) -> None:
    if not u:
        return
    usage.record(
        agent, model,
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_written=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


def structured(agent: str, model: str, system: str, user: str, schema: type[T],
               max_tokens: int = 16000, retries: int = 1,
               extra_blocks: list | None = None) -> T:
    """system은 캐싱 대상(고정), user는 매번 바뀌는 부분.

    extra_blocks: 첨부 자료(이미지·문서) 콘텐츠 블록. 요구사항 텍스트 *앞에* 놓는다 —
    자료를 먼저 보여주고 지시를 나중에 주는 편이 자료를 지시로 오인할 여지가 적다.

    구조화 출력이라도 검증에 실패할 수 있으므로 한 번은 다시 물어본다.
    """
    content = ([*extra_blocks, {"type": "text", "text": user}]
               if extra_blocks else user)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client().messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": content}],
                output_format=schema,
            )
            _bill(agent, model, resp.usage)
            if resp.stop_reason == "refusal":
                raise RuntimeError(f"모델이 요청을 거절했습니다: {resp.stop_details}")
            return resp.parsed_output
        except (anthropic.APIStatusError, anthropic.APIConnectionError,
                ValueError, TypeError) as e:
            last = e
            if attempt >= retries:
                break
            bus.say("SYSTEM", f"{agent} 응답 처리 실패 — 재시도 ({type(e).__name__})",
                    kind="error")
            time.sleep(1.5)
    raise RuntimeError(f"{agent} 호출이 {retries + 1}회 모두 실패했습니다: {last}") from last


def bill_messages(agent: str, model: str, messages: list) -> None:
    """tool_runner가 뱉은 메시지들의 사용량을 합산."""
    for m in messages:
        _bill(agent, model, getattr(m, "usage", None))
