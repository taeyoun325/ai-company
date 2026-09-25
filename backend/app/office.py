"""사무실 — 지금 누가 어디서 무엇을 하는가 (DAY 25 · 사무실 개편).

## 왜 서버가 정하나

화면이 이벤트를 접어 상태를 짐작하던 시절(DAY 24 까지)에는 규칙이 화면
코드 안에 흩어져 있었다. "Mock 으로 끝낸 일을 완료로 칠까" 같은 판단은
**제품의 규칙**이지 화면의 취향이 아니다. 여기서 한 번 정하고, 화면과
비서실(`secretary.py`)이 같은 답을 쓴다 — 둘이 다르게 말하면 대표는
어느 쪽을 믿어야 할지 모른다.

## 직원 상태 다섯 가지 (사규 §2)

| 상태 | 뜻 | 말풍선 |
|---|---|---|
| `done` 완료 | 이번 단계의 자기 몫이 끝났다 | 완료했어요! |
| `working` 진행 중 | 지금 모델을 부르고 있거나 자기 단계를 돌고 있다 | 일하는 중… |
| `approval` 승인 대기 | **대표 결정이 필요하다** — 회의실에서 기다린다 | 확인해주세요 |
| `integration` 연동 대기 | 외부 연결이 없어 **진짜 일을 못 한다** | 연결 기다려요 |
| `idle` 대기 | 앞 단계를 기다리는 정상 상태 | 업무 대기중 |

규칙:

1. **연동 대기와 대기를 섞지 않는다.** 연동 대기는 대표가 무언가를 줘야
   풀린다 — 그래서 `reason` 에 **무엇이 없는지**를 반드시 적는다.
2. **상태마다 이유를 한 줄 남긴다**(`reason`). 이유 없는 색은 장식이다.
3. **연결 안 된 것을 완료로 표시하지 않는다.** Mock 으로 끝낸 일은
   `done` 이 아니라 `integration` 이다 — 대본이 만든 결과를 대표가 진짜
   완료로 읽는 순간이 이 제품에서 제일 나쁜 순간이다.

우선순위: 승인 대기 > 진행 중 > 연동 대기 > 완료 > 대기. 진행 중이
연동 대기보다 앞인 이유: Mock 으로라도 **지금 움직이고 있다**는 것은
사실이다. 대신 `mock: true` 가 같이 나가고 화면이 MOCK 을 붙인다.

## 모델을 부르지 않는다

전부 이미 있는 기록(메타 · 이벤트 · 사용량)을 읽는다. 사무실을 볼 때마다
돈이 나가면 아무도 사무실을 안 본다.
"""
from __future__ import annotations

import time

from app import deploy, lang, metrics, tenant, usage
from app.agents import roles, staff
from app.database import store
from app.orchestrator import engine

STATES = ("done", "working", "approval", "integration", "idle")

# 부서 — 자리 배치와 비서실의 말투가 이 이름을 쓴다.
# 처음 앉는 팀. 대표가 옮기면(`staff.set_team`) 그 기록이 이긴다 (DAY 26).
DEPT = staff.HOME_TEAM

# 하루 시나리오 (사규 §3) — 이 제품의 파이프라인에 맞춘 12단계.
SCENARIO = ("arrive", "plan", "plan_gate", "tests", "implement", "pytest",
            "review", "task_gate", "rework", "finalize", "saved", "brief")

_MAIN_OWNER = {"PLAN": "strategist", "REPLAN": "strategist",
               "FINALIZE": "strategist", "WRITE_TESTS": "analyst"}


def _participants(a: dict, tasks: list[dict]) -> list[str]:
    """이 승인 건 때문에 회의실에서 기다리는 사람."""
    if a.get("gate") == "plan":
        return [roles.PLANNER, roles.VERIFIER]
    who = (a.get("detail") or {}).get("assignee")
    if not who:
        who = next((t.get("assignee") for t in tasks
                    if t.get("id") == a.get("task_id")), None)
    return [w for w in (who, roles.VERIFIER) if w]


