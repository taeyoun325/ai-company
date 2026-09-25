"""실행 하나의 지표 — "왜 느린가" 에 답한다 (DAY 25 · 관측성).

## 무엇이 있었고 무엇이 없었나

비용은 보였다(`usage`). 인계 근거도 구조로 남았다(`handoff` 이벤트).
그런데 **시간**이 없었다. "이 프로젝트가 왜 12분이나 걸렸나"를 물으면
로그를 위에서부터 읽으며 타임스탬프를 빼는 수밖에 없었다.

## 원자료는 이벤트다

모델 호출마다 `call` 이벤트가 시작·끝으로 두 번 나온다(`providers/base.py`).
단계가 바뀔 때마다 `phase` 이벤트가 나온다. 둘 다 트레이스 파일에 남으므로
**어느 인스턴스에서 물어도** 같은 답이 나온다(`bus.read_trace`) — 실행이
다른 인스턴스에서 돌았어도.

지표를 따로 저장하지 않는 이유: 저장된 지표와 이벤트가 어긋나는 날이
온다. 이벤트가 진실이고, 지표는 그걸 접은 것이다.

## 무엇을 내나

| 칸 | 답하는 질문 |
|---|---|
| `by_agent` | 누가 느린가 — 평균·p50·p95·최대, 기다린 시간, 재시도, 실패 |
| `by_phase` | 어느 단계에서 시간을 쓰나 — 계획·테스트 작성·구현·pytest·검토 |
| `slowest` | 가장 오래 걸린 호출 다섯 |
| `inflight` | 지금 응답을 기다리는 호출과 **몇 초째인지** |
| `parallelism` | 모델 호출 시간 합 ÷ 벽시계 — 1 을 넘으면 실제로 동시에 일했다 |
"""
from __future__ import annotations

import time

from app import bus

# 단계 이름 중 "사람이 기다린 시간"(승인 대기)은 모델이 쓴 시간과 섞지 않는다.
_WAIT_PHASES = {"AWAITING"}


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[k]


def events_of(slug: str) -> list[dict]:
    """트레이스 파일이 있으면 그것을, 없으면 이 프로세스의 메모리를 본다.

    **시각순**으로 돌려준다. 번호는 프로세스마다 따로 세지므로(재시작 전
    기록이 섞인 파일), 번호순은 시간순이 아닐 수 있다.
    """
    ev = bus.read_trace(slug) or bus.history(slug)
    return sorted(ev, key=lambda e: (e.get("ts", 0.0), e.get("id", 0)))


