"""오케스트레이터 (지시서 §9 · §10).

## 이 파일이 지키려는 것

1. **순서를 코드가 정한다.** 테스트가 구현보다 먼저 쓰이고, 검증자에게는
   담당자의 설명이 가지 않는다. 이 둘이 깨지면 교차검증이 형식만 남는다.
2. **하드스톱이 실제로 멈춘다.** 라운드·비용·재기획 상한. 상한이 사후
   감지면 그건 상한이 아니라 부고다.
3. **모델이 고른 것을 검사 없이 따르지 않는다.** AUTO 라우팅이 없는
   직원을 지목하면 되돌린다.

전 구간을 Mock 으로 돌린다. 그게 현재 방침이고, Mock 이 계약을 지키는지는
`test_employees.py` 가 따로 본다.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config, usage                              # noqa: E402
from app.agents import employee, roles                          # noqa: E402
from app.agents.schemas import Plan, Task, Verdict              # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import engine, runner                      # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402

TIMEOUT = 90


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    # 지갑은 디스크에 남는다. 격리하지 않으면 앞 테스트가 쓴 크레딧이
    # 뒤 테스트를 굶긴다 — 실패가 테스트 순서에 따라 달라진다.
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    credits.reset()
    registry.reset()
    yield
    credits.reset()
    registry.reset()


def _wait(slug: str, timeout: float = TIMEOUT) -> dict:
    deadline = time.time() + timeout
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    assert not engine.is_running(slug), f"{timeout}초 안에 끝나지 않았다"
    return store.meta(slug)


def _run(requirement: str = "간단한 계산기를 만들어주세요") -> tuple[str, dict]:
    slug = engine.start(requirement)
    return slug, _wait(slug)


# ── 전 구간이 돈다 ─────────────────────────────────────────────────
def test_full_run_completes_and_produces_files():
    slug, m = _run()
    assert m["status"] == "done", m.get("stopped_reason")
    files = store.files_of(slug)
    assert "src/calc.py" in files
    assert "tests/test_calc.py" in files


def test_run_is_billed_per_employee():
    """직원별로 갈라 세지 못하면 §14 원가 계산도 §15 크레딧도 불가능하다."""
    _, m = _run()
    billed = {k for k, v in m["usage"].items() if v["calls"]}
    assert {"strategist", "developer", "analyst"} <= billed


def test_rework_loop_actually_runs():
    """Mock 개발자는 처음에 0 나눗셈을 빠뜨리고, 반려를 받고 고친다.
    개발자가 한 번만 불렸다면 반려 루프가 돌지 않은 것이다."""
    _, m = _run()
    assert m["usage"]["developer"]["calls"] >= 2


def test_tests_are_written_before_implementation():
    """구현자가 테스트를 보고 맞춰 짜면 '테스트 통과'가 아무것도 보증하지 않는다."""
    slug, _ = _run()
    phases = [e["name"] for e in bus.history(slug) if e["type"] == "phase"]
    assert phases.index("WRITE_TESTS") < phases.index("IMPLEMENT")


def test_verifier_never_sees_the_builders_explanation(monkeypatch):
    """검증자가 담당자의 자기 합리화를 읽으면 교차검증이 오염된다."""
    seen: list[str] = []
    real = employee.ask

    def spy(employee_id, user, schema, history=None):
        if employee_id == roles.VERIFIER:
            seen.append(user)
        return real(employee_id, user, schema, history)

    monkeypatch.setattr(employee, "ask", spy)
    _run()
    assert seen, "검증자가 한 번도 불리지 않았다"
    # Mock 개발자의 self_check / summary 문구가 검증자 프롬프트에 섞이면 안 된다
    for text in seen:
        assert "예외 경로는 확인하지 못했다" not in text
        assert "확인 부탁드립니다" not in text


def test_run_records_mock_flag():
    """Mock 으로 만든 산출물이 저장소에 실제 결과처럼 남으면 안 된다."""
    _, m = _run()
    assert m["mock"] is True


# ── 하드스톱 (§18) ─────────────────────────────────────────────────
def test_round_limit_stops_the_run(monkeypatch):
    monkeypatch.setattr(config, "MAX_ROUNDS", 1)
    _, m = _run()
    assert m["status"] == "stopped"
    assert "라운드 상한" in m["stopped_reason"]


def test_cost_limit_is_checked_before_the_call(monkeypatch):
    """사후 감지는 상한이 아니다. 개발자 한 번이 예산을 통째로 넘길 수 있다."""
    monkeypatch.setattr(config, "MAX_PROJECT_COST", 0.0001)
    monkeypatch.setattr(employee, "worst_case_cost", lambda _id: 1.0)
    _, m = _run()
    assert m["status"] == "stopped"
    assert "비용 상한" in m["stopped_reason"]
    assert m["cost"] <= config.MAX_PROJECT_COST + 1e-9, "상한을 넘겨 쓴 뒤 멈췄다"


def test_replan_limit_stops_the_run(monkeypatch):
    """검증자가 계속 반려하면 무한 루프가 된다. 그 비용은 CEO 가 낸다."""
    monkeypatch.setattr(config, "MAX_REWORK", 1)
    monkeypatch.setattr(config, "MAX_REPLANS", 0)
    real = employee.ask

    def always_fail(employee_id, user, schema, history=None):
        if schema is Verdict:
            return Verdict(message_to_team="안 됩니다", verdict="fail",
                           severity="major", findings=[], required_fixes=["고치세요"])
        return real(employee_id, user, schema, history)

    monkeypatch.setattr(employee, "ask", always_fail)
    _, m = _run()
    assert m["status"] == "stopped"
    assert "재기획 상한" in m["stopped_reason"]


def test_empty_plan_stops_instead_of_reporting_success(monkeypatch):
    """태스크 0개짜리 계획을 그대로 진행하면 '전부 완료'로 끝난다."""
    real = employee.ask

    def empty(employee_id, user, schema, history=None):
        if schema is Plan:
            return Plan(message_to_team="빈 계획", project_name="x",
                        acceptance_criteria=[], tasks=[])
        return real(employee_id, user, schema, history)

    monkeypatch.setattr(employee, "ask", empty)
    _, m = _run()
    assert m["status"] == "stopped"


def test_employee_failure_stops_cleanly(monkeypatch):
    def boom(*a, **kw):
        raise employee.EmployeeFailed("strategist", "제공자 죽음")

    monkeypatch.setattr(employee, "ask", boom)
    _, m = _run()
    assert m["status"] == "stopped"
    assert "직원 호출 실패" in m["stopped_reason"]


def test_concurrency_limit(monkeypatch):
    """무제한 동시 실행은 비용과 요청 한도를 동시에 터뜨린다."""
    monkeypatch.setattr(engine, "MAX_CONCURRENT", 0)
    with pytest.raises(RuntimeError):
        engine.start("아무거나")


# ── AUTO 라우팅 (§10) ──────────────────────────────────────────────
def test_route_picks_an_assignable_employee():
    assert engine.route("README 를 써주세요").employee in roles.assignable()


def test_route_rejects_an_unassignable_pick(monkeypatch):
    """모델이 검증자를 지목하면 검증자가 자기 코드를 검증하게 된다.
    고르게 하되, 고른 것을 검사 없이 따르지는 않는다."""
    from app.agents.schemas import Routing
    monkeypatch.setattr(employee, "ask",
                        lambda *a, **kw: Routing(employee=roles.VERIFIER, why="x"))
    assert engine.route("아무거나").employee in roles.assignable()


def test_unassignable_task_assignee_falls_back():
    bad = Task(id="t1", title="x", assignee="analyst", deps=[], files=[],
               covers=[], done_when="x")
    assert engine._assignee(bad) in roles.assignable()


def test_task_signature_changes_with_content():
    """done 을 id 로만 관리하면, 재기획에서 같은 id 의 다른 태스크를
    이미 끝났다고 착각하고 건너뛴다."""
    a = Task(id="t1", title="구현", assignee="developer", deps=[], files=[],
             covers=["ac1"], done_when="된다")
    b = a.model_copy(update={"done_when": "다르게 된다"})
    assert engine._sig(a) != engine._sig(b)


def test_topological_order_respects_deps():
    tasks = [
        Task(id="t2", title="뒤", assignee="writer", deps=["t1"], files=[],
             covers=[], done_when="x"),
        Task(id="t1", title="앞", assignee="developer", deps=[], files=[],
             covers=[], done_when="x"),
    ]
    assert [t.id for t in engine._topo(tasks)] == ["t1", "t2"]


def test_dependency_cycle_does_not_hang():
    """계획을 세운 것도 모델이다. 순환 하나 때문에 실행 전체를 버리지 않는다."""
    tasks = [
        Task(id="t1", title="a", assignee="developer", deps=["t2"], files=[],
             covers=[], done_when="x"),
        Task(id="t2", title="b", assignee="developer", deps=["t1"], files=[],
             covers=[], done_when="x"),
    ]
    assert len(engine._topo(tasks)) == 2


# ── 정지 버튼 ──────────────────────────────────────────────────────
def test_cancel_unknown_run_is_false():
    assert engine.cancel("없는슬러그") is False


# ── 격리된 테스트 실행 ─────────────────────────────────────────────
def test_runner_ignores_project_pytest_config(tmp_path):
    """프로젝트 안의 pytest.ini 가 먹히면, 생성된 코드가 테스트 실행 환경
    자체를 바꿀 수 있다."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                              encoding="utf-8")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8")
    r = runner.run(tmp_path)
    assert r["ok"], r["output"]
    assert r["passed"] == 1