def _latest(events: list[dict]) -> dict:
    """이벤트에서 '지금'을 접는다: 본 줄 단계 · 줄별 단계 · 도는 줄."""
    main: tuple[str, str, float] | None = None
    lanes: dict[str, tuple[str, str, float]] = {}
    active: list[dict] | None = None
    tasks: list[dict] | None = None
    for e in events:
        t = e.get("type")
        if t == "phase":
            lane = e.get("lane")
            row = (e.get("name") or "", e.get("detail") or "", e.get("ts", 0.0))
            if lane:
                lanes[lane] = row
                # 태스크 줄이 움직이면 본 줄의 단계(테스트 작성 등)는 끝났다.
                # 안 지우면 쉬었다 재개한 실행에서 줄 사이의 틈마다 "테스트
                # 선작성 중"이 다시 켜졌다.
                main = None
            else:
                main = row
                lanes = {}             # 본 줄이 말하면 줄들은 끝났다
        elif t == "state":
            if "active" in e:
                active = e.get("active") or []
            if e.get("tasks") is not None:
                tasks = e.get("tasks")
        elif t in ("done", "awaiting"):
            active = []
    return {"main": main, "lanes": lanes, "active": active, "tasks": tasks}


def _integration_items(owner: str) -> tuple[list[dict], dict[str, dict]]:
    """회사 차원의 '연동 대기 항목'(사규 §2)과 직원별 막힌 이유."""
    items: list[dict] = []
    per: dict[str, dict] = {}
    from app import byok
    from app.providers import registry
    with tenant.bind(owner):
        status = registry.status()
        posture = tenant.current()
        byok_missing = (byok.missing(owner)
                        if posture and posture.source == "byok" else [])
        mode = registry.mode()
        mocks = {p["name"]: p for p in status["providers"] if p["mock"]}
    provider_key = {"claude": "anthropic", "gemini": "gemini", "openai": "openai"}
    labels = {"claude": "Anthropic (Claude)", "gemini": "Google (Gemini)",
              "openai": "OpenAI (GPT)"}
    for name, row in sorted(mocks.items()):
        affects = [e.id for e in roles.EMPLOYEES.values()
                   if e.provider == name and staff.is_active(owner, e.id)]
        if not affects:
            continue
        if provider_key[name] in byok_missing:
            why = lang.t("office.int.byok", label=labels[name])
        elif mode == "mock" and row.get("key"):
            why = lang.t("office.int.mockMode", label=labels[name])
        else:
            why = lang.t("office.int.noKey", label=labels[name])
        item = {"key": f"provider:{name}", "label": labels[name], "why": why,
                "affects": affects, "fix": "/settings"}
        items.append(item)
        for a in affects:
            per[a] = item
    if (reason := deploy.allow_code_execution()) is not None:
        item = {"key": "pytest", "label": "pytest",
                "why": lang.t("office.int.noSandbox"),
                "detail": reason, "affects": [roles.VERIFIER], "fix": None}
        items.append(item)
    return items, per


