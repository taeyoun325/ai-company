"""AI 직원 5명 (지시서 §8).

## 이 파일이 지키려는 것

1. **권한 불변식** — 구현자가 검증기를 고칠 수 없다. 이게 무너지면
   "테스트가 통과했다"는 말이 아무것도 보증하지 않는다.
2. **Mock 대본이 진짜 계약을 지킨다** — 키가 맨 마지막에 들어오는 방침
   아래에서, 대본이 스키마를 어기면 파서와 복구 경로가 한 번도 시험되지
   않은 채로 DAY 13 까지 간다.
3. **직원 id 가 어디에도 하드코딩되어 있지 않다** — DAY 1 의 usage 가
   `PM/DEV/QA` 로 박혀 있던 것과 같은 실수를 반복하지 않는다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config, usage                                   # noqa: E402
from app.agents import employee, json_io, mock_script, roles     # noqa: E402
from app.agents.schemas import (Criterion, FinalReport, Plan,    # noqa: E402
                                Routing, TestSuite, Verdict, WorkResult)
from app.database import store                                   # noqa: E402
from app.providers import registry                               # noqa: E402
from app.providers.base import GenerateRequest                   # noqa: E402
from app.tools import project_fs as pfs                          # noqa: E402


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    registry.reset()
    usage.bind("test-employees")
    yield
    usage.drop("test-employees")
    registry.reset()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("테스트 프로젝트")
    pfs.use(slug)
    yield slug
    pfs.release()


# ── 직원 표 ────────────────────────────────────────────────────────
def test_five_employees():
    assert len(roles.EMPLOYEES) == 5, "지시서 §8 은 직원 5명이다"


def test_every_employee_has_a_real_provider():
    names = set(registry.names())
    for e in roles.EMPLOYEES.values():
        assert e.provider in names, f"{e.id} 의 제공자 {e.provider} 가 레지스트리에 없다"


def test_every_employee_model_has_a_price():
    """단가 없는 모델로 일하면 그 직원의 비용이 0 으로 잡힌다.
    0 은 공짜가 아니라 모른다는 뜻이고, 예산 상한이 안 걸린다."""
    for e in roles.EMPLOYEES.values():
        assert e.model in config.PRICES, f"{e.id} 의 모델 {e.model} 단가가 없다"


def test_verifier_is_a_different_company_than_the_builder():
    """같은 회사 모델끼리 검토하면 같은 실수를 함께 놓친다 (§8 교차검증).

    이게 깨지면 제품의 핵심 논리가 사라지는데, 화면에는 아무 변화가 없다.
    그래서 테스트로 못박는다.
    """
    builder = roles.get("developer")
    verifier = roles.get(roles.VERIFIER)
    assert builder.provider != verifier.provider


def test_planner_cannot_write_anything():
    assert roles.get(roles.PLANNER).writes == ()


def test_only_the_verifier_writes_tests():
    writers = [e.id for e in roles.EMPLOYEES.values() if roles.TESTS in e.writes]
    assert writers == [roles.VERIFIER]


def test_developer_cannot_even_read_tests():
    """읽을 수 있으면 테스트를 통과시키는 코드를 쓴다.
    그건 인수기준을 만족시키는 것과 다르다."""
    assert roles.TESTS not in roles.get("developer").reads


def test_assignable_excludes_planner_and_verifier():
    a = roles.assignable()
    assert roles.PLANNER not in a and roles.VERIFIER not in a
    assert set(a) == {"developer", "writer", "designer"}


# ── 사용량 키가 직원 표를 따른다 ───────────────────────────────────
def test_usage_slots_follow_the_roster():
    """DAY 1 의 usage 는 PM/DEV/QA 로 하드코딩돼 있었다.
    직원을 늘리면서 안 고치면 직원별 사용량이 세 칸에 섞인다."""
    slots = set(usage.agents_of())
    assert set(roles.ids()) <= slots


def test_call_is_billed_to_the_employee(project):
    employee.ask("strategist", "# 의뢰인 요구사항\n계산기를 만들어주세요", Plan)
    assert usage.agents_of()["strategist"]["calls"] == 1, \
        "직원 id 로 사용량이 잡히지 않으면 그 직원의 비용이 사라진다"


# ── 권한이 실제로 막히는가 ─────────────────────────────────────────
def test_developer_write_to_tests_is_denied(project):
    with pytest.raises(pfs.Denied):
        pfs.write("tests/test_x.py", "assert True", "developer")


def test_developer_read_of_tests_is_denied(project):
    pfs.write("tests/test_x.py", "assert True", "analyst")
    with pytest.raises(pfs.Denied):
        pfs.read("tests/test_x.py", "developer")


def test_analyst_write_to_src_is_denied(project):
    with pytest.raises(pfs.Denied):
        pfs.write("src/x.py", "x = 1", "analyst")


def test_writer_writes_only_docs(project):
    pfs.write("docs/README.md", "# 안녕", "writer")
    with pytest.raises(pfs.Denied):
        pfs.write("src/x.py", "x = 1", "writer")


def test_escape_outside_project_is_denied(project):
    for bad in ("../../etc/passwd", "src/../../secret.txt", "/etc/passwd"):
        with pytest.raises(pfs.Denied):
            pfs.write(bad, "x", "developer")


def test_sibling_prefix_is_not_inside(project):
    """`projects/calc` 와 `projects/calc-evil` 은 접두사로는 통과한다.
    문자열 비교로 경로를 검사하면 여기서 뚫린다."""
    with pytest.raises(pfs.Denied):
        pfs.write(f"../{project}-evil/src/x.py", "x", "developer")


def test_environment_changing_filenames_are_forbidden(project):
    """conftest.py 하나면 테스트 실행 환경 자체가 바뀐다."""
    for name in ("conftest.py", "pytest.ini", "sitecustomize.py", "evil.pth"):
        with pytest.raises(pfs.Denied):
            pfs.write(f"src/{name}", "x", "developer")


def test_unknown_area_is_denied(project):
    with pytest.raises(pfs.Denied):
        pfs.write("bin/run.sh", "x", "developer")


def test_snapshot_respects_read_permission(project):
    pfs.write("src/calc.py", "x = 1", "developer")
    pfs.write("tests/test_calc.py", "assert True", "analyst")
    assert "tests/test_calc.py" not in pfs.snapshot("developer")
    assert "tests/test_calc.py" in pfs.snapshot("analyst")


def test_overwrite_keeps_history(project):
    pfs.write("src/calc.py", "old", "developer")
    pfs.write("src/calc.py", "new", "developer")
    vs = store.versions(project, "src/calc.py")
    assert len(vs) >= 2, "덮어쓰기 이전 내용이 남지 않으면 회차별 diff 가 불가능하다"


# ── Mock 대본이 계약을 지키는가 ────────────────────────────────────
@pytest.mark.parametrize("employee_id,schema,ask", [
    ("strategist", Plan, "# 의뢰인 요구사항\n계산기를 만들어주세요"),
    ("developer", WorkResult, "태스크: src/calc.py 에 사칙연산을 구현하세요"),
    ("writer", WorkResult, "태스크: docs/README.md 에 사용법을 쓰세요 (writer)"),
    ("designer", WorkResult, "태스크: design/screen.md 를 명세하세요 (designer)"),
    ("analyst", TestSuite, "인수기준으로 테스트를 작성하세요"),
    ("analyst", Verdict, "이 산출물을 검토하세요"),
    ("strategist", FinalReport, "인수기준 전체를 대조하세요"),
    ("strategist", Routing, "이 일을 누구에게 맡길까요"),
])
def test_mock_script_satisfies_every_schema(employee_id, schema, ask, project):
    """대본이 스키마를 어기면, 파서와 복구 경로가 한 번도 시험되지 않은 채
    DAY 13 까지 간다. 그때 키를 꽂으면 전부 터진다."""
    out = employee.ask(employee_id, ask, schema)
    assert isinstance(out, schema)


def test_mock_plan_assigns_only_assignable_employees(project):
    plan = employee.ask("strategist", "# 의뢰인 요구사항\n계산기", Plan)
    for t in plan.tasks:
        assert t.assignee in roles.assignable(), f"없는 담당자: {t.assignee}"


def test_mock_plan_tasks_cover_declared_criteria(project):
    plan = employee.ask("strategist", "# 의뢰인 요구사항\n계산기", Plan)
    ids = {c.id for c in plan.acceptance_criteria}
    for t in plan.tasks:
        assert set(t.covers) <= ids, "존재하지 않는 인수기준을 덮는다고 적었다"


def test_mock_verdict_fails_when_tests_failed(project):
    v = employee.ask("analyst", '테스트 리포트: {"ok": false}', Verdict)
    assert v.verdict == "fail"


def test_mock_verdict_passes_on_clean_report(project):
    v = employee.ask("analyst", '테스트 리포트: {"ok": true}\n모든 기준 충족', Verdict)
    assert v.verdict == "pass"


def test_verdict_always_carries_a_confidence_value(project):
    """대본이 이 필드를 빠뜨리면 스키마 검증에서 바로 터진다 — 여기서
    한 번 더 명시적으로 본다, 나중에 대본을 고칠 사람에게 신호가
    되도록."""
    v = employee.ask("analyst", '테스트 리포트: {"ok": true}', Verdict)
    assert 0.0 <= v.confidence <= 1.0


def test_verdict_confidence_is_bounded_to_zero_one():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Verdict(message_to_team="x", verdict="pass", severity="none",
                findings=[], required_fixes=[], confidence=1.5)
    with pytest.raises(pydantic.ValidationError):
        Verdict(message_to_team="x", verdict="pass", severity="none",
                findings=[], required_fixes=[], confidence=-0.1)


def test_verdict_confidence_is_required():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Verdict(message_to_team="x", verdict="pass", severity="none",
                findings=[], required_fixes=[])


def test_mock_developer_fixes_after_rejection(project):
    """반려 사유가 들어오면 고친 버전을 낸다. 난수가 아니라 입력으로 가른다."""
    first = employee.ask("developer", "태스크: 사칙연산 구현", WorkResult)
    again = employee.ask("developer", "태스크: 사칙연산 구현\n반려 사유: 0 나눗셈 미처리",
                         WorkResult)
    assert "ValueError" not in first.files[0].content
    assert "ValueError" in again.files[0].content


def test_mock_output_is_labelled(project):
    """Mock 이 만든 것임이 보여야 한다. 안 보이면 아무도 진짜와 가짜를 구분 못 한다."""
    p = registry.get("claude")
    text = p.generate(GenerateRequest.ask("아무 지침", "아무 질문")).text
    assert "MOCK" in text.upper()


# ── JSON 파싱 ──────────────────────────────────────────────────────
def test_extract_stops_at_balanced_brace():
    """`rfind('}')` 로 자르면 뒤에 붙은 설명 속 중괄호까지 삼켜서
    멀쩡한 JSON 을 깨진 것으로 만든다."""
    text = '{"a": 1}\n\n설명입니다. {이건 JSON 이 아닙니다}'
    assert json_io.extract_json(text) == '{"a": 1}'


def test_extract_handles_braces_inside_strings():
    text = '{"a": "중괄호 } 포함", "b": 2}'
    assert json_io.extract_json(text) == text


def test_extract_prefers_code_fence():
    text = '앞말\n```json\n{"a": 1}\n```\n뒷말 {거짓}'
    assert json_io.extract_json(text) == '{"a": 1}'


def test_parse_failure_is_not_swallowed():
    """빈 객체로 때우면 '태스크 0개짜리 계획'이 정상처럼 흘러간다."""
    with pytest.raises(json_io.ParseFailed):
        json_io.parse("JSON 이 없는 답변입니다", Plan)


def test_parse_rejects_unknown_fields():
    """모르는 필드를 조용히 버리면, 모델이 엉뚱한 이름으로 답한 것을
    빈 값으로 읽고 그대로 진행한다."""
    with pytest.raises(json_io.ParseFailed):
        json_io.parse('{"id": "ac1", "text": "t", "몰래": 1}', Criterion)


def test_repair_path_retries_once_then_gives_up(project, monkeypatch):
    """두 번 같은 실수를 하는 모델은 세 번째에도 한다. 그 사이 비용은 CEO 가 낸다."""
    p = registry.get("claude")
    monkeypatch.setattr(p, "responder", lambda req: "JSON 이 아닙니다")
    with pytest.raises(employee.EmployeeFailed):
        employee.ask("strategist", "계획을 세우세요", Plan)
    assert len(p.calls) == employee.REPAIR_ATTEMPTS + 1


def test_repair_path_recovers(project, monkeypatch):
    p = registry.get("claude")
    calls = {"n": 0}
    real = mock_script.responder

    def flaky(req):
        calls["n"] += 1
        return "처음엔 망가진 답" if calls["n"] == 1 else real(req)

    monkeypatch.setattr(p, "responder", flaky)
    plan = employee.ask("strategist", "# 의뢰인 요구사항\n계산기", Plan)
    assert plan.tasks, "복구 경로가 동작하지 않으면 실행이 통째로 죽는다"


# ── 화면에 내려보낼 직원 현황 ──────────────────────────────────────
def test_extract_survives_code_fence_inside_json_string():
    """문서나 코드를 내보내는 직원의 응답은 거의 항상 JSON 문자열 값 안에
    코드펜스를 담고 있다. 닫는 펜스로 끝을 자르면 바로 거기서 끊긴다."""
    import json as _json
    inner = "# 안녕\n\n```python\nadd(1, 2)\n```\n"
    text = "```json\n" + _json.dumps(
        {"path": "docs/README.md", "content": inner}, ensure_ascii=False) + "\n```"
    got = _json.loads(json_io.extract_json(text))
    assert got["content"] == inner


def test_status_marks_mock(project):
    for row in employee.status():
        assert row["mock"] is True, "Mock 여부가 화면에 전달되지 않는다"
        assert row["model"], "모델이 비어 있으면 화면이 무엇으로 일하는지 못 그린다"


# ── 대본도 언어를 따른다 (DAY 22) ──────────────────────────────────
def test_mock_script_speaks_the_users_language(project):
    """실제 모델은 프롬프트로 언어를 정한다. **Mock 은 프롬프트를 읽지
    않으므로** 그 길이 없고, 영어로 쓰는 사람이 데모를 돌리면 대사·문서·
    명세가 전부 한국어로 나왔다. 무료 요금제가 없는 제품에서 Mock 은
    사실상 데모이고, 데모가 읽히지 않으면 결제 버튼은 눌리지 않는다.
    """
    from app import lang

    with lang.bind("en"):
        plan = employee.ask("strategist", "# 의뢰인 요구사항\ncalculator", Plan)
        assert "acceptance criteria" in plan.message_to_team, plan.message_to_team
        assert not _has_korean(plan.message_to_team)
        for c in plan.acceptance_criteria:
            assert not _has_korean(c.text), c.text
        for t in plan.tasks:
            assert not _has_korean(t.title), t.title

        work = employee.ask("writer", "# 할 일\ndocs/README.md", WorkResult)
        assert not _has_korean(work.message_to_team), work.message_to_team
        assert not _has_korean(work.files[0].content), work.files[0].content

    with lang.bind("ja"):
        plan = employee.ask("strategist", "# 의뢰인 요구사항\n電卓", Plan)
        assert "受け入れ基準" in plan.message_to_team, plan.message_to_team

    # 기본은 한국어 그대로.
    plan = employee.ask("strategist", "# 의뢰인 요구사항\n계산기", Plan)
    assert "인수기준" in plan.message_to_team


def test_the_demo_still_rejects_and_then_fixes_in_english(project):
    """대본을 번역하면서 데모의 **반려 → 수정** 루프가 깨질 수 있었다.

    재작업 판단은 프롬프트의 `# 반려 사유` 헤더로 가른다 —
    `orchestrator/prompts.py` 가 만드는 것이고 모델용이라 번역하지 않는다.
    그래서 대본 언어와 무관하게 유지된다. 그 사실을 검사로 못 박는다.
    """
    from app import lang

    with lang.bind("en"):
        first = employee.ask("developer", "# 할 일\nsrc/calc.py", WorkResult)
        assert "ValueError" not in first.files[0].content

        fixed = employee.ask(
            "developer",
            "# 할 일\nsrc/calc.py\n\n# 반려 사유\n{\"required_fixes\": []}",
            WorkResult)
        assert "ValueError" in fixed.files[0].content
        # 예외 문장도 언어를 따른다 — 산출물 안의 글자다.
        assert "cannot divide by zero" in fixed.files[0].content


def test_mock_routing_reads_english_and_japanese_requirements(project):
    """요구사항은 사용자가 쓴 글이라 언어를 고를 수 없다. 영어로
    "usage docs" 라고 쓴 사람이 개발자에게 배정되면 라우팅이 고장 난
    것처럼 보인다."""
    assert employee.ask("strategist", "write the usage docs",
                        Routing).employee == "writer"
    assert employee.ask("strategist", "spec the result screen layout",
                        Routing).employee == "designer"
    assert employee.ask("strategist", "ドキュメントを書いて",
                        Routing).employee == "writer"
    assert employee.ask("strategist", "implement the four operations",
                        Routing).employee == "developer"


def _has_korean(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)