def test_runner_reports_failures_without_crashing(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8")
    r = runner.run(tmp_path)
    assert r["ok"] is False
    assert r["failed"] == 1


def test_runner_skips_when_there_are_no_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    r = runner.run(tmp_path)
    assert r["skipped_run"] is True
    assert r["ok"] is False, "테스트가 없는 것을 통과로 읽으면 안 된다"


def test_runner_strips_secrets_from_child_env(monkeypatch):
    """생성된 코드가 os.environ 을 읽어 키를 가져가면, 그 코드는 서버에서
    돈다. 자식 프로세스에 키를 넘기지 않는 것이 유일한 방어다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("MY_DB_PASSWORD", "hunter2")
    env = runner._clean_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "MY_DB_PASSWORD" not in env
    assert env["PYTHONNOUSERSITE"] == "1", "usercustomize.py 자동 import 를 막아야 한다"


# ── 죽은 실행 치우기 (DAY 22) ──────────────────────────────────────
def test_a_run_left_behind_by_a_restart_is_closed(tmp_path, monkeypatch):
    """`new_project()` 는 status 를 running 으로 쓰고, 그걸 끝으로 바꾸는
    것은 실행 스레드뿐이다. 프로세스가 죽으면 되돌릴 사람이 없어서, 그
    프로젝트는 목록에서 영원히 '진행 중'으로 남는다."""
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("재시작에 버려진 실행")
    store.save_meta(slug, {"beat": time.time() - engine.BEAT_STALE - 10})

    assert engine.sweep_stale_runs() == [slug]
    meta = store.meta(slug)
    assert meta["status"] == "stopped"
    assert meta["stopped_reason"], "왜 멈췄는지 적히지 않았다"


def test_a_fresh_beat_is_left_alone(tmp_path, monkeypatch):
    """박자가 최근이면 다른 인스턴스가 돌리는 중일 수 있다. 살아 있는
    실행을 죽었다고 하는 쪽이 더 나쁘다."""
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("지금 도는 실행")
    store.save_meta(slug, {"beat": time.time()})
    assert engine.sweep_stale_runs() == []
    assert store.meta(slug)["status"] == "running"


def test_sweeping_keeps_the_files(tmp_path, monkeypatch):
    """지우지 않고 중단으로 표시한다. 조용히 사라지면 사용자는 자기가
    뭘 잘못했는지 찾게 된다."""
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("산출물이 남아야 한다")
    (store.dir_of(slug) / "src" / "calc.py").write_text("x = 1", encoding="utf-8")
    store.save_meta(slug, {"beat": 0})
    engine.sweep_stale_runs()
    assert (store.dir_of(slug) / "src" / "calc.py").exists()
