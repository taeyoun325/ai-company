"""태스크 병렬 실행 (DAY 25).

## 이 파일이 지키려는 것

1. **의존성이 풀린 태스크는 실제로 동시에 돈다.** Mock 계획의 t2(작가)와
   t3(디자이너)는 둘 다 t1 에만 기댄다 — 둘이 같은 순간에 일하고 있어야 한다.
2. **같이 돌면 안 되는 것은 같이 돌지 않는다.** 같은 직원의 태스크 둘,
   쓰기 구역이 겹치는 두 직원. 겹치면 나중에 쓴 쪽이 이기고, 되돌리기가
   남의 시도까지 지운다.
3. **줄마다 실행 범위가 다시 선다.** 줄 스레드에서 사용량이 안 잡히면
   비용이 사라지고(§14), 테넌트 자세가 안 서면 운영자 키로 나간다.
4. **예산은 동시에 나가 있는 호출까지 더해서 본다.** 두 줄이 같은 순간에
   "남은 예산 ≥ 내 최악 비용"을 보고 둘 다 부르면 합친 만큼 넘친다.
"""
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config, tenant, usage                     # noqa: E402
from app.agents import employee, roles                          # noqa: E402
from app.agents.schemas import Plan, WorkResult                 # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import engine, guard                       # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402

TIMEOUT = 90


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
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


class _Overlap:
    """구현 호출이 동시에 몇 개 떠 있었나를 센다."""

    def __init__(self, hold: float = 0.3):
        self.hold = hold
        self.lock = threading.Lock()
        self.active: dict[str, int] = {}
        self.max_total = 0
        self.max_same = 0
        self.together: set[frozenset] = set()
        self.seen_tenant: list = []
        self.seen_usage_run: list = []

    def wrap(self, real):
        def spy(employee_id, user, schema, history=None, model=None):
            if schema is not WorkResult:
                return real(employee_id, user, schema, history, model=model)
            self.seen_tenant.append(tenant.current())
            self.seen_usage_run.append(usage.current())
            with self.lock:
                self.active[employee_id] = self.active.get(employee_id, 0) + 1
                live = {k for k, v in self.active.items() if v}
                if len(live) > 1:
                    self.together.add(frozenset(live))
                self.max_total = max(self.max_total, sum(self.active.values()))
                self.max_same = max(self.max_same, self.active[employee_id])
            try:
                time.sleep(self.hold)
                return real(employee_id, user, schema, history, model=model)
            finally:
                with self.lock:
                    self.active[employee_id] -= 1
        return spy


