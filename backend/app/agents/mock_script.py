"""Mock 직원 대본 — 키 없이 회사 전체를 돌리기 위한 것 (지시서 §1).

## 이건 임시방편이 아니다

방침상 API 키는 맨 마지막에 들어온다. 그러면 DAY 13까지 오케스트레이터·
화면·저장·과금이 **전부 이 대본 위에서만** 돌아간다. 그러니 대본은
"그럴듯한 글"이 아니라 **스키마를 지키는 진짜 응답**이어야 한다.
JSON 이 깨지면 그건 Mock 의 문제가 아니라, 우리가 만든 파서와 복구
경로가 한 번도 제대로 시험되지 않았다는 뜻이다.

## 어떻게 스키마를 아는가

`employee.ask()` 가 시스템 프롬프트에 `## 출력 스키마: Plan` 헤더를 넣는다.
그 한 줄을 읽는다. 제공자 인터페이스를 바꾸지 않아도 되고(§7), 실제 제공자가
보는 것과 **같은 프롬프트**를 보게 된다.

(스키마 본문의 첫 `"title"` 을 읽지 않는다 — 그건 최상위가 아니라 `$defs`
안의 필드일 수 있다. 실제로 처음엔 그렇게 짰다가 `"Id"` 를 집었다.)

## 결정적이다

같은 입력에 같은 답. 화면을 고칠 때마다 다른 글이 나오면 무엇이 바뀐
건지 알 수 없고, 테스트는 흔들린다. 재작업 분기도 난수가 아니라
**입력에 반려 사유가 들어 있는가**로 가른다.
"""
from __future__ import annotations

import json
import re

from app.agents import json_io
from app.providers.base import GenerateRequest

_TITLE = re.compile(re.escape(json_io.NAME_HEADER) + r"([A-Za-z]+)")

# 반려 사유가 프롬프트에 들어오면 '고친 버전'을 낸다. 난수가 아니라 입력으로 가른다.
_REWORK_MARK = "반려"


def _schema_name(req: GenerateRequest) -> str | None:
    m = _TITLE.search(req.system)
    return m.group(1) if m else None


def _j(obj: dict) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"


def _requirement(req: GenerateRequest) -> str:
    text = req.last_user_text
    m = re.search(r"# 의뢰인 요구사항\n(.+)", text)
    line = (m.group(1) if m else text).strip().splitlines()[0]
    return line[:80]


# ── 각 스키마의 대본 ────────────────────────────────────────────────
def _plan(req: GenerateRequest) -> dict:
    return {
        "message_to_team": "요구사항을 인수기준 3개와 태스크 3개로 정리했습니다.",
        "project_name": "mock-project",
        "acceptance_criteria": [
            {"id": "ac1", "text": "add, sub, mul, div 네 함수가 정상 동작한다"},
            {"id": "ac2", "text": "0으로 나누면 ValueError를 발생시킨다"},
            {"id": "ac3", "text": "README 에 네 함수의 사용법이 적혀 있다"},
        ],
        "tasks": [
            {"id": "t1", "title": "사칙연산 네 함수 구현", "assignee": "developer",
             "deps": [], "files": ["src/calc.py"], "covers": ["ac1", "ac2"],
             "done_when": "네 함수를 import 할 수 있고 div(1,0)이 ValueError를 낸다"},
            {"id": "t2", "title": "사용법 문서", "assignee": "writer",
             "deps": ["t1"], "files": ["docs/README.md"], "covers": ["ac3"],
             "done_when": "네 함수의 시그니처와 예시가 문서에 있다"},
            {"id": "t3", "title": "결과 화면 명세", "assignee": "designer",
             "deps": ["t1"], "files": ["design/screen.md"], "covers": [],
             "done_when": "비어 있음·불러오는 중·실패 세 상태가 명세되어 있다"},
        ],
    }


_CALC_BAD = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    "def div(a, b):\n    return a / b\n"
)
_CALC_GOOD = _CALC_BAD.replace(
    "def div(a, b):\n    return a / b\n",
    'def div(a, b):\n    if b == 0:\n        raise ValueError("0으로 나눌 수 없습니다")\n'
    "    return a / b\n")


