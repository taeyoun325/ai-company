"""제공자 선택 — 키 유무에 따른 교체를 여기 한 곳에 가둔다.

## 왜 한 곳인가

`if has_key: ... else: mock` 이 코드 곳곳에 퍼지면, 마지막 날 키를 꽂는 일이
설정 변경이 아니라 개조 공사가 된다. 분기는 여기서만 한다.

## 모드 (환경변수 `PROVIDER_MODE`)

| 값 | 뜻 |
|---|---|
| `auto` (기본) | 키가 있으면 실제, 없으면 Mock |
| `mock` | 키가 있어도 Mock. 비용 없이 화면·흐름을 만들 때 |
| `real` | Mock 으로 떨어지지 않는다. 키가 없으면 **실패한다** |

`real` 이 따로 있는 이유: 배포 환경에서 키 설정이 빠졌을 때 조용히 Mock 으로
돌아가면, 가짜 결과물이 진짜처럼 사용자에게 간다. 그건 버그가 아니라 사고다.

## Mock 으로 fallback 하지 않는 이유

`FallbackProvider` 의 뒤에는 **실제 제공자만** 세운다(예: Claude → Gemini).
실제 호출이 실패했을 때 Mock 이 받아주면, 실패가 성공처럼 보이고 사용자는
Mock 이 지어낸 글을 AI 의 작업 결과로 받는다. 실패는 실패로 보여야 한다.
Mock 은 "아무 키도 없을 때" 또는 "일부러 mock 모드일 때"만 쓴다.
"""
from __future__ import annotations

import os
import threading

from app import config

from app.providers.base import AIProvider, FallbackProvider, ProviderUnavailable
from app.providers.claude import ClaudeProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider

MODES = ("auto", "mock", "real")

_lock = threading.RLock()
_real: dict[str, AIProvider] = {}
_mocks: dict[str, MockProvider] = {}

# 실제 제공자 생성자.
_FACTORIES: dict[str, callable] = {
    "claude": ClaudeProvider,
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}

# 대체 순서 (§18). 실제 → 실제 만 적는다. Mock 은 여기 오지 않는다.
#
# 사슬을 **회사가 다른 쪽으로** 건다. 한 회사가 장애면 그 회사의 다른 모델도
# 같이 죽는 경우가 많으므로, 같은 회사 안에서 넘기는 것은 대체가 아니라
# 같은 문을 두 번 두드리는 것이다.
#
# 검증자(gemini)의 대체에 claude 를 두지 **않는다**: 구현이 Claude 인데
# 검증까지 Claude 로 넘어가면 교차검증이라는 전제가 조용히 사라진다.
# 그건 "느리게라도 돌아감"이 아니라 "검증한 척"이다. 차라리 멈춘다.
_FALLBACKS: dict[str, tuple[str, ...]] = {
    "claude": ("openai",),
    "gemini": (),
    "openai": ("claude",),
}


def mode() -> str:
    m = os.getenv("PROVIDER_MODE", "auto").strip().lower()
    return m if m in MODES else "auto"


def names() -> list[str]:
    return sorted(_FACTORIES)


def _real_provider(name: str) -> AIProvider:
    with _lock:
        if name not in _real:
            if name not in _FACTORIES:
                raise ProviderUnavailable(f"알 수 없는 제공자: {name}", provider=name)
            _real[name] = _FACTORIES[name]()
        return _real[name]


def _mock_provider(name: str) -> MockProvider:
    with _lock:
        if name not in _mocks:
            real_model = _FACTORIES[name]().default_model if name in _FACTORIES else name
            # 모델 이름을 실제와 같게 둔다 — 화면과 사용량 집계가 실제와 같은
            # 모양으로 움직여야 마지막 날 바꿔 끼울 때 차이가 안 난다.
            _mocks[name] = MockProvider(name=f"mock:{name}", model=real_model)
        return _mocks[name]


def is_mock(name: str) -> bool:
    """이 제공자가 지금 Mock 으로 동작하는가. 화면이 이걸 표시해야 한다."""
    m = mode()
    if m == "mock":
        return True
    if m == "real":
        return False
    return not _real_provider(name).available()


def get(name: str) -> AIProvider:
    """이름으로 제공자를 얻는다. 모드와 키 상태에 따라 실제/Mock 이 정해진다."""
    m = mode()
    if name == "mock":
        return _mock_provider("claude")
    if name not in _FACTORIES:
        raise ProviderUnavailable(f"알 수 없는 제공자: {name}", provider=name)
    if m == "mock":
        return _mock_provider(name)

    primary = _real_provider(name)
    if m == "real":
        if not primary.available():
            raise ProviderUnavailable(
                f"PROVIDER_MODE=real 인데 {name} 키가 없습니다. "
                f"Mock 으로 대신하지 않습니다.", provider=name)
        return _chain(name, primary)

    # auto
    if primary.available():
        return _chain(name, primary)
    return _mock_provider(name)


def _chain(name: str, primary: AIProvider) -> AIProvider:
    """쓸 수 있는 실제 대체 제공자가 있으면 묶는다."""
    backups = [_real_provider(n) for n in _FALLBACKS.get(name, ())
               if n in _FACTORIES and _real_provider(n).available()]
    return FallbackProvider(primary, *backups) if backups else primary


def reset() -> None:
    """키나 모드가 바뀌면 부른다. 다음 호출에 다시 판단한다."""
    with _lock:
        _real.clear()
        _mocks.clear()


def status() -> dict:
    """화면에 내려보낼 제공자 현황.

    `mock` 이 True 인데 그 사실을 화면이 안 보여주면, 사용자는 Mock 이
    지어낸 글을 AI 의 작업 결과로 믿는다.
    """
    rows = []
    for name in names():
        p = _real_provider(name)
        rows.append({
            "name": name,
            "model": p.default_model,
            "key": p.available(),
            "mock": is_mock(name),
            "fallbacks": list(_FALLBACKS.get(name, ())),
            "models": config.models_of(name),
        })
    return {
        "mode": mode(),
        "providers": rows,
        "any_real": any(r["key"] for r in rows),
        "all_mock": all(r["mock"] for r in rows) if rows else True,
        # 교차검증이 성립하는가 (§8). 구현자와 검증자가 같은 회사면 이 제품의
        # 핵심 논리가 사라지므로, 화면이 그 사실을 말할 수 있어야 한다.
        "cross_check": _cross_check_ok(rows),
    }


def _cross_check_ok(rows: list[dict]) -> bool:
    live = {r["name"] for r in rows if r["key"] and not r["mock"]}
    return "claude" in live and "gemini" in live
