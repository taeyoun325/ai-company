"""Mock 제공자 — 키 없이 전 구간을 만들기 위한 것 (지시서 §1).

## 이건 임시방편이 아니다

현재 방침은 "API 키는 제작을 마친 뒤 맨 마지막에" 이다. 그러면 DAY 13까지
**모든 코드가 이 제공자 위에서만 돌아간다.** 마지막 날 키를 꽂았을 때
터지지 않으려면, Mock 은 실제 제공자와 **같은 계약 테스트를 통과해야 한다**
(`backend/tests/test_providers.py`).

## 결정적(deterministic)인 이유

같은 요청에 같은 답을 준다. 테스트가 흔들리지 않아야 하고, 화면을 고칠 때
매번 다른 글이 나오면 무엇이 바뀐 건지 알 수 없기 때문이다.

## 실패를 일부러 낼 수 있는 이유

재시도·백오프·대체 제공자(§18)는 **키가 있어야만 시험할 수 있는 것이 아니다.**
오히려 실제 API 로는 429 나 5xx 를 원할 때 만들 수 없다. 여기서 만든다.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.providers.base import (AIProvider, GenerateRequest, GenerateResult,
                                ProviderError, Usage)

CHARS_PER_TOKEN = 4          # 거친 어림. 실제 토크나이저가 아니다.


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Failure:
    """앞의 `times` 번 호출을 `error` 로 실패시킨다.

    times=0 이면 실패하지 않는다. 무한히 실패시키려면 times 를 크게 준다.
    """
    error: type[ProviderError] = ProviderError
    times: int = 1
    message: str = "가짜 실패"
    _count: int = 0

    def next(self, provider: str) -> ProviderError | None:
        if self._count >= self.times:
            return None
        self._count += 1
        return self.error(f"{self.message} ({self._count}/{self.times})",
                          provider=provider)

    def reset(self) -> None:
        self._count = 0


Responder = Callable[[GenerateRequest], str]


def _default_responder(req: GenerateRequest) -> str:
    """요청에서 결정적으로 뽑아낸 그럴듯한 답.

    내용은 가짜지만 *모양*은 진짜와 같아야 한다 — 화면과 파서가 이것을 보고
    만들어지기 때문이다. 그래서 짧은 문단 몇 개를 낸다.
    """
    seed = hashlib.sha256(
        (req.system + "|" + "|".join(f"{m.role}:{m.content}" for m in req.messages))
        .encode("utf-8")).hexdigest()
    ask = req.last_user_text.strip().replace("\n", " ")
    if len(ask) > 90:
        ask = ask[:90] + "…"
    return (
        f"[MOCK:{seed[:8]}] 요청을 확인했습니다 — \"{ask}\"\n\n"
        f"1. 무엇을 만들지 정리했습니다.\n"
        f"2. 필요한 단계를 {1 + int(seed[:2], 16) % 4}개로 쪼갰습니다.\n"
        f"3. 끝나면 검증자에게 넘기겠습니다.\n\n"
        f"(이 응답은 Mock 제공자가 만든 것입니다. 실제 모델이 아닙니다.)"
    )


class MockProvider(AIProvider):
    """키 없이 동작하는 제공자.

    latency 를 주면 실제처럼 느리게 만든다 — 화면의 진행 표시가 0초에
    끝나버리면 그게 제대로 보이는지 확인할 수 없기 때문이다.
    테스트에서는 기본값 0 으로 둔다.
    """

    def __init__(self, name: str = "mock", model: str = "mock",
                 latency: float = 0.0, responder: Responder | None = None,
                 failure: Failure | None = None):
        self.name = name
        self.default_model = model
        self.latency = latency
        self.responder = responder or _default_responder
        self.failure = failure
        self.calls: list[GenerateRequest] = []   # 테스트가 들여다본다

    def available(self) -> bool:
        return True                              # 키가 필요 없다. 그게 요점이다.

    def _maybe_fail(self) -> None:
        if self.failure and (err := self.failure.next(self.name)):
            raise err

    def _generate(self, req: GenerateRequest) -> GenerateResult:
        self.calls.append(req)
        self._maybe_fail()
        if self.latency:
            time.sleep(self.latency)
        text = self.responder(req)
        prompt = req.system + "".join(m.content for m in req.messages)
        return GenerateResult(
            text=text,
            model=self.model_for(req),
            provider=self.name,
            usage=Usage(input_tokens=estimate_tokens(prompt),
                        output_tokens=estimate_tokens(text)),
            stop_reason="end_turn",
        )

    def _stream(self, req: GenerateRequest) -> Iterator[str]:
        """조각을 다 이으면 `_generate` 의 text 와 **정확히** 같아야 한다.

        계약 테스트가 이것을 확인한다. 어긋나면 화면에 보인 글과 저장된 글이
        달라지는데, 그건 디버깅하기 가장 고약한 종류의 버그다.
        """
        result = self._generate(req)
        text = result.text
        step = 24
        for i in range(0, len(text), step):
            if self.latency:
                time.sleep(self.latency / 8)
            yield text[i:i + step]

    def reset(self) -> None:
        self.calls.clear()
        if self.failure:
            self.failure.reset()
