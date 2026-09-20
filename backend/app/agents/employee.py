"""직원 한 명을 실제로 부르는 곳 (지시서 §8).

## 이 파일이 하는 일

직원 정의(`roles.py`) + 제공자(`providers/registry.py`) + 계약(`schemas.py`)
을 하나로 묶는다. 오케스트레이터는 이 모듈의 `ask()` 하나만 알면 된다.

## 왜 파싱 실패에 복구 경로를 두나

JSON 을 글로 요구하는 이상(→ `json_io.py`) 실패는 반드시 일어난다.
실패를 그대로 올리면 실행이 통째로 죽고, 조용히 빈 값으로 때우면
"태스크 0개짜리 계획"이 정상처럼 흘러간다. 그래서 **오류 원문을 모델에
그대로 돌려주고 한 번 더** 시킨다. 그래도 안 되면 실패로 올린다.

한 번만 다시 시키는 이유: 두 번 같은 실수를 하는 모델은 세 번째에도 한다.
그 사이 비용은 CEO 가 낸다.

## 사용량은 누구 앞으로 다는가

`GenerateRequest.agent` 에 **직원 id** 를 넣는다. `usage` 가 그 키로 센다.
여기서 빠뜨리면 그 직원의 비용이 통째로 사라진다(§14).
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

from pydantic import BaseModel

from app import bus, config
from app.agents import json_io, roles
from app.agents.roles import Employee
from app.providers import registry
from app.providers.base import GenerateRequest, Message, ProviderError

T = TypeVar("T", bound=BaseModel)

REPAIR_ATTEMPTS = 1          # 파싱 실패 시 다시 시킬 횟수


class EmployeeFailed(RuntimeError):
    """그 직원으로는 이 일을 끝낼 수 없다. 오케스트레이터가 판단한다."""

    def __init__(self, employee: str, message: str, *, cause: BaseException | None = None):
        super().__init__(f"{employee}: {message}")
        self.employee = employee
        self.cause = cause


def provider_of(e: Employee):
    return registry.get(e.provider)


def is_mock(e: Employee) -> bool:
    """이 직원이 지금 Mock 으로 일하고 있는가. 화면이 표시해야 한다."""
    return registry.is_mock(e.provider)


def _request(e: Employee, user: str, schema: type[BaseModel] | None,
             history: list[Message] | None = None) -> GenerateRequest:
    system = e.system
    if schema is not None:
        system = f"{system}\n\n{json_io.render_instruction(schema)}"
    messages = [*(history or []), Message("user", user)]
    return GenerateRequest(
        system=system, messages=messages, model=e.model,
        max_tokens=e.max_tokens, temperature=e.temperature,
        agent=e.id,                      # ← 사용량이 이 키로 잡힌다 (§14)
    )


def say(e: Employee, text: str, kind: str = "say") -> None:
    bus.say(e.id, text, kind=kind)


def ask(employee_id: str, user: str, schema: type[T],
        history: list[Message] | None = None) -> T:
    """직원에게 일을 시키고 스키마로 검증된 답을 받는다."""
    e = roles.get(employee_id)
    p = provider_of(e)
    req = _request(e, user, schema, history)

    last_error: str | None = None
    for attempt in range(REPAIR_ATTEMPTS + 1):
        if last_error is not None:
            # 오류 원문을 그대로 돌려준다. '다시 해보세요'만으로는 같은 실수를 한다.
            req = _request(
                e,
                f"직전 응답을 스키마로 읽지 못했습니다.\n\n"
                f"## 오류\n{last_error}\n\n"
                f"## 다시 할 것\n같은 요청에 대해 **JSON 객체 하나만** 내보내세요. "
                f"위 오류가 가리키는 필드를 고치세요.\n\n"
                f"## 원래 요청\n{user}",
                schema, history)
        try:
            result = p.generate(req)
        except ProviderError as ex:
            raise EmployeeFailed(e.id, str(ex), cause=ex) from ex

        try:
            return json_io.parse(result.text, schema)
        except json_io.ParseFailed as ex:
            last_error = str(ex)
            if attempt >= REPAIR_ATTEMPTS:
                break
            bus.say("SYSTEM",
                    f"{e.name}({e.role})의 답을 읽지 못해 형식을 고쳐 다시 요청합니다 — "
                    f"{last_error.splitlines()[0]}", kind="error")

    raise EmployeeFailed(e.id, f"응답을 스키마로 읽지 못했습니다.\n{last_error}")


def ask_text(employee_id: str, user: str,
             history: list[Message] | None = None) -> str:
    """구조화가 필요 없는 한마디. MANUAL 모드의 직접 지시에 쓴다(§11)."""
    e = roles.get(employee_id)
    try:
        return provider_of(e).generate(_request(e, user, None, history)).text
    except ProviderError as ex:
        raise EmployeeFailed(e.id, str(ex), cause=ex) from ex


def stream_text(employee_id: str, user: str,
                history: list[Message] | None = None) -> Iterator[str]:
    """조각을 흘린다. 스트리밍은 재시도하지 않는다(§18) — 같은 문장이 두 번 보인다."""
    e = roles.get(employee_id)
    try:
        yield from provider_of(e).stream(_request(e, user, None, history))
    except ProviderError as ex:
        raise EmployeeFailed(e.id, str(ex), cause=ex) from ex


def status(run: str | None = None) -> list[dict]:
    """화면이 그릴 직원 현황 (§8 · §4 가상 사무실).

    `mock` 이 True 인데 화면이 그걸 안 보여주면, 사용자는 Mock 이 지어낸
    글을 AI 직원의 작업 결과로 믿는다.

    `run` 을 받는 이유: 사용량은 **실행별**로 스레드 로컬에 묶여 있다(§14).
    HTTP 요청은 다른 스레드에서 처리되므로, run 을 안 주면 그 스레드에는
    아무 실행도 묶여 있지 않아 전부 0 으로 나온다. 화면에는 "아직 아무도
    일하지 않음"으로 보이고, 실제로는 한창 일하는 중이다.
    """
    from app import usage
    per = usage.agents_of(run)
    out = []
    for e in roles.EMPLOYEES.values():
        row = e.info()
        row["mock"] = is_mock(e)
        row["usage"] = per.get(e.id, {})
        out.append(row)
    return out


def worst_case_cost(employee_id: str) -> float:
    """이 직원을 한 번 부를 때의 최악 비용($).

    호출 *전에* 예산을 검사하려면 필요하다. 사후 감지는 상한이 아니라 부고다.
    입력은 넉넉히 잡고, 출력은 max_tokens 를 다 쓴다고 본다.
    """
    e = roles.get(employee_id)
    worst_input = 80_000 if e.kind in ("build", "verify") else 40_000
    return config.price_of(e.model, worst_input, e.max_tokens)


def max_worst_case() -> float:
    """직원 중 **한 번 부를 때 가장 비싼** 사람의 최악 비용($).

    실행을 시작해도 되는지 판단할 때 쓴다. 프로젝트 상한 전액을 미리
    잡아두면, 무료 요금제처럼 월 한도와 상한이 같은 경우 한 달에 한 번만
    시작할 수 있게 된다 — 그건 상한이 아니라 횟수 제한이다.
    한 번 부를 돈이 있으면 시작은 시킨다. 도중에 모자라면 `_spend_guard`
    가 단계 경계에서 멈춘다.
    """
    return max(worst_case_cost(i) for i in roles.ids())
