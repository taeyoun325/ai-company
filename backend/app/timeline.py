"""B5 — 협업 타임라인.

`logs/trace.jsonl`을 읽어 "누가 언제 무엇을 넘겼는지"를 구간으로 만든다.
핸드오프와 재작업 구간이 눈에 보이는 것이 목적이다.

단계마다 주인공이 다르다:
  PLAN·REPLAN·FINALIZE → PM,  WRITE_TESTS·REVIEW → QA,
  IMPLEMENT → DEV,  TEST → 시스템(파이썬이 pytest를 직접 돌린다)
"""
import json

from app import config

PHASE_OWNER = {
    "PLAN": "PM", "REPLAN": "PM", "FINALIZE": "PM",
    "WRITE_TESTS": "QA", "REVIEW": "QA",
    "IMPLEMENT": "DEV", "TEST": "SYSTEM",
}
PHASE_LABEL = {
    "PLAN": "기획", "WRITE_TESTS": "테스트 선작성", "IMPLEMENT": "구현",
    "TEST": "테스트 실행", "REVIEW": "검증", "REPLAN": "재기획", "FINALIZE": "최종검수",
}


def _events(run_id: str) -> list[dict]:
    path = config.LOGS / "trace.jsonl"
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue          # 쓰는 도중에 읽으면 마지막 줄이 잘릴 수 있다
            if ev.get("run") == run_id:
                out.append(ev)
    return out


def build(run_id: str) -> dict:
    """구간 목록과 표시(마커)를 만든다."""
    evs = _events(run_id)
    if not evs:
        return {"run": run_id, "segments": [], "markers": [], "duration": 0,
                "started_at": None}

    t0 = evs[0]["ts"]
    tend = evs[-1]["ts"]

    segments: list[dict] = []
    markers: list[dict] = []
    open_seg: dict | None = None

    for ev in evs:
        t = ev["ts"] - t0

        if ev["type"] == "phase":
            if open_seg:
                open_seg["end"] = t
                segments.append(open_seg)
            name = ev.get("name", "")
            open_seg = {
                "phase": name,
                "label": PHASE_LABEL.get(name, name),
                "agent": PHASE_OWNER.get(name, "SYSTEM"),
                "detail": ev.get("detail", ""),
                "start": t, "end": t,
            }

        elif ev["type"] == "message" and ev.get("kind") == "verdict":
            text = ev.get("text", "")
            if ev.get("agent") == "QA":
                fail = "반려" in text
                markers.append({"t": t, "kind": "fail" if fail else "pass",
                                "label": "반려" if fail else "통과"})

        elif ev["type"] == "message" and ev.get("kind") == "error":
            markers.append({"t": t, "kind": "error",
                            "label": (ev.get("text") or "")[:60]})

        elif ev["type"] == "done":
            markers.append({"t": t, "kind": "done" if ev.get("ok") else "stopped",
                            "label": f"완성도 {ev.get('score', 0)}"})

    if open_seg:
        open_seg["end"] = tend - t0
        segments.append(open_seg)

    # 같은 단계가 연달아 나오면 사람이 읽기 어렵다 — 회차 번호를 붙인다
    seen: dict[str, int] = {}
    for s in segments:
        seen[s["phase"]] = seen.get(s["phase"], 0) + 1
        s["nth"] = seen[s["phase"]]
        s["dur"] = round(s["end"] - s["start"], 2)

    return {
        "run": run_id,
        "started_at": t0,
        "duration": round(tend - t0, 2),
        "segments": segments,
        "markers": markers,
        "handoffs": _handoffs(segments),
    }


def _handoffs(segments: list[dict]) -> list[dict]:
    """에이전트가 바뀌는 지점 = 핸드오프."""
    out = []
    for a, b in zip(segments, segments[1:]):
        if a["agent"] != b["agent"]:
            out.append({"t": b["start"], "from": a["agent"], "to": b["agent"],
                        "label": f"{a['label']} → {b['label']}"})
    return out


def summary(run_id: str) -> dict:
    """에이전트별 점유 시간. 누가 병목인지 바로 보인다."""
    tl = build(run_id)
    per: dict[str, float] = {}
    for s in tl["segments"]:
        per[s["agent"]] = round(per.get(s["agent"], 0) + s["dur"], 2)
    return {"duration": tl["duration"], "per_agent": per,
            "handoffs": len(tl["handoffs"]),
            "reworks": sum(1 for m in tl["markers"] if m["kind"] == "fail")}
