"""API 키 없이 UI를 시연/디버깅하기 위한 가짜 에이전트.

대본이지만 파일 생성과 pytest 실행은 진짜로 한다.
python server.py --mock 으로 켠다.
"""
import time

import bus
import config
import usage
from schemas import (Criterion, FinalReport, Finding, Plan, QAVerdict, Task,
                     TestFile, TestSuite)


def _beat(sec: float = 1.1) -> None:
    time.sleep(sec)


def _spend(agent: str, inp: int, out: int) -> None:
    """가짜 사용량. 화면의 토큰 게이지가 실제처럼 움직이게 한다."""
    usage.record(agent, config.MODEL_OF[agent], inp, out)


CRITERIA = [
    Criterion(id="ac1", text="add, sub, mul, div 네 함수가 정상 동작한다"),
    Criterion(id="ac2", text="0으로 나누면 ValueError를 발생시킨다"),
    Criterion(id="ac3", text="div는 정수끼리 나눠도 실수 결과를 반환한다"),
]


def plan(requirement: str) -> Plan:
    bus.say("PM", "요구사항 확인했습니다. 작업을 쪼개볼게요.")
    _beat()
    _spend("PM", 1840, 620)
    p = Plan(
        message_to_team="계산기 하나짜리 모듈입니다. 인수기준 3개로 정리했고 태스크는 둘로 나눴습니다.",
        project_name="mini-calculator",
        acceptance_criteria=CRITERIA,
        tasks=[
            Task(id="t1", title="사칙연산 네 함수 구현", deps=[], files=["src/calc.py"],
                 covers=["ac1", "ac3"], done_when="네 함수가 import 가능하고 동작한다"),
            Task(id="t2", title="0 나눗셈 예외 처리", deps=["t1"], files=["src/calc.py"],
                 covers=["ac2"], done_when="div(1, 0)이 ValueError를 낸다"),
        ],
    )
    bus.say("PM", p.message_to_team)
    return p


def replan(plan_, task, verdict):
    bus.say("PM", "태스크를 다시 쪼갭니다.")
    _spend("PM", 2600, 500)
    return plan_


def finalize(plan_, files, report) -> FinalReport:
    bus.say("PM", "모든 태스크가 끝났습니다. 인수기준 전체를 대조합니다.")
    _beat()
    _spend("PM", 3120, 410)
    r = FinalReport(
        message_to_team="인수기준 3개 전부 충족했습니다. 납품 가능합니다.",
        summary="src/calc.py를 생성했고 검증자가 작성한 테스트가 모두 통과했습니다.",
        met_criteria=["ac1", "ac2", "ac3"], unmet_criteria=[],
    )
    bus.say("PM", r.message_to_team)
    return r


_TESTS = '''import pytest
from calc import add, sub, mul, div


def test_basic():
    assert add(2, 3) == 5
    assert sub(5, 2) == 3
    assert mul(3, 4) == 12


def test_div_returns_float():
    assert div(10, 4) == 2.5


def test_div_zero_raises_value_error():
    with pytest.raises(ValueError):
        div(1, 0)
'''


def write_tests(criteria, tasks) -> TestSuite:
    bus.say("QA", "구현 전에 인수기준으로 테스트를 먼저 작성합니다.")
    _beat()
    _spend("QA", 2100, 900)
    s = TestSuite(
        message_to_team="기준 3개를 테스트 파일 하나로 묶었습니다. 0 나눗셈은 예외 타입까지 봅니다.",
        files=[TestFile(path="tests/test_calc.py", covers=["ac1", "ac2", "ac3"],
                        content=_TESTS)],
        uncovered=[],
    )
    bus.say("QA", s.message_to_team)
    return s


_CALC_BAD = '''def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def mul(a, b):
    return a * b


def div(a, b):
    return a / b
'''

_CALC_GOOD = _CALC_BAD.replace(
    "def div(a, b):\n    return a / b\n",
    'def div(a, b):\n    if b == 0:\n        raise ValueError("0으로 나눌 수 없습니다")\n    return a / b\n',
)


def implement(task: Task, criteria, feedback):
    from tools import fs
    if feedback:
        bus.say("DEV", "반려 사유 반영해서 다시 작업합니다.")
    else:
        bus.say("DEV", f"'{task.title}' 착수합니다.")
    _beat(0.8)
    _spend("DEV", 2450 if not feedback else 3300, 980)

    bus.say("DEV", f"파일 목록 확인 — {len(fs.listdir('DEV'))}개", kind="tool")
    _beat(0.5)

    # t1은 0 검사가 없는 상태로 내고, t2 또는 반려 후에 고친다
    good = feedback is not None or task.id == "t2"
    fs.write("src/calc.py", _CALC_GOOD if good else _CALC_BAD, "DEV")
    bus.say("DEV", "`src/calc.py` " + ("수정" if good else "새로 만듦"), kind="tool")
    _beat(0.5)

    msg = ("div에 0 검사 추가했습니다." if good
           else "사칙연산 네 개 구현했습니다. 확인 부탁드려요.")
    bus.say("DEV", msg)
    return msg, ["src/calc.py"]


def review(task: Task, criteria, files, report) -> QAVerdict:
    bus.say("QA", f"'{task.title}' 검토 시작합니다. 파일 {len(files)}개.")
    _beat()
    _spend("QA", 2980, 340)

    if not report.get("ok"):
        v = QAVerdict(
            message_to_dev="내가 쓴 테스트가 실패합니다. div가 0을 그대로 나눕니다 — ac2 위반이라 반려합니다.",
            verdict="fail", severity="major",
            findings=[Finding(file="src/calc.py", issue="0 나눗셈 미처리",
                              why="ac2는 ValueError를 요구하는데 ZeroDivisionError가 난다")],
            required_fixes=["div에서 b == 0이면 ValueError를 발생시킬 것"],
        )
    else:
        v = QAVerdict(
            message_to_dev="테스트 전부 통과하고 코드도 인수기준과 일치합니다. 통과.",
            verdict="pass", severity="none", findings=[], required_fixes=[],
        )

    icon = "통과" if v.verdict == "pass" else f"반려 ({v.severity})"
    bus.say("QA", f"**{icon}** — {v.message_to_dev}", kind="verdict")
    for f in v.findings:
        bus.say("QA", f"`{f.file}` · {f.issue}", kind="tool")
    return v
