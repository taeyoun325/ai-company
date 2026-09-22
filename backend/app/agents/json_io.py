"""모델이 낸 글에서 JSON 을 꺼내 스키마로 검증한다 (지시서 §8).

## 왜 제공자별 구조화 출력 API 를 안 쓰나

Anthropic 에는 `messages.parse` 가 있고 Google·OpenAI 는 모양이 다르다.
제공자마다 다른 길로 가면 §7 어댑터를 둔 의미가 사라진다 — 계약 테스트가
제공자별로 갈라지고, 제공자를 하나 추가할 때마다 직원 코드를 고쳐야 한다.
그래서 **모든 제공자에 똑같이** JSON 을 글로 요구하고 글에서 파싱한다.

대가는 파싱 실패 가능성이다. 그래서 세 겹으로 막는다:
1. 스키마를 프롬프트에 그대로 박는다 (`schema_block`)
2. 코드펜스·앞뒤 잡담을 걷어내고 균형 잡힌 첫 객체만 꺼낸다
3. 실패하면 **오류 원문을 되돌려주고 한 번 더** 시킨다 (`app/agents/employee.py`)

## 실패를 조용히 삼키지 않는다

빈 객체나 기본값으로 때우면 오케스트레이터는 "계획이 세워졌는데 태스크가
0개"라는 상태를 정상으로 읽고 그대로 완료 처리한다. 파싱 실패는 실패다.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app import lang

T = TypeVar("T", bound=BaseModel)

_FENCE_OPEN = re.compile(r"```[a-zA-Z]*[ \t]*\r?\n")


class ParseFailed(ValueError):
    """모델의 답을 스키마로 읽지 못했다. 메시지를 그대로 모델에 돌려준다."""


def extract_json(text: str) -> str:
    """글에서 JSON 객체 하나를 꺼낸다.

    코드펜스가 있으면 그 안을 먼저 본다. 없으면 첫 `{` 부터 **괄호가 균형을
    이루는 지점**까지 자른다 — `rfind('}')` 로 자르면 뒤에 붙은 설명 안의
    중괄호까지 삼켜서, 멀쩡한 JSON 을 깨진 것으로 만든다.
    """
    # 코드펜스는 **시작 지점**을 찾는 데만 쓴다. 닫는 펜스로 끝을 자르면,
    # JSON 문자열 값 안에 코드펜스가 들어 있을 때 거기서 끊긴다 — 문서나
    # 코드를 내보내는 직원(writer·developer)의 응답은 거의 항상 그렇다.
    # 끝은 아래의 괄호 균형 스캔이 정한다. 그쪽은 문자열 안을 구분한다.
    m = _FENCE_OPEN.search(text)
    search_from = m.end() if m else 0

    start = text.find("{", search_from)
    if start == -1:
        start = text.find("{")
    if start == -1:
        raise ParseFailed(lang.t("json.noObject"))

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ParseFailed(lang.t("json.unclosed"))


def parse(text: str, schema: type[T]) -> T:
    raw = extract_json(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ParseFailed(lang.t("json.syntax", msg=e.msg, line=e.lineno,
                                 col=e.colno)) from e
    if not isinstance(data, dict):
        raise ParseFailed(lang.t("json.notObject"))
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        raise ParseFailed(lang.t("json.schema", errors=_errors(e))) from e


def _errors(e: ValidationError) -> str:
    """모델이 읽고 고칠 수 있는 형태로 줄인다. 전문을 그대로 주면 길기만 하다."""
    lines = []
    for err in e.errors()[:12]:
        where = ".".join(str(p) for p in err["loc"]) or "(최상위)"
        lines.append(f"- {where}: {err['msg']}")
    return "\n".join(lines)


def schema_block(schema: type[BaseModel]) -> str:
    """프롬프트에 넣을 스키마 설명.

    `description` 을 살려서 넣는다 — 필드 이름만 주면 모델이 의미를 짐작하고,
    짐작은 틀린다.
    """
    return json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)


INSTRUCTION = (
    "답변은 **JSON 객체 하나**로만 내보내세요. 설명·인사말·코드펜스 밖의 글을 "
    "붙이지 마세요. 스키마에 없는 필드를 넣으면 거부됩니다.\n\n"
    "## 출력 스키마: {name}\n\n```json\n{schema}\n```"
)

# 스키마 이름을 헤더로 따로 적는 이유: JSON Schema 안의 첫 `"title"` 은
# 최상위가 아니라 `$defs` 안의 필드일 수 있다. 이름을 찾으려고 스키마 본문을
# 뒤지면 엉뚱한 것을 집는다 — 이름은 이름 자리에 적는다.
NAME_HEADER = "## 출력 스키마: "


def render_instruction(schema: type[BaseModel]) -> str:
    return INSTRUCTION.format(name=schema.__name__, schema=schema_block(schema))
