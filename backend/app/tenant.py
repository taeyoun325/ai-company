"""테넌트 자세 — **어느 키로 호출하는가**를 한 곳에서 정한다 (DAY 19).

## 왜 이 파일이 생겼나

요금제가 셋일 때는 "얼마를 주느냐"만 달랐다. BYOK 를 넣는 순간 **호출
경로 자체가** 요금제마다 달라진다:

| source | 키 | 크레딧 |
|---|---|---|
| `none` (요금제 미선택) | 없음 — 아무것도 시작할 수 없다 | 해당 없음 |
| `mock` | 없음 — 실제 호출을 하지 않는다 | 차감 없음 (원가 0) |
| `byok` (자체 키) | 고객의 키 | 차감 없음 — **고객이 직접 낸다** |
| `platform` (유료) | 운영자의 키 | 차감 |

이 분기가 코드 여기저기로 퍼지면, 한 군데만 빠뜨려도 **무료 사용자가
우리 키를 태우거나, BYOK 사용자의 요금을 우리가 낸다.** 둘 다 조용히
일어나고 청구서로만 드러난다. 그래서 분기는 여기 하나뿐이다.

## 어떻게 강제되나

`bind()` 가 컨텍스트 변수를 세우고, 그걸 읽는 곳은 둘뿐이다:

- `secrets_broker.get()` — BYOK 면 **고객 키만** 준다. 운영자 키로
  넘어가지 않는다. 없으면 없는 것이다.
- `providers.registry.mode()` — `mock` 자세면 Mock 을 강제한다.

이렇게 두면 "키를 넘기는 걸 깜빡한 호출 경로"가 우리 키를 쓰는 사고가
되지 않는다. 자세를 세우지 않은 경로는 기본값(`platform`)으로 돌고,
그건 지금까지의 동작 그대로다 — 로컬 개발이 안 깨진다.

## 스레드

실행은 별도 스레드에서 돈다(`orchestrator/engine.py`). 컨텍스트 변수는
스레드를 자동으로 따라가지 **않으므로**, 스레드 안에서 다시 세운다.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field

from app import byok

SOURCES = ("platform", "byok", "mock", "none")


class KeysMissing(RuntimeError):
    """BYOK 요금제인데 고객 키가 없다. 우리 키로 대신 부르지 않는다."""


class NoPlan(RuntimeError):
    """요금제를 고르지 않았다.

    무료 요금제가 없으므로 계정을 만든 직후의 상태다. Mock 으로 돌려주지
    **않는다** — 그건 없앤 무료 요금제를 이름만 바꿔 되살리는 것이고,
    사용자는 대본이 지어낸 산출물을 제품의 실력으로 읽는다.
    """


@dataclass(frozen=True)
class Posture:
    owner: str = "local"
    plan: str = "platform"
    source: str = "platform"
    keys: dict[str, str] = field(default_factory=dict)

    @property
    def charge_credits(self) -> bool:
        """크레딧을 깎는가. 우리 키로 나간 비용만 깎는다."""
        return self.source == "platform"


_current: contextvars.ContextVar[Posture | None] = contextvars.ContextVar(
    "tenant_posture", default=None)


def current() -> Posture | None:
    return _current.get()


def source_of(plan_name: str) -> str:
    """요금제가 선언한 호출 경로. 모르는 값은 `platform` 으로 읽지 않는다 —
    오타 하나가 조용히 우리 키를 태우는 쪽이 되면 안 된다."""
    from app.usage import credits
    src = str(credits.plan(plan_name).get("source", "platform"))
    return src if src in SOURCES else "mock"


def posture_for(owner: str) -> Posture:
    from app.usage import credits
    plan_name = credits.wallet(owner).plan
    src = source_of(plan_name)
    keys = byok.keys_of(owner) if src == "byok" else {}
    return Posture(owner=owner, plan=plan_name, source=src, keys=keys)


def require_runnable(owner: str) -> Posture:
    """실행을 시작하기 전에 이 테넌트가 돌 수 있는지 본다.

    BYOK 인데 키가 없으면 **시작 자체를 거부한다.** 중간에 터지면 절반쯤
    만들어진 프로젝트와 함께 "왜 멈췄는지 모르겠는" 화면이 남는다.
    """
    p = posture_for(owner)
    from app import lang
    if p.source == "none":
        raise NoPlan(lang.t("plan.required"))
    if p.source == "byok":
        missing = byok.missing(owner)
        if missing:
            from app import secrets_broker
            labels = ", ".join(secrets_broker.KEYS[n][1] for n in missing)
            raise KeysMissing(lang.t("byok.missing", keys=labels))
    return p


@contextmanager
def bind(owner: str, posture: Posture | None = None):
    """이 블록 안의 모든 모델 호출이 이 테넌트의 자세로 돈다."""
    token = _current.set(posture or posture_for(owner))
    try:
        yield _current.get()
    finally:
        _current.reset(token)


def describe(owner: str) -> dict:
    """화면이 "지금 누구 키로 도는가"를 말할 수 있어야 한다."""
    p = posture_for(owner)
    return {"plan": p.plan, "source": p.source,
            "charge_credits": p.charge_credits,
            "byok_ready": byok.ready(owner) if p.source == "byok" else None}
