"""태스크 병렬 실행 (DAY 25).

## 이 파일이 지키려는 것

1. **의존성이 풀린 태스크는 실제로 동시에 돈다.** Mock 계획의 t2(작가)와
   t3(디자이너)는 둘 다 t1 에만 기댄다 — 둘이 같은 순간에 일하고 있어야 한다.
2. **같이 돌면 안 되는 것은 같이 돌지 않는다.** 같은 파일을 쓰는 태스크 둘.
   겹치면 나중에 쓴 쪽이 이기고, 되돌리기가 남의 시도까지 지운다.
2½. **같이 돌아도 되는 것은 같이 돈다 (DAY 26).** 같은 직원이라도 계획에
   적은 파일이 안 겹치면 동시에 돈다 — 파일 예약. 예약한 파일을 남이 쓰면
   그 파일만 거부되고, 포기해서 되돌릴 때 남의 파일을 건드리지 않는다.
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
from app.agents.schemas import FileWrite, Plan, WorkResult      # noqa: E402
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


def test_same_employee_with_the_same_file_never_runs_twice_at_once(monkeypatch):
    """두 개발자 태스크가 같은 파일(src/calc.py)을 적었다 — 차례로 돈다."""
    ov = _Overlap(hold=0.1)
    monkeypatch.setattr(employee, "ask", ov.wrap(_plan_two_developer_tasks(employee.ask)))
    m = _wait(engine.start("간단한 계산기를 만들어주세요"))
    assert m["status"] == "done", m.get("stopped_reason")
    assert ov.max_same == 1, "같은 직원의 태스크 둘이 같은 파일을 동시에 썼다"


def _two_developer_tasks_on_different_files(real, *, t1b_writes: str = "src/extra.py"):
    """t1b 는 `src/extra.py` 를 적는다. 실제로 쓰는 파일은 `t1b_writes`."""
    def fake(employee_id, user, schema, history=None, model=None):
        if schema is Plan and employee_id == roles.PLANNER:
            p = real(employee_id, user, schema, history, model=model)
            t1 = p.tasks[0]
            t1b = t1.model_copy(update={"id": "t1b", "title": t1.title + " (2)",
                                        "files": ["src/extra.py"]})
            return p.model_copy(update={"tasks": [t1, t1b]})
        out = real(employee_id, user, schema, history, model=model)
        if schema is WorkResult and '"id": "t1b"' in user:
            # 첫 시도에만 `t1b_writes` 를 쓴다 — 반려 뒤에는 자기 파일로 간다.
            # (그때는 t1 이 끝나 예약을 놓았을 수 있다.)
            path = t1b_writes if "# 반려 사유" not in user else "src/extra.py"
            return out.model_copy(update={"files": [
                FileWrite(path=path, content="EXTRA = 1\n")]})
        return out
    return fake


def test_same_employee_on_different_files_runs_in_parallel(monkeypatch):
    """DAY 25 의 한계 — 개발자 태스크가 다섯이면 다섯 번 차례로 돌았다.
    계획에 적은 파일이 안 겹치면 같은 직원도 동시에 일한다."""
    ov = _Overlap(hold=0.3)
    monkeypatch.setattr(employee, "ask",
                        ov.wrap(_two_developer_tasks_on_different_files(employee.ask)))
    slug = engine.start("간단한 계산기를 만들어주세요")
    m = _wait(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert ov.max_same == 2, "파일이 안 겹치는 개발자 태스크 둘이 차례로 돌았다"
    assert "src/extra.py" in store.files_of(slug)


def test_a_file_reserved_by_another_lane_is_refused(monkeypatch):
    """t1b 가 적지 않은 파일(t1 의 src/calc.py)을 쓰려 한다 — t1 이 잡고 있으므로
    그 파일만 거부된다. 두 줄이 한 파일을 쓰는 일은 없다."""
    ov = _Overlap(hold=0.3)
    monkeypatch.setattr(employee, "ask", ov.wrap(
        _two_developer_tasks_on_different_files(employee.ask,
                                                t1b_writes="src/calc.py")))
    slug = engine.start("간단한 계산기를 만들어주세요")
    m = _wait(slug)
    assert ov.max_same == 2
    refused = [e for e in bus.history(slug) if e["type"] == "message"
               and "src/calc.py" in e.get("text", "") and e.get("kind") == "error"]
    assert refused, "예약된 파일을 다른 줄이 썼다"
    assert "EXTRA" not in (store.dir_of(slug) / "src" / "calc.py").read_text(
        encoding="utf-8"), "t1 의 파일이 t1b 의 내용으로 덮였다"
    assert m["status"] in ("done", "stopped")


def test_apply_records_baseline_only_for_files_it_actually_wrote(monkeypatch):
    """거부된 파일을 되돌릴 목록에 넣으면, 포기해서 되돌릴 때 그 파일을 쓰던
    **다른 태스크의 일**을 옛 내용으로 덮는다 (병렬로 돌며 생긴 구멍)."""
    from app.tools import project_fs as pfs
    slug = store.new_project("계산기")
    bus.bind(slug)
    pfs.use(slug)
    try:
        run = engine._Run(slug, "local")
        run.claims["other"] = {"src/a.py"}
        baseline: dict = {}
        work = WorkResult(message_to_team="", summary="", self_check="", files=[
            FileWrite(path="src/a.py", content="mine"),      # 남이 잡은 파일
            FileWrite(path="docs/b.md", content="x"),        # 권한 밖
            FileWrite(path="src/c.py", content="ok")])
        written = engine._apply(work, "developer", run=run, sig="me",
                                baseline=baseline)
    finally:
        pfs.release()
        bus.release()
    assert written == ["src/c.py"]
    assert baseline == {"src/c.py": None}
    assert run.claims["me"] == {"src/c.py"}, "거부된 파일의 예약이 남았다"
    assert not (store.dir_of(slug) / "src" / "a.py").exists()


def test_conflicts_rule():
    from app.agents.schemas import Task
    def t(id, who, files):
        return Task(id=id, title=id, assignee=who, deps=[], files=files,
                    covers=[], done_when="")
    dev_a, dev_b = t("a", "developer", ["src/a.py"]), t("b", "developer", ["src/b.py"])
    assert not engine._conflicts(dev_a, dev_b)
    assert engine._conflicts(dev_a, t("c", "developer", ["./src/a.py"]))
    assert engine._conflicts(dev_a, t("d", "developer", ["src"])), "폴더 예약은 그 아래를 덮는다"
    assert engine._conflicts(dev_a, t("e", "developer", [])), "안 적은 태스크는 무엇을 쓸지 모른다"
    assert not engine._conflicts(dev_a, t("f", "writer", [])), "구역이 다르면 늘 같이 돈다"


def _writer_also_declares_design(real):
    def fake(employee_id, user, schema, history=None, model=None):
        p = real(employee_id, user, schema, history, model=model)
        if schema is Plan and employee_id == roles.PLANNER:
            tasks = [t.model_copy(update={"files": [*t.files, "design/screen.md"]})
                     if t.assignee == "writer" else t for t in p.tasks]
            return p.model_copy(update={"tasks": tasks})
        return p
    return fake


def _widen_writer():
    from app.agents import permissions
    clean, risks = permissions.validate(
        {"writer": {"writes": ["docs", "design"]}})
    return {"overrides": clean, "risks": risks}


def test_overlapping_write_areas_and_files_do_not_run_together(monkeypatch):
    """프로젝트 권한으로 작가에게 design/ 쓰기를 주고, 작가 태스크가 디자이너의
    파일까지 적었다 — 둘은 같은 파일을 쓸 수 있으므로 같이 돌면 안 된다."""
    ov = _Overlap(hold=0.1)
    monkeypatch.setattr(employee, "ask",
                        ov.wrap(_writer_also_declares_design(employee.ask)))
    slug = engine.start("간단한 계산기를 만들어주세요", permissions=_widen_writer())
    m = _wait(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert frozenset({"writer", "designer"}) not in ov.together


def test_overlapping_areas_with_disjoint_files_still_run_together(monkeypatch):
    """구역이 겹쳐도 계획에 적은 파일이 안 겹치면 같이 돈다 (DAY 26).
    DAY 25 에는 구역만 보고 통째로 줄을 세웠다."""
    ov = _Overlap(hold=0.3)
    monkeypatch.setattr(employee, "ask", ov.wrap(employee.ask))
    slug = engine.start("간단한 계산기를 만들어주세요", permissions=_widen_writer())
    m = _wait(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert frozenset({"writer", "designer"}) in ov.together


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
