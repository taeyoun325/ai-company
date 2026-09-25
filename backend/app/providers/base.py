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
import itertools
import random
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack
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


@dataclass(frozen=True)
class StreamEnd:
    """스트림 끝에 제공자가 알려주는 사용량 (DAY 26).

    `_stream()` 은 글 조각(`str`)을 흘리고, 제공자가 사용량을 알려주면
    **마지막에** 이것을 하나 낸다. 호출부에는 나가지 않는다 — `stream()` 이
    받아서 청구한다. 조각과 한 통로로 흘리는 이유: 사용량은 스트림이 끝나야
    알 수 있고, 따로 돌려받는 길을 두면 제공자마다 그 길을 빠뜨린다.
    """
    usage: Usage
    model: str | None = None
    stop_reason: str | None = None


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


# ── 호출 기록 (DAY 25 · 관측성) ────────────────────────────────────
_call_seq = itertools.count(1)


def _next_call_id() -> int:
    return next(_call_seq)


def _emit_call(stage: str, call_id: int, agent: str, provider: str,
               model: str, **detail) -> None:
    """모델 호출 하나의 시작·끝을 버스에 남긴다.

    실행 밖의 호출(설정 화면의 키 확인 등)은 버스에 run 이 없다 — 그런
    호출까지 로그에 섞지 않는다. 기록에 실패해도 호출은 계속된다: 관측은
    증거물이지 실행의 전제가 아니다.
    """
    if bus.current() is None:
        return
    try:
        rounded = {k: (round(v, 1) if isinstance(v, float) else v)
                   for k, v in detail.items()}
        bus.emit("call", call_id=call_id, stage=stage, agent=agent,
                 provider=provider, model=model, **rounded)
    except Exception:                                          # noqa: BLE001
        pass


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
    def _stream(self, req: GenerateRequest) -> Iterator[str | StreamEnd]:
        """조각을 흘린다. 조각을 다 이으면 `_generate` 의 text 와 같아야 한다.

        제공자가 사용량을 알려주면 마지막에 `StreamEnd` 를 하나 낸다. 안
        내면 `stream()` 이 글자 수로 어림해 청구한다 — 0 으로 두지 않는다.
        """

    # --- 공통 ---
    def model_for(self, req: GenerateRequest) -> str:
        return req.model or self.default_model

    def generate(self, req: GenerateRequest) -> GenerateResult:
        """재시도·백오프·사용량 기록·**걸린 시간**을 붙여 호출한다.

        재시도 상한은 `config.MAX_RETRY`(§18). 상한에 닿으면 마지막 오류를
        그대로 올린다 — 조용히 빈 결과를 돌려주면 위에서 성공으로 오해한다.

        ## 시간을 여기서 재는 이유 (DAY 25)

        비용은 보였지만 "왜 느린가"는 안 보였다. 느린 이유는 셋 중 하나다 —
        모델이 오래 생각했다(`model_ms`), 한도에 걸려 기다렸다(`wait_ms`),
        실패하고 다시 불렀다(`attempts`). 셋을 **따로** 재야 대응이 갈린다:
        첫째는 모델·effort 를 낮추고, 둘째는 요청 한도를 올리고, 셋째는
        제공자 상태를 본다. 한 숫자로 뭉치면 셋 다 "느리다"로 보인다.

        호출 시작과 끝에 `call` 이벤트를 낸다. 시작을 따로 내는 이유는,
        끝난 호출만 보이면 **지금 3분째 응답을 기다리는 중**이라는 사실이
        끝날 때까지 안 보이기 때문이다 — 가장 답답한 순간에 화면이 조용하다.
        """
        call_id = _next_call_id()
        model = self.model_for(req)
        _emit_call("start", call_id, req.agent, self.name, model)
        started = time.perf_counter()
        model_ms = 0.0
        wait_ms = 0.0
        last: ProviderError | None = None
        for attempt in range(config.MAX_RETRY + 1):
            t0 = time.perf_counter()
            try:
                result = self._generate(req)
            except ProviderError as e:
                model_ms += (time.perf_counter() - t0) * 1000
                last = e
                if not e.retryable or attempt >= config.MAX_RETRY:
                    total = (time.perf_counter() - started) * 1000
                    usage.record_failure(req.agent, total)
                    _emit_call("end", call_id, req.agent, self.name, model,
                               ok=False, ms=total, model_ms=model_ms,
                               wait_ms=wait_ms, attempts=attempt + 1,
                               error=type(e).__name__)
                    raise
                delay = backoff_delay(attempt, getattr(e, "retry_after", None))
                bus.say("SYSTEM",
                        lang.t("log.retry", who=self.name, delay=f"{delay:.1f}",
                               n=attempt + 1, max=config.MAX_RETRY,
                               why=type(e).__name__),
                        kind="error")
                w0 = time.perf_counter()
                _sleep(delay)
                wait_ms += (time.perf_counter() - w0) * 1000
                continue
            model_ms += (time.perf_counter() - t0) * 1000
            total = (time.perf_counter() - started) * 1000
            result = replace(result, attempts=attempt + 1)
            self._bill(req, result, latency_ms=total, wait_ms=wait_ms)
            u = result.usage
            _emit_call("end", call_id, req.agent, self.name, result.model,
                       ok=True, ms=total, model_ms=model_ms, wait_ms=wait_ms,
                       attempts=attempt + 1, input=u.input_tokens,
                       output=u.output_tokens, cached=u.cached_tokens)
            return result
        raise last or TransientError(lang.t("prov.retries"), provider=self.name)

    def stream(self, req: GenerateRequest) -> Iterator[str]:
        """조각을 흘린다 — `generate()` 와 **똑같이** 청구·기록한다 (DAY 26).

        ## 왜 여기서 청구하나

        DAY 25 까지 이 메서드는 `_stream()` 을 그대로 돌려줬다. 재시도도,
        사용량도, 시간도 없었다 — 스트리밍으로 부른 호출은 **청구되지
        않았다.** 쓰는 곳이 없어서 드러나지 않았을 뿐, 화면에 스트리밍을
        붙이는 날 그 호출은 공짜가 된다(우리 키로 나가는데 고객 크레딧은
        안 깎인다).

        ## 재시도는 첫 조각 전까지만

        조각을 이미 내보낸 뒤에 다시 부르면 사용자는 같은 문장을 두 번
        본다. 첫 조각이 나오기 **전**의 실패(연결 거절·429)는 `generate()`
        와 같은 규칙으로 다시 한다 — 아무것도 보여준 적이 없으니 겹칠 것도
        없다.

        ## 중간에 끊겨도 청구한다

        소비자가 도중에 그만 읽거나(`close()`), 조각을 내보낸 뒤 연결이
        끊기면 제공자는 **이미 만든 만큼 청구한다.** 사용량을 끝까지 못
        받으므로 글자 수로 어림해서 남긴다. 0 으로 두면 끊는 것이 곧
        공짜로 쓰는 법이 된다.

        ## 실행 범위를 **지금** 잡는다

        이 함수는 제너레이터가 아니다 — 부르는 순간 실행(`bus`·`usage`)을
        기억한다. `astream()` 은 조각마다 스레드 풀의 아무 스레드에서
        `next()` 를 부르는데, 그 스레드에는 실행이 묶여 있지 않다. 몸통이
        처음 도는 순간에 잡으면 이미 늦다.
        """
        return self._open_stream(req, bus.current(), usage.current())

    def _open_stream(self, req: GenerateRequest, bus_run: str | None,
                     usage_run: str | None) -> Iterator[str]:
        return self._billed_stream(req, bus_run, usage_run)

    def _billed_stream(self, req: GenerateRequest, bus_run: str | None,
                       usage_run: str | None) -> Iterator[str]:
        def scope() -> ExitStack:
            st = ExitStack()
            st.enter_context(bus.scoped(bus_run))
            st.enter_context(usage.scoped(usage_run))
            return st

        call_id = _next_call_id()
        model = self.model_for(req)
        with scope():
            _emit_call("start", call_id, req.agent, self.name, model,
                       stream=True)
        started = time.perf_counter()
        wait_ms = 0.0
        parts: list[str] = []
        end: StreamEnd | None = None
        attempt = 0
        settled = False

        def settle(*, ok: bool, error: str | None = None) -> None:
            """한 번만 청구·기록한다. 예외 경로가 겹쳐도 두 번은 없다."""
            nonlocal settled
            if settled:
                return
            settled = True
            total = (time.perf_counter() - started) * 1000
            with scope():
                if not parts and not (ok and end is not None):
                    usage.record_failure(req.agent, total)
                    _emit_call("end", call_id, req.agent, self.name, model,
                               ok=False, ms=total, wait_ms=wait_ms,
                               attempts=attempt + 1, stream=True,
                               error=error or "Empty")
                    return
                u = end.usage if end is not None else self._estimate(req, parts)
                result = GenerateResult(
                    text="".join(parts), provider=self.name,
                    model=(end.model if end and end.model else model),
                    usage=u, attempts=attempt + 1,
                    stop_reason=end.stop_reason if end else None)
                self._bill(req, result, latency_ms=total, wait_ms=wait_ms)
                extra = {"error": error} if error else {}
                _emit_call("end", call_id, req.agent, self.name, result.model,
                           ok=ok, ms=total, wait_ms=wait_ms,
                           attempts=attempt + 1, stream=True,
                           estimated=end is None, input=u.input_tokens,
                           output=u.output_tokens, cached=u.cached_tokens,
                           **extra)

        try:
            while True:
                it = self._stream(req)
                try:
                    for item in it:
                        if isinstance(item, StreamEnd):
                            end = item
                            continue
                        if item:
                            parts.append(item)
                            yield item
                    break
                except ProviderError as e:
                    if parts or not e.retryable or attempt >= config.MAX_RETRY:
                        settle(ok=False, error=type(e).__name__)
                        raise
                    delay = backoff_delay(attempt, getattr(e, "retry_after", None))
                    with scope():
                        bus.say("SYSTEM",
                                lang.t("log.retry", who=self.name,
                                       delay=f"{delay:.1f}", n=attempt + 1,
                                       max=config.MAX_RETRY,
                                       why=type(e).__name__),
                                kind="error")
                    w0 = time.perf_counter()
                    _sleep(delay)
                    wait_ms += (time.perf_counter() - w0) * 1000
                    attempt += 1
                finally:
                    close = getattr(it, "close", None)
                    if close is not None:
                        close()
            settle(ok=True)
        except GeneratorExit:
            # 소비자가 도중에 그만 읽었다. 만든 만큼은 이미 나갔다.
            settle(ok=False, error="Closed")
            raise
        except BaseException as e:
            settle(ok=False, error=type(e).__name__)
            raise

    @staticmethod
    def _estimate(req: GenerateRequest, parts: list[str]) -> Usage:
        """제공자가 사용량을 안 알려줬을 때의 어림 (4글자 ≈ 1토큰).

        실제보다 적게 잡힐 수 있다는 것을 안다. 그래도 0 보다는 진실에
        가깝고, 호출 기록에 `estimated` 로 남으므로 어림인 줄 안다.
        """
        prompt = req.system + "".join(m.content for m in req.messages)
        return Usage(input_tokens=max(1, len(prompt) // 4),
                     output_tokens=max(1, len("".join(parts)) // 4))

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

    def _bill(self, req: GenerateRequest, result: GenerateResult, *,
              latency_ms: float = 0.0, wait_ms: float = 0.0) -> None:
        u = result.usage
        usage.record(req.agent, result.model,
                     input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                     cached_tokens=u.cached_tokens, cache_written=u.cache_written,
                     latency_ms=latency_ms, wait_ms=wait_ms,
                     retries=max(0, result.attempts - 1))

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
        """앞이 **첫 조각 전에** 쓰러지면 뒤로 넘긴다.

        조각을 이미 내보낸 뒤라면 넘기지 않는다 — 다른 모델이 이어 쓰면
        한 답에 두 목소리가 섞인다. 청구는 각 제공자의 `stream()` 이 한다.
        """
        usable = self._usable()
        if not usable:
            raise ProviderUnavailable(
                lang.t("prov.none", name=self.name), provider=self.name)
        # 실행 범위는 **지금** 이 스레드에서 잡는다 — 제너레이터 안에서
        # 각 제공자의 `stream()` 을 부르면 늦다(`AIProvider.stream` 참조).
        return self._open_stream(req, bus.current(), usage.current())

    def _open_stream(self, req: GenerateRequest, bus_run: str | None,
                     usage_run: str | None) -> Iterator[str]:
        return self._fallback_stream(req, self._usable(), bus_run, usage_run)

    def _fallback_stream(self, req: GenerateRequest, usable: list[AIProvider],
                         bus_run: str | None,
                         usage_run: str | None) -> Iterator[str]:
        last: ProviderError | None = None
        for p in usable:
            started = False
            try:
                for chunk in p._open_stream(req, bus_run, usage_run):
                    started = True
                    yield chunk
                return
            except ProviderError as e:
                if started:
                    raise
                last = e
                with bus.scoped(bus_run):
                    bus.say("SYSTEM",
                            lang.t("log.fallback", who=p.name,
                                   why=type(e).__name__), kind="error")
        raise last or ProviderUnavailable(lang.t("prov.allFailed"),
                                          provider=self.name)

    # 추상 메서드 충족용 — 이 클래스는 위임만 하므로 직접 호출되지 않는다.
    def _generate(self, req: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    def _stream(self, req: GenerateRequest) -> Iterator[str | StreamEnd]:
        raise NotImplementedError