def snapshot(owner: str = "local", slug: str | None = None,
             *, now: float | None = None) -> dict:
    """사무실 한 장. `slug` 가 없으면 아무 일도 없는 사무실이다."""
    now = now or time.time()
    m = store.meta(slug) if slug else {}
    events = metrics.events_of(slug) if m else []
    met = metrics.compute(events, now=now) if events else None
    cur = _latest(events)
    running = bool(m) and engine.is_running(slug)
    status = m.get("status") if m else None
    tasks = cur["tasks"] if cur["tasks"] is not None else (m.get("tasks") or [])
    approvals = [a for a in (m.get("approvals") or []) if a.get("status") == "pending"]
    gate_list = m.get("gates") or []
    # 도는 중에는 메모리가 최신이다 — 메타의 사용량은 태스크가 끝날 때만 쓰인다.
    usage_rows = (usage.agents_of(slug) if running else None) or m.get("usage") or {}
    inflight = {c["agent"]: c for c in (met or {}).get("inflight", [])}
    # 끝난 줄의 마지막 단계(REVIEW)가 남아 있으면 검증자가 영영 "검토 중"
    # 으로 보인다. **지금 도는 줄**만 본다.
    live_ids = ({a.get("task") for a in cur["active"]}
                if cur["active"] is not None else set(cur["lanes"]))
    lanes = ({k: v for k, v in cur["lanes"].items() if k in live_ids}
             if running else {})
    main = cur["main"] if running else None
    lanes_live = bool(lanes)
    checkpoint = m.get("checkpoint") or {}
    stage = checkpoint.get("stage") or ("tasks" if checkpoint.get("plan") else None)
    int_items, blocked = _integration_items(owner)
    manual_busy = None
    if m and (status == "manual" or m.get("mode") == "manual"):
        from app.database import index
        try:
            manual_busy = index.lock_holder(slug)
        except Exception:                                      # noqa: BLE001
            manual_busy = None
    by_task = {t.get("id"): t for t in tasks}
    names = {e: staff.name_of(owner, e) for e in roles.ids()}

    in_meeting: dict[str, dict] = {}
    for a in approvals:
        for w in _participants(a, tasks):
            in_meeting.setdefault(w, a)

    rows = []
    for e in roles.EMPLOYEES.values():
        hired = staff.is_active(owner, e.id)
        mine = [t for t in tasks if t.get("assignee") == e.id]
        done_n = sum(1 for t in mine if t.get("status") == "done")
        u = usage_rows.get(e.id) or {}
        row = {
            "id": e.id, "name": names[e.id], "dept": staff.team_of(owner, e.id),
            "home_dept": DEPT.get(e.id, "etc"),
            "role": e.info()["role"], "provider": e.provider,
            "hired": hired, "mock": e.id in blocked,
            "task": None, "progress": {"done": done_n, "total": len(mine)},
            "calls": int(u.get("calls") or 0), "cost": float(u.get("cost") or 0.0),
            "avg_ms": (round(float(u.get("latency_ms") or 0) / u["calls"], 1)
                       if u.get("calls") else None),
            "inflight_ms": None, "place": "desk",
        }
        state, reason = _decide(e.id, row, m=m, running=running, status=status,
                                manual_busy=manual_busy,
                                mine=mine, tasks=tasks, by_task=by_task,
                                meeting=in_meeting.get(e.id), lanes=lanes,
                                main=main, lanes_live=lanes_live,
                                inflight=inflight.get(e.id), stage=stage,
                                blocked=blocked.get(e.id), names=names, now=now)
        row["state"] = state
        row["reason"] = reason
        if state == "approval":
            row["place"] = "meeting"
        elif not hired:
            row["place"] = "away"
        rows.append(row)

    return {
        "now": now,
        "run": _run_view(slug, m, running, met, tasks, approvals) if m else None,
        "employees": rows,
        "approvals": approvals,
        "gates": gate_list,
        "meeting": {"who": sorted(in_meeting),
                    "approval_id": approvals[0]["id"] if approvals else None},
        "integrations": int_items,
        "scenario": _scenario(m, main, lanes, approvals, gate_list, stage, tasks)
        if m else [{"key": k, "state": "todo"} for k in SCENARIO],
        "metrics": ({"inflight": met["inflight"], "parallelism": met["parallelism"],
                     "wall_ms": met["wall_ms"], "human_wait_ms": met["human_wait_ms"]}
                    if met else None),
    }