def _work(req: GenerateRequest) -> dict:
    text = req.last_user_text
    fixed = _REWORK_MARK in text

    if "designer" in text or "design/" in text:
        return {
            "message_to_team": "결과 화면을 세 상태로 나눠 명세했습니다.",
            "files": [{"path": "design/screen.md", "content": (
                "# 결과 화면\n\n"
                "- 여백 16px · 본문 #111827 · 강조 #2563EB\n\n"
                "## 상태\n"
                "1. 비어 있음 — '계산할 식을 입력하세요'\n"
                "2. 불러오는 중 — 버튼 비활성 + 회전 표시\n"
                "3. 실패 — 붉은 배너(#DC2626)에 오류 문장 그대로\n")}],
            "summary": "결과 화면의 세 상태를 값으로 명세했다.",
            "self_check": "상태 3개를 모두 적었다. 실제 구현과 대조하지는 못했다.",
        }

    if "writer" in text or "docs/" in text:
        return {
            "message_to_team": "네 함수의 사용법을 예시와 함께 적었습니다.",
            "files": [{"path": "docs/README.md", "content": (
                "# calc\n\n"
                "사칙연산 네 함수.\n\n"
                "```python\n"
                "from calc import add, sub, mul, div\n\n"
                "add(2, 3)   # 5\n"
                "sub(5, 2)   # 3\n"
                "mul(3, 4)   # 12\n"
                "div(10, 4)  # 2.5\n"
                "```\n\n"
                "`div` 는 두 번째 인자가 0이면 `ValueError` 를 냅니다.\n")}],
            "summary": "네 함수의 시그니처와 예시를 문서에 적었다.",
            "self_check": "코드를 읽고 썼다. 실행해 보지는 않았다.",
        }

    return {
        "message_to_team": ("반려 사유대로 div 에 0 검사를 넣었습니다." if fixed
                            else "사칙연산 네 개 구현했습니다. 확인 부탁드립니다."),
        "files": [{"path": "src/calc.py",
                   "content": _CALC_GOOD if fixed else _CALC_BAD}],
        "summary": ("div 가 0 을 받으면 ValueError 를 내도록 고쳤다." if fixed
                    else "add·sub·mul·div 를 구현했다."),
        "self_check": ("0 나눗셈을 확인했다." if fixed
                       else "네 함수의 기본 동작만 확인했다. 예외 경로는 확인하지 못했다."),
    }


def _tests(req: GenerateRequest) -> dict:
    return {
        "message_to_team": "인수기준 3개 중 2개를 테스트로 묶었습니다. ac3 은 사람이 봐야 합니다.",
        "files": [{"path": "tests/test_calc.py", "covers": ["ac1", "ac2"], "content": (
            "import pytest\n\n"
            "from calc import add, sub, mul, div\n\n\n"
            "def test_basic():\n"
            "    assert add(2, 3) == 5\n"
            "    assert sub(5, 2) == 3\n"
            "    assert mul(3, 4) == 12\n"
            "    assert div(10, 4) == 2.5\n\n\n"
            "def test_div_zero_raises_value_error():\n"
            "    with pytest.raises(ValueError):\n"
            "        div(1, 0)\n")}],
        "uncovered": ["ac3"],
    }


def _verdict(req: GenerateRequest) -> dict:
    text = req.last_user_text
    # 테스트 리포트가 실패로 들어왔거나, 코드에 0 검사가 없으면 반려한다.
    failed = '"ok": false' in text.lower() or (
        "def div" in text and "ValueError" not in text)
    if failed:
        return {
            "message_to_team": "내가 쓴 테스트가 실패합니다. div 가 0 을 그대로 나눕니다 — ac2 위반이라 반려합니다.",
            "verdict": "fail", "severity": "major",
            "findings": [{"file": "src/calc.py", "issue": "0 나눗셈 미처리",
                          "why": "ac2 는 ValueError 를 요구하는데 ZeroDivisionError 가 난다"}],
            "required_fixes": ["div 에서 b == 0 이면 ValueError 를 발생시킬 것"],
        }
    return {
        "message_to_team": "테스트가 전부 통과하고 코드도 인수기준과 일치합니다. 통과.",
        "verdict": "pass", "severity": "none", "findings": [], "required_fixes": [],
    }


def _final(req: GenerateRequest) -> dict:
    return {
        "message_to_team": "인수기준 3개 전부 충족했습니다. 납품 가능합니다.",
        "summary": "src/calc.py · docs/README.md · design/screen.md 를 만들었고 테스트가 통과했습니다.",
        "met_criteria": ["ac1", "ac2", "ac3"],
        "unmet_criteria": [],
    }


def _routing(req: GenerateRequest) -> dict:
    text = req.last_user_text
    if any(k in text for k in ("문서", "글", "카피", "README")):
        return {"employee": "writer", "why": "문서 작업이라 작가에게 맡깁니다."}
    if any(k in text for k in ("화면", "디자인", "UI", "배치")):
        return {"employee": "designer", "why": "화면 명세라 디자이너에게 맡깁니다."}
    return {"employee": "developer", "why": "코드를 써야 하는 일이라 개발자에게 맡깁니다."}


_SCRIPTS = {
    "Plan": _plan,
    "WorkResult": _work,
    "TestSuite": _tests,
    "Verdict": _verdict,
    "FinalReport": _final,
    "Routing": _routing,
}


def responder(req: GenerateRequest) -> str:
    """`MockProvider` 에 꽂는 응답 함수."""
    name = _schema_name(req)
    script = _SCRIPTS.get(name or "")
    if script is None:
        # 구조화 요청이 아니다 — 평문 한마디(§11 MANUAL 직접 지시 등).
        return (f"[MOCK] 요청을 확인했습니다 — \"{_requirement(req)}\"\n\n"
                f"실제 모델이 아니라 Mock 제공자가 만든 답입니다. "
                f"설정에서 API 키를 등록하면 실제 직원이 답합니다.")
    body = _j(script(req))
    # Mock 이 만든 것임이 산출물 밖에서도 보여야 한다. JSON 안에 섞으면
    # 스키마 위반이 되므로 코드펜스 뒤에 붙인다 — 파서는 펜스만 읽는다.
    return f"{body}\n\n(이 응답은 Mock 제공자가 만든 것입니다. 실제 모델이 아닙니다.)"
