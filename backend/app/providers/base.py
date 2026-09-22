"""AI 제공자 인터페이스 (지시서 §7).

## 왜 어댑터인가

직원 코드가 anthropic·genai SDK 를 직접 부르면 모델을 바꿀 수 없다.
모든 모델 호출이 이 인터페이스를 지나가야, 나중에 제공자를 갈아끼우는 일이
**설정 변경**이 된다. 지금은 API 키가 없어 Mock 으로만 돌리므로, 이 규칙이
"나중에 좋은 구조"가 아니라 **당장의 생존 조건**이다.

## 재시도·백오프·사용량 기록이 왜 여기 있나

각 제공자가 알아서 하게 두면 제공자마다 다르게 하거나 빠뜨린다.
`generate()` 는 **final** 이라고 생각하고 읽으면 된다 — 하위 클래스는
`_generate()` 만 구현하고, 재시도(§18)·사용량 집계(§14)는 공짜로 얻는다.

## 동기인 이유 (지시서 §7 은 async 로 적혀 있다)

의도한 이탈이다. `bus.py` 와 `usage/` 가 실행(run) 범위를 `threading.local()`
로 잡는다. 한 스레드에서 코루틴이 번갈아 돌면 그 스레드 로컬이 서로 다른
실행의 것을 가리키게 되어 **비용이 엉뚱한 프로젝트에 붙는다.**
그래서 핵심은 동기로 두고, FastAPI 쪽에서 쓸 async 표면은
`agenerate()` · `astream()` 으로 따로 낸다 — 스레드 풀로 넘기므로
스레드 로컬이 깨지지 않는다.
"""
from __future__ import annotations

import abc
import asyncio
import random
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field, replace
from typing import Literal

from app import bus, config, lang, usage

Role = Literal["user", "assistant"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


# ── 주고받는 값 ────────────────────────────────────────────────────
@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_written: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cached_tokens


@dataclass(frozen=True)
class GenerateRequest:
    """한 번의 모델 호출.

    agent: 사용량을 누구 앞으로 달 것인가(§14). 직원 id 를 넣는다.
    model: None 이면 제공자의 기본 모델. 직원이 모델을 고를 수 있게 열어둔다.
    """
    system: str
    messages: list[Message] = field(default_factory=list)
    model: str | None = None
    max_tokens: int = 4096
    # temperature 는 **모든 제공자가 받는 값이 아니다.** 현재 Claude 모델은
    # 이 값을 아예 거부한다(400). 그래서 '얼마나 공들일지'를 뜻하는
    # effort 를 따로 둔다 — Claude 는 effort 를, Gemini·OpenAI 는
    # temperature 를 쓴다. 둘을 한 값으로 뭉개지 않는 이유: 창의성과
    # 사고 깊이는 다른 축이고, 뭉개면 어느 쪽도 제대로 조절되지 않는다.
    temperature: float = 0.2
    effort: Effort = "high"
    agent: str = "SYSTEM"

    @classmethod
    def ask(cls, system: str, user: str, **kw) -> GenerateRequest:
        return cls(system=system, messages=[Message("user", user)], **kw)

    @property
    def last_user_text(self) -> str:
        for m in reversed(self.messages):
            if m.role == "user":
                return m.content
        return ""


@dataclass(frozen=True)
class GenerateResult:
    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None
    attempts: int = 1


# ── 오류 ────────────────────────────────────────────────────────────
class ProviderError(RuntimeError):
    """제공자 호출 실패. `retryable` 이 재시도 여부를 가른다.

    재시도 가능 여부를 예외 타입에 박아두는 이유: 호출부가 문자열을 보고
    짐작하지 않게 하기 위해서다. 짐작은 틀리고, 틀리면 4xx 에 5번 재시도한다.
    """
    retryable = False

    def __init__(self, message: str, *, provider: str = "", cause: BaseException | None = None):
        super().__init__(message)
        self.provider = provider
        self.cause = cause


class ProviderUnavailable(ProviderError):
    """키가 없거나 설정이 틀렸다. 재시도해도 같은 결과다."""


class AuthError(ProviderError):
    """인증 거부. 키를 고치기 전에는 몇 번을 해도 같다."""


class RefusedError(ProviderError):
    """모델이 요청을 거절했다. 같은 입력을 다시 넣으면 또 거절한다."""


class RateLimited(ProviderError):
    """요청 한도. 기다렸다 다시 하면 된다."""
    retryable = True

    def __init__(self, message: str, *, retry_after: float | None = None, **kw):
        super().__init__(message, **kw)
        self.retry_after = retry_after


class TransientError(ProviderError):
    """일시적 장애(5xx·연결 끊김). 기다렸다 다시 하면 된다."""
    retryable = True


# ── 재시도 ──────────────────────────────────────────────────────────
BASE_DELAY = 0.5
MAX_DELAY = 20.0


def _sleep(seconds: float) -> None:
    """테스트가 갈아끼울 수 있게 모듈 수준으로 빼뒀다.

    안 그러면 재시도 테스트 하나가 30초를 잡아먹는다.
    """
    time.sleep(seconds)


def backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    """지수 백오프 + 지터. attempt 는 0부터.

    지터를 넣는 이유: 여러 직원이 동시에 한도를 맞으면 똑같이 기다렸다가
    똑같이 다시 몰려가서 또 한도를 맞는다.
    """
    if retry_after is not None:
        return min(float(retry_after), MAX_DELAY)
    return min(BASE_DELAY * (2 ** attempt), MAX_DELAY) * (0.5 + random.random() / 2)


# ── 인터페이스 ──────────────────────────────────────────────────────
class AIProvider(abc.ABC):
    """모든 AI 제공자의 공통 표면.

    하위 클래스가 구현할 것은 `available` · `_generate` · `_stream` 셋뿐이다.
    """

    name: str = "base"
    default_model: str = ""

    # --- 하위 클래스가 구현한다 ---
    @abc.abstractmethod
    def available(self) -> bool:
        """지금 실제로 호출할 수 있는가(키가 있는가)."""

    @abc.abstractmethod
    def _generate(self, req: GenerateRequest) -> GenerateResult:
        """한 번 호출한다. 실패는 ProviderError 로 올린다."""

    @abc.abstractmethod
    def _stream(self, req: GenerateRequest) -> Iterator[str]:
        """조각을 흘린다. 조각을 다 이으면 `_generate` 의 text 와 같아야 한다."""

    # --- 공통 ---
    def model_for(self, req: GenerateRequest) -> str:
        return req.model or self.default_model

    def generate(self, req: GenerateRequest) -> GenerateResult:
        """재시도·백오프·사용량 기록을 붙여 호출한다.

        재시도 상한은 `config.MAX_RETRY`(§18). 상한에 닿으면 마지막 오류를
        그대로 올린다 — 조용히 빈 결과를 돌려주면 위에서 성공으로 오해한다.
        """
        last: ProviderError | None = None
        for attempt in range(config.MAX_RETRY + 1):
            try:
                result = self._generate(req)
            except ProviderError as e:
                last = e
                if not e.retryable or attempt >= config.MAX_RETRY:
                    raise
                delay = backoff_delay(attempt, getattr(e, "retry_after", None))
                bus.say("SYSTEM",
                        lang.t("log.retry", who=self.name, delay=f"{delay:.1f}",
                               n=attempt + 1, max=config.MAX_RETRY,
                               why=type(e).__name__),
                        kind="error")
                _sleep(delay)
                continue
            result = replace(result, attempts=attempt + 1)
            self._bill(req, result)
            return result
        raise last or TransientError(lang.t("prov.retries"), provider=self.name)

    def stream(self, req: GenerateRequest) -> Iterator[str]:
        """스트리밍은 재시도하지 않는다.

        조각을 이미 내보낸 뒤에 재시도하면 사용자는 같은 문장을 두 번 본다.
        끊기면 호출부가 판단해서 `generate()` 로 다시 받게 한다.
        """
        return self._stream(req)

    async def agenerate(self, req: GenerateRequest) -> GenerateResult:
        """FastAPI 쪽 표면. 스레드로 넘겨서 스레드 로컬을 지킨다."""
        return await asyncio.to_thread(self.generate, req)

    async def astream(self, req: GenerateRequest) -> AsyncIterator[str]:
        it = self.stream(req)
        sentinel = object()
        while True:
            chunk = await asyncio.to_thread(next, it, sentinel)
            if chunk is sentinel:
                return
            yield chunk  # type: ignore[misc]

    def _bill(self, req: GenerateRequest, result: GenerateResult) -> None:
        u = result.usage
        usage.record(req.agent, result.model,
                     input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                     cached_tokens=u.cached_tokens, cache_written=u.cache_written)

    def info(self) -> dict:
        return {"name": self.name, "model": self.default_model,
                "available": self.available()}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} model={self.default_model}>"


