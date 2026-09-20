"""MANUAL 모드 (지시서 §11).

## 이 파일이 지키려는 것

**두 경로가 같은 규칙을 쓴다.** AUTO 에서 막히는 것이 MANUAL 에서 뚫리면,
그 차이가 곧 구멍이다. CEO 가 직접 시켰다는 사실은 권한의 근거가 아니다.

그리고 예산. MANUAL 은 버튼을 여러 번 누르는 모드이므로, 누를 때마다
누적이 0 으로 돌아가면 상한이 영영 걸리지 않는다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config, usage                              # noqa: E402
from app.agents import employee, roles                          # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import manual                              # noqa: E402
from app.providers import registry                               # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    registry.reset()
    yield
    registry.reset()


@pytest.fixture
def slug():
    s = manual.open_project("계산기를 만들어주세요")
    yield s
    manual.clear_history(s)


# ── 기본 흐름 ──────────────────────────────────────────────────────
def test_instruct_writes_files(slug):
    out = manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    assert out["files"] == ["src/calc.py"]
    assert "src/calc.py" in store.files_of(slug)


def test_planner_answers_in_prose_without_inventing_files(slug):
    """파일을 쓸 수 없는 직원에게 files 스키마를 씌우면, 빈 배열을 채우려고
    없는 파일을 지어낸다."""
    out = manual.instruct(slug, roles.PLANNER, "어떻게 나누면 좋을까요?")
    assert out["files"] == []
    assert out["text"].strip()


def test_history_is_kept_per_employee(slug):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    manual.instruct(slug, "writer", "문서를 써주세요")
    assert manual.history(slug, "developer"), "다음 지시에서 이어받을 수 없다"
    assert not any("사칙연산" in m.content
                   for m in manual.history(slug, "writer")), \
        "직원끼리 대화가 섞이면 교차검증 전제가 무너진다"


def test_history_is_capped(slug):
    for _ in range(MAX := manual.MAX_HISTORY):
        manual.instruct(slug, "developer", f"{_}번째 지시입니다")
    assert len(manual.history(slug, "developer")) <= MAX, \
        "이력이 무한히 쌓이면 비용이 대화 길이의 제곱으로 자란다"


def test_clear_history(slug):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    manual.clear_history(slug, "developer")
    assert manual.history(slug, "developer") == []


# ── 권한 경계는 AUTO 와 같다 ───────────────────────────────────────
def test_ceo_cannot_grant_write_permission(slug, monkeypatch):
    """'CEO 가 시켰다'는 권한의 근거가 아니다.

    작가에게 src/ 를 쓰라고 시키고 모델이 따르더라도, 파일은 거부되어야 한다.
    """
    from app.agents.schemas import FileWrite, WorkResult
    monkeypatch.setattr(employee, "ask", lambda *a, **kw: WorkResult(
        message_to_team="썼습니다", summary="s", self_check="c",
        files=[FileWrite(path="src/evil.py", content="x = 1")]))
    out = manual.instruct(slug, "writer", "src/evil.py 에 써주세요")
    assert out["files"] == []
    assert "src/evil.py" not in store.files_of(slug)


def test_denied_write_is_reported_not_silent(slug, monkeypatch):
    from app.agents.schemas import FileWrite, WorkResult
    monkeypatch.setattr(employee, "ask", lambda *a, **kw: WorkResult(
        message_to_team="썼습니다", summary="s", self_check="c",
        files=[FileWrite(path="tests/test_x.py", content="x")]))
    manual.instruct(slug, "developer", "테스트를 고쳐주세요")
    errors = [e for e in bus.history(slug)
              if e.get("kind") == "error" and "거부" in e.get("text", "")]
    assert errors, "조용히 버리면 CEO 는 지시가 먹혔다고 믿는다"


# ── 예산 (§18) ─────────────────────────────────────────────────────
def test_usage_accumulates_across_instructions(slug):
    """지시마다 0 으로 돌아가면, 버튼을 여러 번 누르는 것으로 상한을 우회한다."""
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    first = usage.agents_of(slug)["developer"]["calls"]
    manual.instruct(slug, "developer", "주석을 달아주세요")
    assert usage.agents_of(slug)["developer"]["calls"] > first


def test_budget_is_checked_before_the_call(slug, monkeypatch):
    monkeypatch.setattr(config, "MAX_PROJECT_COST", 0.0)
    monkeypatch.setattr(employee, "worst_case_cost", lambda _id: 1.0)
    with pytest.raises(RuntimeError, match="비용 상한"):
        manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    assert "src/calc.py" not in store.files_of(slug), "상한을 넘긴 뒤에 멈췄다"


# ── 검증 ───────────────────────────────────────────────────────────
def test_verify_runs_the_same_check_as_auto(slug):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    manual.instruct(slug, "analyst", "인수기준대로 테스트를 써주세요")
    out = manual.verify(slug)
    assert out["verdict"]["verdict"] in ("pass", "fail")
    assert "passed" in out["report"]


def test_verify_without_criteria_uses_the_requirement(slug):
    """기준 없이 검증하면 검증자가 기준을 지어낸다."""
    crit = manual._criteria_of(store.meta(slug))
    assert crit and "계산기" in crit[0].text


def test_verifier_prompt_has_no_builder_explanation(slug, monkeypatch):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    seen = []
    real = employee.ask

    def spy(employee_id, user, schema, history=None):
        if employee_id == roles.VERIFIER:
            seen.append(user)
        return real(employee_id, user, schema, history)

    monkeypatch.setattr(employee, "ask", spy)
    manual.verify(slug)
    assert seen
    assert all("확인하지 못했다" not in t for t in seen)


# ── 잘못된 입력 ────────────────────────────────────────────────────
def test_unknown_project_raises(slug):
    with pytest.raises(KeyError):
        manual.instruct("없는프로젝트", "developer", "안녕")


def test_empty_message_raises(slug):
    with pytest.raises(ValueError):
        manual.instruct(slug, "developer", "   ")


def test_unknown_employee_raises(slug):
    with pytest.raises(KeyError):
        manual.instruct(slug, "없는직원", "안녕")


def test_busy_project_rejects_a_second_instruction(slug, monkeypatch):
    """같은 프로젝트에 둘이 동시에 쓰면 파일이 서로를 덮어쓴다."""
    import threading
    started = threading.Event()
    release = threading.Event()
    real = employee.ask

    def slow(*a, **kw):
        started.set()
        release.wait(10)
        return real(*a, **kw)

    monkeypatch.setattr(employee, "ask", slow)
    t = threading.Thread(target=lambda: manual.instruct(slug, "developer", "구현"),
                         daemon=True)
    t.start()
    assert started.wait(10)
    try:
        with pytest.raises(manual.Busy):
            manual.instruct(slug, "writer", "문서")
    finally:
        release.set()
        t.join(20)
