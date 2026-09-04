"""Anthropic 호출 공통부: 구조화 출력 + 프롬프트 캐싱 + 사용량 집계 + 재시도."""
import time
from typing import TypeVar

import anthropic

import bus
import usage

T = TypeVar("T")
_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


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
               max_tokens: int = 16000, retries: int = 1) -> T:
    """system은 캐싱 대상(고정), user는 매번 바뀌는 부분.

    구조화 출력이라도 검증에 실패할 수 있으므로 한 번은 다시 물어본다.
    """
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client().messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": user}],
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
