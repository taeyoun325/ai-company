"""에이전트 사이의 계약서. 자연어 대화가 아니라 이 스키마로만 주고받는다.

각 스키마에 message_to_* 필드가 있는 이유: 채팅 로그에 사람이 읽을 수 있는
한 마디를 남기기 위해서다. 구조화 데이터는 오케스트레이터가, 그 한 마디는 화면이 쓴다.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    # additionalProperties: false 를 스키마에 넣기 위해 필요 (구조화 출력 요구사항)
    model_config = ConfigDict(extra="forbid")


class Criterion(Strict):
    id: str = Field(description="ac1, ac2 처럼 짧은 식별자")
    text: str = Field(description="기계가 판정 가능한 합격 조건 한 문장")


class Task(Strict):
    id: str = Field(description="t1, t2 처럼 짧은 식별자")
    title: str
    deps: list[str] = Field(description="선행 태스크 id 목록. 없으면 빈 배열")
    files: list[str] = Field(description="이 태스크가 건드릴 src/ 기준 상대경로")
    covers: list[str] = Field(description="이 태스크가 충족시키는 인수기준 id 목록")
    done_when: str = Field(description="기계가 판정 가능한 완료 조건")


class Plan(Strict):
    message_to_team: str = Field(description="팀에게 하는 한두 문장. 채팅에 표시된다")
    project_name: str
    acceptance_criteria: list[Criterion]
    tasks: list[Task]

    def ac_text(self) -> list[str]:
        return [f"[{c.id}] {c.text}" for c in self.acceptance_criteria]


class TestFile(Strict):
    path: str = Field(description="tests/ 기준 상대경로. test_ 로 시작해야 한다")
    covers: list[str] = Field(description="이 파일이 검증하는 인수기준 id 목록")
    content: str = Field(description="파일 전체 내용. import는 src 패키지 기준")


class TestSuite(Strict):
    message_to_team: str = Field(description="팀에게 하는 한두 문장. 채팅에 표시된다")
    files: list[TestFile]
    uncovered: list[str] = Field(
        description="테스트로 자동 검증이 불가능해 사람이 봐야 하는 인수기준 id 목록")


class Finding(Strict):
    file: str
    issue: str
    why: str = Field(description="어떤 인수기준/done_when을 어떻게 위반하는지")


class QAVerdict(Strict):
    message_to_dev: str = Field(description="개발자에게 하는 한두 문장. 채팅에 표시된다")
    verdict: Literal["pass", "fail"]
    severity: Literal["none", "minor", "major", "blocker"]
    findings: list[Finding]
    required_fixes: list[str]


class FinalReport(Strict):
    message_to_team: str
    summary: str
    met_criteria: list[str] = Field(description="충족된 인수기준 id 목록")
    unmet_criteria: list[str] = Field(description="충족되지 않은 인수기준 id 목록")
