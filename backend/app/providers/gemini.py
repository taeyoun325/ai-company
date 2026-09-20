"""GeminiProvider — Google 어댑터 (지시서 §7 · §8 Analyst-Gemini).

## 왜 Gemini 가 검증자인가

같은 회사 모델끼리 검토하면 학습 분포가 같아 **같은 실수를 함께 놓친다.**
구현이 Claude 면 검증은 다른 회사여야 한다. 이건 취향이 아니라 이 제품의
핵심 논리다(§8 교차검증).

## ClaudeProvider 와 같은 모양인 이유

`base.AIProvider` 가 재시도·백오프·사용량 집계를 전부 갖고 있으므로 여기는
**SDK 호출과 예외 번역**만 한다. 두 어댑터가 서로 다른 모양이면 그 차이가
곧 버그가 된다 — 계약 테스트를 둘에 똑같이 거는 이유다.

## genai 의 역할 이름이 다르다

Anthropic 은 `assistant`, Google 은 `model` 이다. 여기서 번역한다.
system 은 messages 가 아니라 `system_instruction` 설정으로 들어간다.
"""
from __future__ import annotations

from collections.abc import Iterator

from app import config, secrets_broker
from app.providers.base import (AIProvider, AuthError, GenerateRequest,
                                GenerateResult, ProviderError,
                                ProviderUnavailable, RateLimited,
                                RefusedError, TransientError, Usage)

# 기다렸다 다시 하면 되는 것들
_RETRYABLE = ("ServerError", "ServiceUnavailable", "DeadlineExceeded",
              "InternalServerError", "APIConnectionError", "APITimeoutError",
              "UnknownApiResponse")
_AUTH = ("PermissionDenied", "Unauthenticated", "UnauthorizedError",
         "AuthenticationError")

# 안전 필터에 걸려 끊긴 경우. 같은 입력을 다시 넣으면 또 걸린다.
_BLOCKED_FINISH = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
                   "RECITATION", "IMAGE_SAFETY"}


def translate(e: BaseException, provider: str = "gemini") -> ProviderError:
    """SDK 예외 → 우리 예외.

    genai 는 대부분을 `APIError`(+ `code`) 하나로 올린다. 그래서 타입 이름보다
    **HTTP 코드**가 더 믿을 만한 신호다. 모르는 것은 재시도하지 않는 쪽으로 둔다 —
    영영 성공하지 않을 요청에 MAX_RETRY 번 돈을 쓰는 것보다 멈추는 쪽이 싸다.
    """
    name = type(e).__name__
    msg = secrets_broker.scrub(f"{name}: {e}")
    status = getattr(e, "code", None) or getattr(e, "status_code", None)

    if status == 429 or name in ("ResourceExhausted", "RateLimitError"):
        return RateLimited(msg, retry_after=_retry_after(e), provider=provider, cause=e)
    if status in (401, 403) or name in _AUTH:
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


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, model: str | None = None):
        self.default_model = model or config.QA_MODEL

    def available(self) -> bool:
        return secrets_broker.has("gemini")

    def _client(self):
        if not self.available():
            raise ProviderUnavailable(
                "Google (Gemini) API 키가 없습니다. 설정에서 등록하세요.", provider=self.name)
        try:
            from app.providers import gemini_client
        except ImportError as e:                       # pragma: no cover
            raise ProviderUnavailable(
                f"google-genai 패키지가 없습니다: {e}", provider=self.name) from e
        return gemini_client.client()

    # ── 요청 ────────────────────────────────────────────────────────
    def _payload(self, req: GenerateRequest) -> dict:
        # Anthropic 의 'assistant' 는 여기서 'model' 이다. 이 한 줄을 빠뜨리면
        # 멀티턴 대화에서 역할이 뒤집혀 모델이 자기 말을 사용자 말로 읽는다.
        contents = [{"role": "model" if m.role == "assistant" else "user",
                     "parts": [{"text": m.content}]} for m in req.messages]
        return {
            "model": self.model_for(req),
            "contents": contents,
            "config": {
                "system_instruction": req.system,
                "max_output_tokens": req.max_tokens,
                "temperature": req.temperature,
            },
        }

    @staticmethod
    def _usage_of(raw) -> Usage:
        if not raw:
            return Usage()
        g = lambda k: getattr(raw, k, 0) or 0          # noqa: E731
        # genai 의 prompt_token_count 에는 캐시된 토큰이 **포함**되어 있다.
        # 그대로 두면 캐시분을 두 번 센다(base._bill 이 input+cached 를 과금).
        cached = g("cached_content_token_count")
        return Usage(input_tokens=max(0, g("prompt_token_count") - cached),
                     output_tokens=g("candidates_token_count"),
                     cached_tokens=cached)

    @staticmethod
    def _finish(resp) -> str | None:
        cands = getattr(resp, "candidates", None) or []
        if not cands:
            return None
        fr = getattr(cands[0], "finish_reason", None)
        return getattr(fr, "name", None) or (str(fr) if fr else None)

    def _generate(self, req: GenerateRequest) -> GenerateResult:
        client = self._client()
        try:
            resp = client.models.generate_content(**self._payload(req))
        except ProviderError:
            raise
        except Exception as e:                          # noqa: BLE001
            raise translate(e, self.name) from e

        finish = self._finish(resp)
        if finish in _BLOCKED_FINISH:
            raise RefusedError(f"모델이 응답을 차단했습니다: {finish}", provider=self.name)

        text = (getattr(resp, "text", None) or "").strip()
        if not text and finish not in (None, "STOP", "MAX_TOKENS"):
            # 빈 응답을 성공으로 올리면 위에서 "모델이 할 말이 없었다"로 읽는다.
            raise TransientError(f"빈 응답 (finish_reason={finish})", provider=self.name)

        return GenerateResult(
            text=text,
            model=self.model_for(req),
            provider=self.name,
            usage=self._usage_of(getattr(resp, "usage_metadata", None)),
            stop_reason=finish,
        )

    def _stream(self, req: GenerateRequest) -> Iterator[str]:
        client = self._client()
        try:
            for chunk in client.models.generate_content_stream(**self._payload(req)):
                piece = getattr(chunk, "text", None)
                if piece:
                    yield piece
        except ProviderError:
            raise
        except Exception as e:                          # noqa: BLE001
            raise translate(e, self.name) from e