def compute(events: list[dict], *, now: float | None = None) -> dict:
    now = now or time.time()
    starts: dict[int, dict] = {}
    calls: list[dict] = []
    for e in events:
        if e.get("type") != "call":
            continue
        cid = e.get("call_id")
        if e.get("stage") == "start":
            starts[cid] = e
        elif e.get("stage") == "end":
            s = starts.pop(cid, None)
            calls.append({
                "call_id": cid, "agent": e.get("agent"),
                "provider": e.get("provider"), "model": e.get("model"),
                "ok": bool(e.get("ok")), "error": e.get("error"),
                "ms": float(e.get("ms") or 0.0),
                "model_ms": float(e.get("model_ms") or 0.0),
                "wait_ms": float(e.get("wait_ms") or 0.0),
                "attempts": int(e.get("attempts") or 1),
                "input": int(e.get("input") or 0),
                "output": int(e.get("output") or 0),
                "started_at": s.get("ts") if s else None,
                "ended_at": e.get("ts"),
            })

    by_agent: dict[str, dict] = {}
    for c in calls:
        a = by_agent.setdefault(c["agent"] or "?", {
            "calls": 0, "ok": 0, "failed": 0, "total_ms": 0.0,
            "wait_ms": 0.0, "retries": 0, "output": 0, "_ms": []})
        a["calls"] += 1
        a["ok" if c["ok"] else "failed"] += 1
        a["total_ms"] += c["ms"]
        a["wait_ms"] += c["wait_ms"]
        a["retries"] += max(0, c["attempts"] - 1)
        a["output"] += c["output"]
        a["_ms"].append(c["ms"])
    for a in by_agent.values():
        ms = a.pop("_ms")
        a["avg_ms"] = round(a["total_ms"] / a["calls"], 1) if a["calls"] else 0.0
        a["p50_ms"] = round(_pct(ms, 50), 1)
        a["p95_ms"] = round(_pct(ms, 95), 1)
        a["max_ms"] = round(max(ms), 1) if ms else 0.0
        a["total_ms"] = round(a["total_ms"], 1)
        a["wait_ms"] = round(a["wait_ms"], 1)
        # 출력 토큰/초 — 모델이 느린 것인가(낮다), 많이 쓴 것인가(높다).
        secs = a["total_ms"] / 1000
        a["tokens_per_sec"] = round(a["output"] / secs, 1) if secs > 0 else None

    # 단계별 시간 — 줄(lane)마다 따로 접는다. 병렬로 돌면 한 줄의 단계가
    # 다른 줄의 단계 이벤트에 끊기지 않아야 한다.
    by_phase: dict[str, dict] = {}
    open_phase: dict[str, tuple[str, float]] = {}
    first_ts = events[0]["ts"] if events else now
    last_ts = events[-1]["ts"] if events else now
    # 멈췄다 재개하면 `done` 뒤에 이벤트가 더 온다. **마지막** done 뒤에
    # 일이 더 없어야 끝난 것이다.
    last_done = max((i for i, e in enumerate(events) if e.get("type") == "done"),
                    default=-1)
    finished = last_done >= 0 and not any(
        e.get("type") in ("phase", "call") for e in events[last_done + 1:])

    def _close(lane: str, until: float) -> None:
        cur = open_phase.pop(lane, None)
        if cur is None:
            return
        name, since = cur
        row = by_phase.setdefault(name, {"ms": 0.0, "count": 0})
        row["ms"] += max(0.0, (until - since) * 1000)
        row["count"] += 1

    for e in events:
        if e.get("type") == "phase":
            lane = str(e.get("lane") or "main")
            if lane == "main":
                # 본 줄이 다시 말하면(재기획·최종 검수) 태스크 줄들은 전부
                # 끝난 뒤다 — 본 줄은 줄이 하나도 안 돌 때만 움직인다.
                for other in list(open_phase):
                    _close(other, e["ts"])
            else:
                # 태스크 줄이 뜨면 본 줄의 단계(테스트 작성 등)는 거기서
                # 끝났다. 안 닫으면 WRITE_TESTS 가 구현 시간 전체를 먹는다.
                # 승인 대기 뒤에 재개한 실행도 본 줄 단계 없이 곧장 줄을
                # 띄우므로 같은 규칙으로 기다림이 닫힌다.
                _close("main", e["ts"])
                _close(lane, e["ts"])
            open_phase[lane] = (e.get("name") or "?", e["ts"])
        elif e.get("type") == "awaiting":
            for lane in list(open_phase):
                _close(lane, e["ts"])
            open_phase["main"] = ("AWAITING", e["ts"])
        elif e.get("type") == "done":
            for lane in list(open_phase):
                _close(lane, e["ts"])
    end = last_ts if finished else now
    for lane in list(open_phase):
        _close(lane, end)
    for row in by_phase.values():
        row["ms"] = round(row["ms"], 1)

    inflight = [{"call_id": cid, "agent": s.get("agent"),
                 "provider": s.get("provider"), "model": s.get("model"),
                 "elapsed_ms": round((now - s["ts"]) * 1000, 1)}
                for cid, s in starts.items()] if not finished else []

    wall_ms = max(0.0, (end - first_ts) * 1000)
    waited_ms = sum(r["ms"] for n, r in by_phase.items() if n in _WAIT_PHASES)
    busy_ms = sum(c["ms"] for c in calls)
    work_wall = max(0.0, wall_ms - waited_ms)
    return {
        "wall_ms": round(wall_ms, 1),
        "human_wait_ms": round(waited_ms, 1),
        "model_ms": round(busy_ms, 1),
        "parallelism": round(busy_ms / work_wall, 2) if work_wall > 0 else None,
        "calls": len(calls),
        "failed_calls": sum(1 for c in calls if not c["ok"]),
        "retries": sum(max(0, c["attempts"] - 1) for c in calls),
        "by_agent": by_agent,
        "by_phase": by_phase,
        "slowest": sorted(calls, key=lambda c: c["ms"], reverse=True)[:5],
        "inflight": inflight,
        "finished": finished,
    }


def of(slug: str) -> dict:
    return compute(events_of(slug))