def _decide(eid: str, row: dict, *, m: dict, running: bool, status: str | None,
            manual_busy: str | None = None,
            mine: list[dict], tasks: list[dict], by_task: dict, meeting: dict | None,
            lanes: dict, main, lanes_live: bool, inflight: dict | None,
            stage: str | None, blocked: dict | None, names: dict,
            now: float) -> tuple[str, str]:
    if not row["hired"]:
        return "idle", lang.t("office.r.away")

    # ① 승인 대기 — 대표가 결정해야 풀린다.
    if meeting is not None:
        row["task"] = {"id": meeting.get("task_id"), "title": meeting.get("title")}
        key = "office.r.held" if meeting.get("held") else "office.r.approval"
        return "approval", lang.t(key, title=meeting.get("title", ""))

    # ② 진행 중 — 지금 움직이고 있는 증거가 있을 때만.
    # MANUAL 은 실행 스레드가 없다. 대신 지시 하나가 잡은 점유(`index` 의
    # 잠금)가 "지금 이 사람이 대표 지시를 처리 중"이라는 증거다.
    if manual_busy == eid:
        label = lang.t("office.r.manualBusy")
        if inflight is not None:
            row["inflight_ms"] = inflight["elapsed_ms"]
            label += " · " + lang.t("office.r.waitingModel",
                                    s=int(inflight["elapsed_ms"] // 1000),
                                    model=inflight.get("model") or "")
        return "working", label
    if running:
        working = _working(eid, row, lanes=lanes, main=main,
                           lanes_live=lanes_live, by_task=by_task, tasks=tasks,
                           inflight=inflight)
        if working is not None:
            return "working", working

    # ③ 연동 대기 — 무엇이 없는지 적는다(규칙 ①).
    if blocked is not None:
        if row["progress"]["done"] or (eid in (roles.PLANNER, roles.VERIFIER)
                                       and stage):
            return "integration", lang.t("office.r.mockDone",
                                         label=blocked["label"])
        return "integration", blocked["why"]

    if not m:
        return "idle", lang.t("office.r.noRun")

    # ④ 완료 — 이번 실행에서 자기 몫이 끝났다.
    if status == "done":
        if eid == roles.PLANNER:
            return "done", lang.t("office.r.finalDone")
        if eid == roles.VERIFIER:
            return "done", lang.t("office.r.reviewsDone",
                                  n=(m.get("score_detail") or {}).get("tasks", "-"))
        if mine:
            return "done", lang.t("office.r.tasksDone", n=len(mine))
        return "idle", lang.t("office.r.noTask")
    if eid == roles.PLANNER and stage:
        return "done", lang.t("office.r.planDone")
    if eid == roles.VERIFIER and stage == "tasks":
        if tasks and all(t.get("status") in ("done", "awaiting") for t in tasks):
            return "done", lang.t("office.r.reviewsDone",
                                  n=f"{sum(1 for t in tasks if t.get('status') == 'done')}"
                                    f"/{len(tasks)}")
        return "idle", lang.t("office.r.waitReview")
    if mine and all(t.get("status") == "done" for t in mine):
        return "done", lang.t("office.r.tasksDone", n=len(mine))

    # ⑤ 대기 — 무엇을 기다리는지 적는다.
    if status == "manual" or m.get("mode") == "manual":
        return "idle", lang.t("office.r.manualIdle")
    if status == "stopped":
        return "idle", lang.t("office.r.stopped",
                              why=(m.get("stopped_reason") or "")[:80])
    if status == "awaiting":
        return "idle", lang.t("office.r.parked")
    todo = [t for t in mine if t.get("status") != "done"]
    if todo:
        row["task"] = {"id": todo[0].get("id"), "title": todo[0].get("title")}
        blocker = _blocker(todo[0], by_task, m)
        if blocker:
            return "idle", lang.t("office.r.waitDep", task=blocker)
        return "idle", lang.t("office.r.waitTurn", task=todo[0].get("title", ""))
    if not stage and eid != roles.PLANNER:
        return "idle", lang.t("office.r.waitPlan", who=names[roles.PLANNER])
    return "idle", lang.t("office.r.noTask")


def _working(eid: str, row: dict, *, lanes: dict, main, lanes_live: bool,
             by_task: dict, tasks: list[dict], inflight: dict | None) -> str | None:
    """지금 움직이고 있는 증거. 없으면 None."""
    label = None
    # 줄(태스크)에서의 역할
    for lane, (name, _detail, _ts) in lanes.items():
        t = by_task.get(lane) or {}
        title = t.get("title", lane)
        if name in ("IMPLEMENT", "TEST") and t.get("assignee") == eid:
            row["task"] = {"id": lane, "title": title}
            label = lang.t("office.r.implement" if name == "IMPLEMENT"
                           else "office.r.pytest", task=title)
            break
        if name == "REVIEW" and eid == roles.VERIFIER:
            row["task"] = {"id": lane, "title": title}
            label = lang.t("office.r.review", task=title)
            break
    # 본 줄의 단계 — 태스크 줄이 없을 때만
    if label is None and main and not lanes:
        name = main[0]
        if _MAIN_OWNER.get(name) == eid:
            label = lang.t(f"office.r.main.{name}")
    if inflight is not None:
        secs = int(inflight["elapsed_ms"] // 1000)
        row["inflight_ms"] = inflight["elapsed_ms"]
        wait = lang.t("office.r.waitingModel", s=secs, model=inflight.get("model") or "")
        return f"{label} · {wait}" if label else wait
    return label


def _blocker(task: dict, by_task: dict, m: dict) -> str | None:
    """이 태스크가 기다리는 앞 태스크의 제목."""
    plan = (m.get("checkpoint") or {}).get("plan") or {}
    deps = next((t.get("deps") or [] for t in plan.get("tasks", [])
                 if t.get("id") == task.get("id")), [])
    for d in deps:
        dep = by_task.get(d)
        if dep and dep.get("status") != "done":
            return dep.get("title", d)
    return None


def _run_view(slug: str, m: dict, running: bool, met: dict | None,
              tasks: list[dict], approvals: list[dict]) -> dict:
    return {
        "slug": slug, "name": m.get("name") or slug,
        "requirement": m.get("requirement", ""),
        "status": m.get("status"), "running": running,
        "stopped_reason": m.get("stopped_reason"),
        "created_at": m.get("created_at"), "mock": bool(m.get("mock")),
        "cost": float(m.get("cost") or 0.0), "score": m.get("score"),
        "tasks_done": sum(1 for t in tasks if t.get("status") == "done"),
        "tasks_total": len(tasks), "pending": len(approvals),
        "held": sum(1 for a in approvals if a.get("held")),
        "confidence": (m.get("score_detail") or {}).get("confidence"),
    }


def _scenario(m: dict, main_row, lanes: dict, approvals: list[dict],
              gate_list: list[str], stage: str | None,
              tasks: list[dict]) -> list[dict]:
    """하루 시나리오 12단계(사규 §3)의 지금 모습.

    상태: `done` · `current` · `todo` · `off`(그 승인 지점을 안 켰다) ·
    `skip`(이번에는 일어나지 않았다).
    """
    status = m.get("status")
    main = main_row[0] if (main_row and not lanes) else None
    lane_names = {v[0] for v in lanes.values()}
    finished = status == "done"
    all_done = bool(tasks) and all(t.get("status") == "done" for t in tasks)
    plan_pending = any(a.get("gate") == "plan" for a in approvals)
    task_pending = any(a.get("gate") == "task" for a in approvals)
    plan_gate_on = "plan" in gate_list
    task_gate_on = any(g.startswith("task") or g == "confidence" for g in gate_list)
    sd = m.get("score_detail") or {}
    reworked = bool(sd.get("reworks") or sd.get("replans"))

    def st(key: str) -> str:
        if key == "arrive":
            return "done"
        if key == "plan":
            return "current" if main in ("PLAN",) else (
                "done" if (m.get("checkpoint") or {}).get("plan") else "todo")
        if key == "plan_gate":
            if not plan_gate_on:
                return "off"
            return "current" if plan_pending else ("done" if stage == "tasks" else "todo")
        if key == "tests":
            return "current" if main == "WRITE_TESTS" else (
                "done" if stage == "tasks" else "todo")
        if key in ("implement", "pytest", "review"):
            name = {"implement": "IMPLEMENT", "pytest": "TEST", "review": "REVIEW"}[key]
            if name in lane_names or main == name:
                return "current"
            return "done" if (all_done or finished) else "todo"
        if key == "task_gate":
            if not task_gate_on:
                return "off"
            return "current" if task_pending else ("done" if finished else "todo")
        if key == "rework":
            if main == "REPLAN":
                return "current"
            return "done" if reworked else ("skip" if finished else "todo")
        if key == "finalize":
            return "current" if main == "FINALIZE" else ("done" if finished else "todo")
        if key in ("saved", "brief"):
            return "done" if finished else "todo"
        return "todo"

    return [{"key": k, "state": st(k)} for k in SCENARIO]
