"""비서실 — 대표 지시창 (DAY 25 · 사규 §4).

## 무엇을 하나

대표가 아무 때나 묻는 창구다. 정해진 질문에 **정해진 사람이** 답한다:

| 대표 입력 | 답하는 쪽 | 답 |
|---|---|---|
| 현황 보고 | 비서실 | 시각 · 단계 · 진행 중 부서와 진행률 · 다음 순서 |
| 왜 늦어져? | 비서실 | **진짜 병목 하나** + 원인 |
| [이름] 뭐해? | 그 직원 | 자기 상황 · 맡은 태스크 진행률 · 쓴 돈과 걸린 시간 |
| 회의 소집 | 전원 | 한 명씩 순서대로 한 줄 |
| 지금 브리핑 | 비서실 | 끝난 것 · 남은 것 · 비용 · 시간 · 결재 · 막힌 것 |
| 집중 모드 | 전원 | 자율 행동 중단 · 자리 복귀 (화면이 따른다) |
| 승인할게 | — | 결재가 한 건이면 처리, 여러 건이면 고르게 한다 |

## 모델을 부르지 않는다

답은 전부 기록에서 나온다(`office.snapshot` · `metrics`). 비서실이 모델을
부르면 "왜 늦어?"라고 묻는 것 자체가 늦어지고 돈이 든다. 그리고 모델이
지어낸 보고는 기록과 어긋날 수 있다 — 보고는 **기록을 읽어 주는 것**이다.

## "왜 늦어져?" 규칙 (사규 §4 · 순서가 곧 우선순위)

1. 대표 결재 대기 중이면 **그것부터** 말한다. 다른 얘기를 섞지 않는다.
2. 작업 중이면 가장 오래 기다리는 호출 하나 — 부서 · 진행률 · 정상 여부.
3. 외부 연동 문제면 무엇이 없어서 못 하는지 정확히.
4. 문제가 없으면 "지연 없습니다" 한 줄.
5. "열심히 하고 있습니다" 같은 내용 없는 답은 하지 않는다.
"""
from __future__ import annotations

import re
import time

from app import lang, office

INTENTS = ("status", "why", "whois", "meeting", "brief", "focus", "unfocus",
           "approve", "help")

# 대표가 쓰는 말. 세 언어를 다 본다 — 영어 화면에서 한국어로 물어도 된다.
_WORDS = {
    # 승인은 **되돌릴 수 없는 동작**이다. "승인 대기 뭐 있어?" 같은 질문이
    # 결재가 되면 안 되므로, 명령으로만 쓰이는 모양만 받는다.
    "approve": (r"승인\s*할게", r"승인\s*해\s*줘", r"승인\s*합니다",
                r"승인\s*해$", r"^approve\b", r"\bi approve\b",
                r"\bapprove it\b", r"承認します", r"承認して"),
    "unfocus": (r"집중\s*모드\s*(해제|끄|꺼|off)", r"focus\s*(mode)?\s*off",
                r"unfocus", r"集中モード(解除|オフ)"),
    "focus": (r"집중", r"\bfocus\b", r"集中"),
    "meeting": (r"회의", r"\bmeeting\b", r"会議"),
    "brief": (r"브리핑", r"\bbrief", r"ブリーフィング"),
    "why": (r"왜", r"늦", r"느려", r"지연", r"\bwhy\b", r"\bslow", r"\blate\b",
            r"遅", r"なぜ"),
    "status": (r"현황", r"상황", r"진행", r"보고", r"\bstatus\b", r"\breport\b",
               r"状況", r"現況", r"進捗"),
}
_DOING = (r"뭐\s*해", r"뭐하", r"뭐\s*하고", r"doing", r"何して", r"なにして")


def parse(text: str, names: dict[str, str]) -> tuple[str, str | None]:
    """대표 입력 → (의도, 대상 직원). 이름·직함·id 중 하나라도 맞으면 그 직원."""
    t = (text or "").strip()
    low = t.lower()
    who = None
    for eid, name in names.items():
        role_words = {eid, name.lower(), lang.t(f"role.{eid}").lower()}
        for loc in lang.LANGS:
            with lang.bind(loc):
                role_words.add(lang.t(f"role.{eid}").lower())
                role_words.add(lang.t(f"office.dept.{office.DEPT[eid]}").lower())
        if any(w and w in low for w in role_words):
            who = eid
            break
    if who and any(re.search(p, low) for p in _DOING):
        return "whois", who
    for intent in ("approve", "unfocus", "focus", "meeting", "brief", "why",
                   "status"):
        if any(re.search(p, low) for p in _WORDS[intent]):
            return intent, who
    if who:
        return "whois", who
    return "help", None