# ── 대체 제공자 (지시서 §18) ────────────────────────────────────────
class FallbackProvider(AIProvider):
    """앞이 쓰러지면 뒤로 넘긴다.

    `available()` 이 False 인 제공자는 **시도조차 하지 않는다.** 키가 없는
    제공자에 요청을 던져 예외를 받고 넘어가는 것은 낭비다.

    재시도 가능한 오류는 각 제공자의 `generate()` 안에서 이미 다 소진된 뒤
    여기로 온다. 즉 여기 도달했다는 것은 그 제공자로는 안 된다는 뜻이다.
    """

    def __init__(self, primary: AIProvider, *fallbacks: AIProvider):
        self.chain: list[AIProvider] = [primary, *fallbacks]
        self.name = "→".join(p.name for p in self.chain)
        self.default_model = primary.default_model

    def available(self) -> bool:
        return any(p.available() for p in self.chain)

    def _usable(self) -> list[AIProvider]:
        return [p for p in self.chain if p.available()]

    def generate(self, req: GenerateRequest) -> GenerateResult:
        usable = self._usable()
        if not usable:
            raise ProviderUnavailable(
                lang.t("prov.none", name=self.name), provider=self.name)
        last: ProviderError | None = None
        for p in usable:
            try:
                return p.generate(req)
            except ProviderError as e:
                last = e
                bus.say("SYSTEM",
                        lang.t("log.fallback", who=p.name,
                               why=type(e).__name__), kind="error")
        raise last or ProviderUnavailable(lang.t("prov.allFailed"),
                                          provider=self.name)

    def stream(self, req: GenerateRequest) -> Iterator[str]:
        usable = self._usable()
        if not usable:
            raise ProviderUnavailable(
                lang.t("prov.none", name=self.name), provider=self.name)
        return usable[0].stream(req)

    # 추상 메서드 충족용 — 이 클래스는 위임만 하므로 직접 호출되지 않는다.
    def _generate(self, req: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    def _stream(self, req: GenerateRequest) -> Iterator[str]:
        raise NotImplementedError
