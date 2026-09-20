"""OpenAIProvider — OpenAI 어댑터 (지시서 §7 · §8 Writer).

## 세 번째 회사를 두는 이유

검증자(Gemini)가 구현자(Claude)와 다른 회사여야 하듯, 글을 쓰는 직원도
한 회사에 몰아두면 회사 전체의 문체와 맹점이 하나가 된다. 제공자가 셋이면
한 곳이 죽어도 회사가 멈추지 않는다(§18 대체 사슬).

## Responses API 를 쓴다

`chat.completions` 가 아니라 `responses` 다. 이유는 입력 구조가 Anthropic·
Gemini 와 같은 모양(system 따로, 메시지 배열 따로)이라 어댑터 셋이 서로
닮아 있게 되고, 캐시된 입력 토큰(`cached_tokens`)이 사용량에 그대로
나오기 때문이다 — §14 원가 계산이 그 값을 쓴다.

## 예외 번역만 한다

재시도·백오프·사용량 집계는 `base.AIProvider` 에 있다. 여기서 또 하면
두 겹으로 재시도해서 상한이 MAX_RETRY 의 제곱이 된다.
"""
from __future__ import annotations

from collections.abc import Iterator

from app import config, secrets_broker
from app.providers.base import (AIProvider, AuthError, GenerateRequest,
                                GenerateResult, ProviderError,
                                ProviderUnavailable, RateLimited,
                                RefusedError, TransientError, Usage)

_RETRYABLE = ("APIConnectionError", "APITimeoutError", "InternalServerError",
              "APIConnectionTimeoutError")
_AUTH = ("AuthenticationError", "PermissionDeniedError")


def translate(e: BaseException, provider: str = "openai") -> ProviderError:
    """SDK 예외 → 우리 예외. 모르는 것은 재시도하지 않는 쪽으로 둔다."""
    name = type(e).__name__
    msg = secrets_broker.scrub(f"{name}: {e}")
    status = getattr(e, "status_code", None)

    if name == "RateLimitError" or status == 429:
        return RateLimited(msg, retry_after=_retry_after(e), provider=provider, cause=e)
    if name in _AUTH or status in (401, 403):
        return AuthError(msg, provider=provider, cause=e)
    if name in _RETRYABLE:
        return TransientError(msg, provider=provider, cause=e)
    if isinstance(status, int) and status >= 500:
        return TransientError(msg, provider=provider, cause=e)
    return ProviderError(msg, provider=provider, cause=e)


def _retry_after(e: BaseException) -> float | None:
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    try:
        return float(headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, model: str | None = None):
        self.default_model = model or config.WRITER_MODEL

    def available(self) -> bool:
        return secrets_broker.has("openai")

    def _client(self):
        if not self.available():
            raise ProviderUnavailable(
                "OpenAI API 키가 없습니다. 설정에서 등록하세요.", provider=self.name)
        try:
            from app.providers import openai_client
        except ImportError as e:                       # pragma: no cover
            raise ProviderUnavailable(
                f"openai 패키지가 없습니다: {e}", provider=self.name) from e
        return openai_client.client()

    # ── 요청 ────────────────────────────────────────────────────────
    def _payload(self, req: GenerateRequest) -> dict:
        return {
            "model": self.model_for(req),
            "instructions": req.system,
            "input": [{"role": m.role, "content": m.content} for m in req.messages],
            "max_output_tokens": req.max_tokens,
            "temperature": req.temperature,
        }

    @staticmethod
    def _usage_of(raw) -> Usage:
        if not raw:
            return Usage()
        g = lambda k: getattr(raw, k, 0) or 0          # noqa: E731
        details = getattr(raw, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        # input_tokens 에 캐시분이 포함되어 있다. 빼지 않으면 두 번 센다.
        return Usage(input_tokens=max(0, g("input_tokens") - cached),
                     output_tokens=g("output_tokens"),
                     cached_tokens=cached)

    @staticmethod
    def _text_of(resp) -> str:
        text = getattr(resp, "output_text", None)
        if text:
            return text
        # output_text 는 편의 속성이다. 없으면 블록을 직접 잇는다.
        parts: list[str] = []
        for item in getattr(resp, "output", None) or []:
            for block in getattr(item, "content", None) or []:
                if getattr(block, "type", "") == "output_text":
                    parts.append(getattr(block, "text", "") or "")
        return "".join(parts)

    def _generate(self, req: GenerateRequest) -> GenerateResult:
        client = self._client()
        try:
            resp = client.responses.create(**self._payload(req))
        except ProviderError:
            raise
        except Exception as e:                          # noqa: BLE001
            raise translate(e, self.name) from e

        status = getattr(resp, "status", None)
        if status == "incomplete":
            reason = getattr(getattr(resp, "incomplete_details", None), "reason", "")
            if reason and reason != "max_output_tokens":
                raise RefusedError(f"응답이 중단됐습니다: {reason}", provider=self.name)

        for item in getattr(resp, "output", None) or []:
            if getattr(item, "type", "") == "refusal":
                raise RefusedError("모델이 요청을 거절했습니다.", provider=self.name)

        return GenerateResult(
            text=self._text_of(resp).strip(),
            model=getattr(resp, "model", self.model_for(req)),
            provider=self.name,
            usage=self._usage_of(getattr(resp, "usage", None)),
            stop_reason=status,
        )

    def _stream(self, req: GenerateRequest) -> Iterator[str]:
        client = self._client()
        try:
            with client.responses.stream(**self._payload(req)) as s:
                for event in s:
                    if getattr(event, "type", "") == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield delta
        except ProviderError:
            raise
        except Exception as e:                          # noqa: BLE001
            raise translate(e, self.name) from e
