"""직원 사이의 계약서 (지시서 §8 · §9).

## 자연어가 아니라 스키마로 주고받는 이유

직원끼리 채팅으로 일을 넘기면 파싱이 실패하고, 토큰이 낭비되고, 서로
다른 것을 말하면서 같은 말을 했다고 믿는다. 오케스트레이터가 읽는 것은
**구조화 데이터**이고, 사람이 읽는 것은 각 스키마의 `message_*` 필드다.
그 둘을 한 문자열에 섞으면 둘 다 망가진다.

## 모든 제공자에 같은 방식으로 건다

Anthropic 에는 구조화 출력 API 가 있고 다른 곳에는 없거나 모양이 다르다.
제공자마다 다른 길로 가면 §7 어댑터를 둔 의미가 사라지고, 계약 테스트도
제공자별로 갈라진다. 그래서 **JSON 을 글로 요구하고 글에서 파싱한다**
(`app/agents/json_io.py`). 대신 실패했을 때 오류를 그대로 되돌려주고
한 번 더 시키는 복구 경로를 둔다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    # 모르는 필드를 조용히 버리면, 모델이 엉뚱한 이름으로 답한 것을
    # "빈 값"으로 읽고 그대로 진행한다. 틀렸으면 틀렸다고 해야 한다.
    model_config = ConfigDict(extra="forbid")


class Criterion(Strict):
    id: str = Field(description="ac1, ac2 처럼 짧은 식별자")
    text: str = Field(description="기계가 판정 가능한 합격 조건 한 문장")


class Task(Strict):
    id: str = Field(description="t1, t2 처럼 짧은 식별자")
    title: str
    assignee: str = Field(
        description="이 태스크를 맡을 직원 id. developer · writer · designer 중 하나")
    deps: list[str] = Field(description="선행 태스크 id 목록. 없으면 빈 배열")
    files: list[str] = Field(description="이 태스크가 건드릴 프로젝트 기준 상대경로")
    covers: list[str] = Field(description="이 태스크가 충족시키는 인수기준 id 목록")
    done_when: str = Field(description="기계가 판정 가능한 완료 조건")


class Plan(Strict):
    message_to_team: str = Field(description="팀에게 하는 한두 문장. 채팅에 표시된다")
    project_name: str
    acceptance_criteria: list[Criterion]
    tasks: list[Task]

    def ac_text(self) -> list[str]:
        return [f"[{c.id}] {c.text}" for c in self.acceptance_criteria]


class FileWrite(Strict):
    path: str = Field(description="프로젝트 기준 상대경로")
    content: str = Field(description="파일 전체 내용. 부분 수정이 아니라 전문이다")


class WorkResult(Strict):
    """구현·집필·디자인이 공통으로 내는 결과.

    직원마다 다른 스키마를 두지 않는 이유: 오케스트레이터가 직원마다
    다르게 분기하면 직원을 늘릴 때마다 오케스트레이터를 고쳐야 한다.
    """
    message_to_team: str = Field(description="팀에게 하는 한두 문장. 채팅에 표시된다")
    files: list[FileWrite]
    summary: str = Field(description="무엇을 했는지 한 문단")
    self_check: str = Field(description="스스로 확인한 것과 확인하지 못한 것")


class TestFile(Strict):
    path: str = Field(description="tests/ 기준 상대경로. test_ 로 시작해야 한다")
    covers: list[str] = Field(description="이 파일이 검증하는 인수기준 id 목록")
    content: str = Field(description="파일 전체 내용")


class TestSuite(Strict):
    message_to_team: str = Field(description="팀에게 하는 한두 문장. 채팅에 표시된다")
    files: list[TestFile]
    uncovered: list[str] = Field(
        description="테스트로 자동 검증이 불가능해 사람이 봐야 하는 인수기준 id 목록")


class Finding(Strict):
    file: str
    issue: str
    why: str = Field(description="어떤 인수기준/done_when을 어떻게 위반하는지")


class Verdict(Strict):
    message_to_team: str = Field(description="담당자에게 하는 한두 문장. 채팅에 표시된다")
    verdict: Literal["pass", "fail"]
    severity: Literal["none", "minor", "major", "blocker"]
    findings: list[Finding]
    required_fixes: list[str]
    confidence: float = Field(
        ge=0.0, le=1.0,
        description=(
            "이 판정 자체에 대한 확신도(0~1). verdict 가 맞다는 통과율이 아니라 "
            "**이 판정을 내린 근거가 얼마나 단단한가**다. 코드를 실행해보지 "
            "못했거나, 인수기준이 애매해 임의로 해석했거나, 관련 파일 일부를 "
            "못 봤다면 낮게 적는다. 확신 없는 근거로 내린 pass/fail 은 그렇게 "
            "표시돼야 사람이 한 번 더 볼지 판단할 수 있다."))


class FinalReport(Strict):
    message_to_team: str
    summary: str
    met_criteria: list[str] = Field(description="충족된 인수기준 id 목록")
    unmet_criteria: list[str] = Field(description="충족되지 않은 인수기준 id 목록")


class Routing(Strict):
    """AUTO 모드에서 오케스트레이터가 직원을 고를 때 (지시서 §10)."""
    employee: str = Field(description="맡길 직원 id")
    why: str = Field(description="왜 이 직원인지 한 문장")