def _clock(ts: float, tz_offset: int | None) -> str:
    """화면의 시간대로. `tz_offset` 은 JS 의 `getTimezoneOffset()` (분, 부호 반대)."""
    if tz_offset is None:
        return time.strftime("%H:%M", time.localtime(ts))
    return time.strftime("%H:%M", time.gmtime(ts - tz_offset * 60))


def _dept(eid: str) -> str:
    return lang.t(f"office.dept.{office.DEPT.get(eid, 'etc')}")


def _line(who: str, text: str) -> dict:
    return {"who": who, "text": text}


def answer(text: str, owner: str = "local", slug: str | None = None, *,
           tz_offset: int | None = None, now: float | None = None) -> dict:
    """대표 한 마디에 대한 답. 모델을 부르지 않는다."""
    now = now or time.time()
    snap = office.snapshot(owner, slug, now=now)
    names = {e["id"]: e["name"] for e in snap["employees"]}
    intent, who = parse(text, names)
    fn = {"status": _status, "why": _why, "whois": _whois,
          "meeting": _meeting, "brief": _brief, "focus": _focus,
          "unfocus": _unfocus, "approve": _approve,
          "help": _help}[intent]
    out = fn(snap, who=who, owner=owner, slug=slug,
             clock=_clock(now, tz_offset), now=now)
    out["intent"] = intent
    return out


# ── 답 ──────────────────────────────────────────────────────────────
def _step_label(key: str) -> str:
    return lang.t(f"office.step.{key}")


def _current_step(snap: dict) -> str | None:
    cur = [s["key"] for s in snap["scenario"] if s["state"] == "current"]
    return cur[0] if cur else None


def _next_step(snap: dict) -> str | None:
    seen_current = False
    for s in snap["scenario"]:
        if s["state"] == "current":
            seen_current = True
            continue
        if s["state"] == "todo" and (seen_current or not _current_step(snap)):
            return s["key"]
    return None


def _progress(snap: dict) -> str:
    parts = []
    for e in snap["employees"]:
        p = e["progress"]
        if p["total"]:
            parts.append(f"{_dept(e['id'])} {p['done']}/{p['total']}")
    return " · ".join(parts)


def _status(snap, *, clock, **_):
    run = snap["run"]
    if run is None:
        return {"lines": [_line("secretary", lang.t("sec.noRun", time=clock))]}
    step = _current_step(snap)
    working = [e for e in snap["employees"] if e["state"] == "working"]
    lines = [lang.t("sec.status.head", time=clock, name=run["name"],
                    step=_step_label(step) if step
                    else lang.t(f"sec.runStatus.{run['status']}"))]
    if working:
        lines.append(lang.t("sec.status.working", who=", ".join(
            f"{_dept(e['id'])}({e['name']}) — {e['reason']}" for e in working)))
    prog = _progress(snap)
    if prog:
        lines.append(lang.t("sec.status.progress", progress=prog,
                            done=run["tasks_done"], total=run["tasks_total"]))
    if run["pending"]:
        lines.append(lang.t("sec.status.pending", n=run["pending"]))
    nxt = _next_step(snap)
    if nxt and run["status"] in ("running", "awaiting"):
        lines.append(lang.t("sec.status.next", step=_step_label(nxt)))
    return {"lines": [_line("secretary", "\n".join(lines))]}


