"""ClaudeProvider — Anthropic 어댑터 (지시서 §7 · §8 Developer-Claude).

SDK 호출과 **예외 번역**만 한다. 재시도·백오프·사용량 기록은 `base.AIProvider`
쪽에 있다. 여기서 또 하면 두 겹으로 재시도해서 상한이 `MAX_RETRY` 의 제곱이 된다.

## 예외를 번역하는 이유

SDK 예외를 그대로 위로 올리면 오케스트레이터가 anthropic 을 알아야 한다.
그러면 어댑터를 둔 의미가 없다. 여기서 "재시도해도 되는가"만 남긴 우리 쪽
예외로 바꿔서 올린다.

## 아직 한 번도 실행되지 않았다

키가 없어서다(현재 방침). `available()` 이 False 이므로 레지스트리가
Mock 으로 돌린다. **계약 테스트는 Mock 과 이 클래스에 똑같이 걸려 있고,
키가 없으면 이쪽만 skip 된다** — 키가 생기는 날 그 skip 이 풀리면서
계약을 지키는지 즉시 드러난다.
"""
from __future__ import annotations

from collections.abc import Iterator

from app import config, secrets_broker
from app.providers.base import (AIProvider, AuthError, GenerateRequest,
                                GenerateResult, ProviderError,
                                ProviderUnavailable, RateLimited,
                                RefusedError, TransientError, Usage)

# 5xx·연결 끊김·과부하 — 기다렸다 다시 하면 되는 것들
_RETRYABLE = ("APIConnectionError", "APITimeoutError", "InternalServerError",
              "OverloadedError", "ServiceUnavailableError", "RetryableError",
              "DeadlineExceededError", "ConflictError")
_AUTH = ("AuthenticationError", "PermissionDeniedError", "CredentialsError")


def translate(e: BaseException, provider: str = "claude") -> ProviderError:
    """SDK 예외 → 우리 예외. 모르는 것은 재시도하지 않는 쪽으로 둔다.

    모르는 오류를 재시도 가능으로 두면, 영영 성공하지 않을 요청에
    `MAX_RETRY` 번 돈을 쓴다. 판단이 안 서면 멈추는 쪽이 싸다.
    """
    name = type(e).__name__
    msg = secrets_broker.scrub(f"{name}: {e}")

    if name == "RateLimitError":
        retry_after = None
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                retry_after = float(resp.headers.get("retry-after"))
            except (AttributeError, TypeError, ValueError):
                retry_after = None
        return RateLimited(msg, retry_after=retry_after, provider=provider, cause=e)
    if name in _AUTH:
        return AuthError(msg, provider=provider, cause=e)
    if name in _RETRYABLE:
        return TransientError(msg, provider=provider, cause=e)

    status = getattr(e, "status_code", None)
    if isinstance(status, int) and status >= 500:
        return TransientError(msg, provider=provider, cause=e)
    if status == 429:
        return RateLimited(msg, provider=provider, cause=e)

    return ProviderError(msg, provider=provider, cause=e)


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, model: str | None = None):
        self.default_model = model or config.DEV_MODEL

    # ── 키 ──────────────────────────────────────────────────────────
    def available(self) -> bool:
        return secrets_broker.has("anthropic")

    def _client(self):
        """키는 환경이 아니라 브로커에서 온다 — 기동 시 환경에서 지워졌다."""
        if not self.available():
            raise ProviderUnavailable(
                "Anthropic API 키가 없습니다. 설정에서 등록하세요.", provider=self.name)
        try:
            from app.providers import anthropic_client
        except ImportError as e:                       # pragma: no cover
            raise ProviderUnavailable(
                f"anthropic 패키지가 없습니다: {e}", provider=self.name) from e
        return anthropic_client.client()

    # ── 호출 ────────────────────────────────────────────────────────
    def _payload(self, req: GenerateRequest) -> dict:
        """요청을 Anthropic 모양으로 옮긴다.

        ## temperature 를 보내지 않는다

        현재 Claude 모델(Opus 5 · Sonnet 5 · Opus 4.7+)은 `temperature` ·
        `top_p` · `top_k` 를 **거부한다**(400). 대신 `output_config.effort` 가
        "얼마나 공들일지"를 정한다. 다른 제공자는 여전히 temperature 를
        받으므로, 요청 객체는 둘 다 들고 있고 각 어댑터가 자기 것만 쓴다.

        이건 DAY 14 에 **유효하지 않은 키로 실제 SDK 를 태워보다가** 잡았다.
        키를 꽂는 날 첫 호출에서 `TypeError: unexpected keyword argument
        'temperature'` 로 터졌을 버그다 — 계약 테스트는 Mock 만 통과했고,
        Mock 은 SDK 시그니처를 모른다.

        ## system 에 cache_control 을 붙인다

        고정 프리픽스라 캐시가 걸리면 입력 비용이 크게 준다. 다만
        *걸렸는지*는 usage 의 cached 값으로 확인해야 한다 — 붙였다는
        사실만으로는 근거가 없다.
        """
        return {
            "model": self.model_for(req),
            "max_tokens": req.max_tokens,
            "output_config": {"effort": req.effort},
            "system": [{"type": "text", "text": req.system,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        }

    @staticmethod
    def _usage_of(raw) -> Usage:
        if not raw:
            return Usage()
        g = lambda k: getattr(raw, k, 0) or 0          # noqa: E731
        return Usage(input_tokens=g("input_tokens"), output_tokens=g("output_tokens"),
                     cached_tokens=g("cache_read_input_tokens"),
                     cache_written=g("cache_creation_input_tokens"))

    def _generate(self, req: GenerateRequest) -> GenerateResult:
        client = self._client()
        try:
            resp = client.messages.create(**self._payload(req))
        except ProviderError:
            raise
        except Exception as e:                          # noqa: BLE001 — 번역해서 올린다
            raise translate(e, self.name) from e

        if getattr(resp, "stop_reason", None) == "refusal":
            raise RefusedError(f"모델이 요청을 거절했습니다: "
                               f"{getattr(resp, 'stop_details', '')}", provider=self.name)

        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return GenerateResult(
            text=text.strip(),
            model=getattr(resp, "model", self.model_for(req)),
            provider=self.name,
            usage=self._usage_of(getattr(resp, "usage", None)),
            stop_reason=getattr(resp, "stop_reason", None),
        )

    def _stream(self, req: GenerateRequest) -> Iterator[str]:
        client = self._client()
        try:
            with client.messages.stream(**self._payload(req)) as s:
                yield from s.text_stream
        except ProviderError:
            raise
        except Exception as e:                          # noqa: BLE001
            raise translate(e, self.name) from e