def test_writer_and_designer_work_at_the_same_time(monkeypatch):
    ov = _Overlap()
    monkeypatch.setattr(employee, "ask", ov.wrap(employee.ask))
    slug = engine.start("간단한 계산기를 만들어주세요")
    m = _wait(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert frozenset({"writer", "designer"}) in ov.together, \
        "t2·t3 는 둘 다 t1 에만 기대는데 동시에 돌지 않았다"
    files = store.files_of(slug)
    assert "docs/README.md" in files and "design/screen.md" in files


def test_parallel_one_restores_the_serial_behaviour(monkeypatch):
    monkeypatch.setattr(engine, "MAX_PARALLEL_TASKS", 1)
    ov = _Overlap(hold=0.1)
    monkeypatch.setattr(employee, "ask", ov.wrap(employee.ask))
    m = _wait(engine.start("간단한 계산기를 만들어주세요"))
    assert m["status"] == "done", m.get("stopped_reason")
    assert ov.max_total == 1


def test_lanes_rebind_usage_and_tenant(monkeypatch):
    """줄 스레드에서 사용량이 안 잡히면 작가·디자이너의 비용이 사라진다."""
    ov = _Overlap(hold=0.05)
    monkeypatch.setattr(employee, "ask", ov.wrap(employee.ask))
    slug = engine.start("간단한 계산기를 만들어주세요")
    m = _wait(slug)
    assert all(r == slug for r in ov.seen_usage_run), ov.seen_usage_run
    assert all(p is not None and p.owner == "local" for p in ov.seen_tenant)
    assert m["usage"]["writer"]["calls"] >= 1
    assert m["usage"]["designer"]["calls"] >= 1


def test_phase_events_carry_their_lane():
    slug = engine.start("간단한 계산기를 만들어주세요")
    _wait(slug)
    lanes = {e.get("lane") for e in bus.history(slug)
             if e["type"] == "phase" and e["name"] in ("IMPLEMENT", "REVIEW")}
    assert {"t1", "t2", "t3"} <= lanes
    assert all(e["run"] == slug for e in bus.history(slug))


def _plan_two_developer_tasks(real):
    def fake(employee_id, user, schema, history=None, model=None):
        if schema is Plan and employee_id == roles.PLANNER:
            p = real(employee_id, user, schema, history, model=model)
            t1 = p.tasks[0]
            # 서로 기대지 않는 개발자 태스크 둘 — 의존성만 보면 동시에 뜰 수 있다.
            t1b = t1.model_copy(update={"id": "t1b", "title": t1.title + " (2)"})
            return p.model_copy(update={"tasks": [t1, t1b]})
        return real(employee_id, user, schema, history, model=model)
    return fake


def test_same_employee_never_runs_two_tasks_at_once(monkeypatch):
    ov = _Overlap(hold=0.1)
    monkeypatch.setattr(employee, "ask", ov.wrap(_plan_two_developer_tasks(employee.ask)))
    m = _wait(engine.start("간단한 계산기를 만들어주세요"))
    assert m["status"] == "done", m.get("stopped_reason")
    assert ov.max_same == 1, "같은 직원의 태스크 둘이 같은 파일을 동시에 썼다"


def test_overlapping_write_areas_do_not_run_together(monkeypatch):
    """프로젝트 권한으로 작가에게 design/ 쓰기를 주면 작가와 디자이너는
    같은 구역을 쓰게 된다 — 그 둘은 더 이상 같이 돌면 안 된다."""
    from app.agents import permissions
    clean, risks = permissions.validate(
        {"writer": {"writes": ["docs", "design"]}})
    ov = _Overlap(hold=0.1)
    monkeypatch.setattr(employee, "ask", ov.wrap(employee.ask))
    slug = engine.start("간단한 계산기를 만들어주세요",
                        permissions={"overrides": clean, "risks": risks})
    m = _wait(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert frozenset({"writer", "designer"}) not in ov.together


def test_budget_counts_calls_already_in_flight(monkeypatch):
    """두 줄이 동시에 예산을 보면, 먼저 나간 호출의 몫이 뒤의 검사에 보여야 한다."""
    seen: list[float] = []
    real = guard.check_spend

    def spy(slug, owner, about, **kw):
        seen.append(kw.get("inflight", 0.0))
        return real(slug, owner, about, **kw)

    monkeypatch.setattr(guard, "check_spend", spy)
    ov = _Overlap(hold=0.3)
    monkeypatch.setattr(employee, "ask", ov.wrap(employee.ask))
    m = _wait(engine.start("간단한 계산기를 만들어주세요"))
    assert m["status"] == "done"
    assert any(x > 0 for x in seen), "동시에 나간 호출이 예산 검사에 안 보였다"


def test_a_failing_lane_stops_the_run_and_waits_for_the_others(monkeypatch):
    real = employee.ask

    def boom(employee_id, user, schema, history=None, model=None):
        if employee_id == "designer" and schema is WorkResult:
            raise employee.EmployeeFailed("designer", "제공자 장애")
        if employee_id == "writer" and schema is WorkResult:
            time.sleep(0.3)
        return real(employee_id, user, schema, history, model=model)

    monkeypatch.setattr(employee, "ask", boom)
    slug = engine.start("간단한 계산기를 만들어주세요")
    m = _wait(slug)
    assert m["status"] == "stopped"
    assert "designer" in m["stopped_reason"]
    # 다른 줄이 반쯤 쓴 채로 버려지지 않았다 — 실행 스레드가 끝났을 때
    # 줄 스레드도 전부 끝나 있다.
    assert not [t for t in threading.enumerate()
                if t.name.startswith(f"lane:{slug}")]


def test_resume_does_not_charge_the_previous_run_again(monkeypatch):
    """재개한 실행은 앞 실행의 원가를 이어받는다. 끝날 때 **늘어난 만큼만**
    청구해야 한다 — 누적을 통째로 청구하면 재개할 때마다 한 번씩 더 낸다."""
    charged: list[float] = []
    real = credits.charge
    monkeypatch.setattr(credits, "charge",
                        lambda owner, usd: charged.append(usd) or real(owner, usd))
    monkeypatch.setattr(config, "MAX_ROUNDS", 4)
    slug = engine.start("간단한 계산기를 만들어주세요")
    m1 = _wait(slug)
    assert m1["status"] == "stopped"
    monkeypatch.setattr(config, "MAX_ROUNDS", 100)
    engine.resume(slug)
    m2 = _wait(slug)
    assert m2["status"] == "done"
    assert len(charged) == 2
    assert charged[0] == pytest.approx(m1["cost"], abs=1e-4)
    assert sum(charged) == pytest.approx(m2["cost"], abs=1e-4), \
        "두 번 청구한 합이 프로젝트 총원가와 달라야 할 이유가 없다"