def _why(snap, **_):
    """사규 §4 의 순서 그대로. 병목은 **하나**만 말한다."""
    run = snap["run"]
    say = []
    # 멈춘 실행에 남은 결재는 병목이 아니다 — 승인해도 재개하기 전에는 안
    # 넘어간다. 그때의 병목은 "멈춰 있다"는 사실이다.
    if run is not None and run["status"] == "stopped":
        say.append(lang.t("sec.why.stopped", why=run.get("stopped_reason") or "-",
                          done=run["tasks_done"], total=run["tasks_total"]))
        if snap["approvals"]:
            say.append(lang.t("sec.why.stoppedPending", n=len(snap["approvals"])))
        return {"lines": [_line("secretary", "\n".join(say))]}
    # ① 대표 결재 대기
    if snap["approvals"]:
        a = snap["approvals"][0]
        waiting = len(snap["meeting"]["who"])
        key = "sec.why.held" if a.get("held") else "sec.why.approval"
        nxt = lang.t("sec.why.nextPlan") if a.get("gate") == "plan" \
            else lang.t("sec.why.nextTask")
        say.append(lang.t(key, n=waiting, title=a.get("title", ""), next=nxt))
        if len(snap["approvals"]) > 1:
            say.append(lang.t("sec.why.more", n=len(snap["approvals"]) - 1))
        blocked = [i for i in snap["integrations"]]
        if blocked:
            say.append(lang.t("sec.why.alsoIntegration", n=len(blocked)))
        return {"lines": [_line("secretary", "\n".join(say))]}

    if run is None:
        # 도는 일은 없어도, 일을 맡기는 순간 막힐 것이 있으면 말한다(규칙 ③).
        say.append(lang.t("sec.why.noRun"))
        if snap["integrations"]:
            i = snap["integrations"][0]
            say.append(lang.t("sec.why.integration", what=i["why"],
                              who=", ".join(_dept(a) for a in i["affects"])))
            if len(snap["integrations"]) > 1:
                say.append(lang.t("sec.why.moreIntegration",
                                  n=len(snap["integrations"]) - 1))
        return {"lines": [_line("secretary", "\n".join(say))]}

    # 멈춰 있으면 그게 병목이다.
    if run["status"] == "stopped":
        return {"lines": [_line("secretary", lang.t(
            "sec.why.stopped", why=run.get("stopped_reason") or "-",
            done=run["tasks_done"], total=run["tasks_total"]))]}

    # ② 작업 중 — 가장 오래 기다리는 호출 하나
    if run["running"]:
        inflight = (snap.get("metrics") or {}).get("inflight") or []
        working = {e["id"]: e for e in snap["employees"] if e["state"] == "working"}
        if inflight:
            c = max(inflight, key=lambda x: x["elapsed_ms"])
            e = working.get(c["agent"]) or next(
                (x for x in snap["employees"] if x["id"] == c["agent"]), None)
            secs = int(c["elapsed_ms"] // 1000)
            p95 = _p95_secs(snap, c["agent"])
            normal = secs <= max(90, int(p95 * 1.5)) if p95 else secs <= 90
            key = "sec.why.callOk" if normal else "sec.why.callSlow"
            say.append(lang.t(
                key, dept=_dept(c["agent"]), name=e["name"] if e else c["agent"],
                s=secs, model=c.get("model") or "", p95=p95 or "-",
                task=((e or {}).get("task") or {}).get("title") or
                lang.t("sec.why.noTask"),
                done=run["tasks_done"], total=run["tasks_total"]))
        elif working:
            e = next(iter(working.values()))
            say.append(lang.t("sec.why.working", dept=_dept(e["id"]),
                              name=e["name"], reason=e["reason"],
                              done=run["tasks_done"], total=run["tasks_total"]))
        if say:
            return {"lines": [_line("secretary", "\n".join(say))]}

    # ③ 외부 연동
    if snap["integrations"]:
        i = snap["integrations"][0]
        who = ", ".join(_dept(a) for a in i["affects"])
        say.append(lang.t("sec.why.integration", what=i["why"], who=who))
        if len(snap["integrations"]) > 1:
            say.append(lang.t("sec.why.moreIntegration",
                              n=len(snap["integrations"]) - 1))
        return {"lines": [_line("secretary", "\n".join(say))]}

    # ④ 문제 없음
    return {"lines": [_line("secretary", lang.t("sec.why.none"))]}


def _p95_secs(snap: dict, agent: str) -> int | None:
    from app import metrics
    slug = (snap.get("run") or {}).get("slug")
    if not slug:
        return None
    row = metrics.of(slug)["by_agent"].get(agent)
    return int(row["p95_ms"] // 1000) if row and row.get("calls") else None


def _whois(snap, *, who, **_):
    e = next((x for x in snap["employees"] if x["id"] == who), None)
    if e is None:
        return _help(snap)
    lines = [lang.t("sec.whois.state",
                    state=lang.t(f"office.state.{e['state']}"), reason=e["reason"])]
    p = e["progress"]
    if p["total"]:
        lines.append(lang.t("sec.whois.tasks", done=p["done"], total=p["total"]))
    if e["calls"]:
        lines.append(lang.t("sec.whois.usage", n=e["calls"],
                            cost=f"{e['cost']:.4f}",
                            avg=f"{(e['avg_ms'] or 0) / 1000:.1f}"))
    if e["mock"]:
        lines.append(lang.t("sec.whois.mock"))
    return {"lines": [_line(e["id"], "\n".join(lines))]}


# 회의에서 말하는 순서 — 일이 흐르는 순서다(기획 → 검증 → 구현).
MEETING_ORDER = ("strategist", "analyst", "developer", "writer", "designer")


def _meeting(snap, **_):
    """팀장 전원이 회의실에 모여 **한 명씩 한 줄**만 말한다(사규 §3 회의 규칙)."""
    rows = {e["id"]: e for e in snap["employees"]}
    lines = []
    for eid in MEETING_ORDER:
        e = rows.get(eid)
        if not e or not e["hired"]:
            continue
        lines.append(_line(eid, e["reason"]))
    lines.append(_line("secretary", lang.t("sec.meeting.close")))
    return {"lines": lines, "action": {"meeting": [
        eid for eid in MEETING_ORDER if rows.get(eid, {}).get("hired")]}}


def _brief(snap, *, clock, **_):
    run = snap["run"]
    if run is None:
        return {"lines": [_line("secretary", lang.t("sec.noRun", time=clock))]}
    lines = [lang.t("sec.brief.head", time=clock, name=run["name"],
                    status=lang.t(f"sec.runStatus.{run['status']}"))]
    lines.append(lang.t("sec.brief.tasks", done=run["tasks_done"],
                        total=run["tasks_total"], score=run.get("score") or 0))
    lines.append(lang.t("sec.brief.cost", cost=f"{run['cost']:.4f}",
                        mins=f"{((snap.get('metrics') or {}).get('wall_ms') or 0) / 60000:.1f}"))
    if run.get("confidence") not in (None, "—"):
        lines.append(lang.t("sec.brief.confidence", pct=run["confidence"]))
    if run["pending"]:
        lines.append(lang.t("sec.brief.pending", n=run["pending"]))
    if snap["integrations"]:
        lines.append(lang.t("sec.brief.integration", what="; ".join(
            i["why"] for i in snap["integrations"])))
    if run["mock"]:
        lines.append(lang.t("sec.brief.mock"))
    if run["status"] == "stopped" and run.get("stopped_reason"):
        lines.append(lang.t("sec.brief.stopped", why=run["stopped_reason"]))
    nxt = _next_step(snap)
    if run["status"] == "done":
        lines.append(lang.t("sec.brief.done"))
    elif nxt:
        lines.append(lang.t("sec.status.next", step=_step_label(nxt)))
    return {"lines": [_line("secretary", "\n".join(lines))]}


def _focus(snap, **_):
    return {"lines": [_line("secretary", lang.t("sec.focus.on"))],
            "action": {"focus": True}}


def _unfocus(snap, **_):
    return {"lines": [_line("secretary", lang.t("sec.focus.off"))],
            "action": {"focus": False}}


def _approve(snap, *, owner, slug, **_):
    """결재가 **한 건일 때만** 바로 처리한다. 여러 건이면 무엇을 승인했는지
    대표가 모르는 채로 전부 넘어가게 된다 — 고르게 한다."""
    pending = [a for a in snap["approvals"]]
    if not pending or not slug:
        return {"lines": [_line("secretary", lang.t("sec.approve.none"))]}
    if len(pending) > 1:
        listing = "\n".join(f"{i + 1}) {a.get('title', '')}"
                            for i, a in enumerate(pending))
        return {"lines": [_line("secretary",
                                lang.t("sec.approve.many", n=len(pending))
                                + "\n" + listing)],
                "action": {"choose": [a["id"] for a in pending]}}
    from app.orchestrator import engine
    a = pending[0]
    out = engine.decide(slug, a["id"], "approve", owner=owner, by="command")
    text = lang.t("sec.approve.done", title=a.get("title", ""))
    if out.get("note"):
        text += "\n" + lang.t("sec.approve.note", note=out["note"])
    return {"lines": [_line("secretary", text)],
            "action": {"decided": a["id"]}}


def _help(snap, **_):
    return {"lines": [_line("secretary", lang.t("sec.help"))]}

