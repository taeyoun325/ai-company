"""사람이 끼어드는 지점 — 승인 게이트 (DAY 25 · HITL).

## 왜 필요한가

AUTO 는 끝까지 자동이었고, 멈추게 하는 방법은 정지 버튼뿐이었다. 정지는
"그만"이지 "여기서 내가 보고 넘기겠다"가 아니다. 결제 코드나 프로덕션
설정을 만지는 일에서는 **계획을 보고 나서** 돈을 쓰고 싶고, 코드가
**받아들여지기 전에** 한 번 보고 싶다.

## 게이트 세 가지

## 대표의 선택지 네 가지 (DAY 25 · 사무실 개편)

| 선택 | 결정 | 무엇이 일어나나 |
|---|---|---|
| 승인 | `approve` | 다음으로 넘어간다 |
| 수정 요청 | `reject` | 의견을 반려 사유로 담당자에게 돌려준다 — 의견 없이는 못 한다 |
| 보류 | `hold` | **아무것도 안 한다.** 결정은 여전히 열려 있고 실행은 계속 쉰다. 비서실이 "보류한 결재"로 따로 센다 |
| 폐기 | `discard` | 계획이면 실행을 멈춘다. 태스크면 그 태스크가 건드린 파일을 되돌리고 계획에서 뺀 뒤 나머지를 계속한다 |

`stop` 은 DAY 25 초판의 이름이다 — 산출물을 되돌리지 않고 멈춘다. API 는
계속 받는다.

| 게이트 | 언제 멈추나 | 반려하면 |
|---|---|---|
| `plan` | 계획이 서고 나서, 테스트를 쓰기 **전** | 전략가가 CEO 의견으로 계획을 고친다 |
| `task` · `task:<직원>` | 검증자가 통과시킨 태스크를 완료로 치기 **전** | 담당자가 CEO 의견을 반려 사유로 받아 다시 한다 |
| `confidence` | 통과했지만 검증자 확신도가 `CONFIDENCE_GATE` 미만일 때만 | 위와 같다 |

`confidence` 가 따로 있는 이유: 모든 태스크를 보고 싶지는 않지만,
**검증자가 스스로 자신 없다고 한 통과**는 보고 싶다. 확신도(§18)를
화면에 띄우는 것만으로는 사람이 그 순간에 보고 있어야 한다 — 게이트는
사람이 볼 때까지 기다린다.

## 기다리는 동안 무엇이 도나

승인을 기다리는 태스크는 "끝나지 않은" 태스크다. 그것에 기대는 태스크는
기다리고, **기대지 않는 태스크는 계속 돈다.** 더 돌릴 것이 없으면 실행은
`awaiting` 으로 쉰다 — 스레드를 놓고, 좌석도 놓는다(`index.running_count`
는 `running` 만 센다). 결정이 들어오면 체크포인트에서 이어간다.

사람을 기다리며 스레드를 붙잡지 않는 이유: 사람은 몇 시간 뒤에 온다.
그동안 서버가 재시작되면 붙잡고 있던 스레드는 사라지고, 좌석을 산 만큼
다른 실행을 못 돌린다.

## 기록은 프로젝트 메타에 산다

`approvals` 목록. 결정은 어느 인스턴스에서 들어오든 파일에 남고, 실행은
파일을 본다. 기록을 지우지 않는다 — 누가 언제 무엇을 승인했는지는
나중에 "왜 이게 나갔나"를 물을 때의 답이다.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid

from app import bus, lang
from app.database import store

GATES = ("plan", "task", "confidence")
DECISIONS = ("approve", "reject", "hold", "discard", "stop")
_STATUS = {"approve": "approved", "reject": "rejected", "stop": "stopped",
           "discard": "discarded"}

# 확신도가 이보다 낮은 통과는 `confidence` 게이트가 멈춰 세운다.
CONFIDENCE_GATE = float(os.getenv("CONFIDENCE_GATE", "0.6"))


class GateError(ValueError):
    """모르는 게이트 · 잘못된 결정."""


class AlreadyDecided(GateError):
    """이미 결정된 승인 — 두 사람이 같은 버튼을 눌렀거나 두 번 눌렀다."""


class ApprovalNotFound(GateError):
    """없는 승인."""


def normalize(gates) -> list[str]:
    """화면·API 가 보낸 게이트 목록을 검사한다.

    `task:<직원 id>` 는 그 직원이 맡은 태스크만 멈춘다 — "개발자 코드만 내가
    보겠다". 맡을 수 없는 직원(전략가·검증자)을 적으면 거부한다: 그런
    게이트는 영영 안 걸리고, 사용자는 걸어뒀다고 믿는다.
    """
    from app.agents import roles
    out: list[str] = []
    for g in gates or []:
        g = str(g).strip()
        if not g:
            continue
        head, _, who = g.partition(":")
        if head not in GATES or (who and head != "task"):
            raise GateError(lang.t("gate.unknown", gate=g,
                                   allowed=", ".join(GATES)))
        if who:
            e = roles.EMPLOYEES.get(who)
            if e is None or e.kind not in ("build", "write", "design"):
                raise GateError(lang.t("gate.badEmployee", who=who))
        if g not in out:
            out.append(g)
    return out


def of(slug: str) -> list[str]:
    return list(store.meta(slug).get("gates") or [])


def set_gates(slug: str, gates) -> list[str]:
    clean = normalize(gates)
    store.save_meta(slug, {"gates": clean})
    return clean


def task_reason(gates: list[str], assignee: str, confidence: float) -> str | None:
    """이 통과를 사람이 봐야 하나. 봐야 하면 이유(`task` · `confidence`)."""
    if "task" in gates or f"task:{assignee}" in gates:
        return "task"
    if "confidence" in gates and confidence < CONFIDENCE_GATE:
        return "confidence"
    return None


def plan_hash(plan) -> str:
    raw = plan.model_dump_json() if hasattr(plan, "model_dump_json") else str(plan)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── 기록 ────────────────────────────────────────────────────────────
def _all(m: dict) -> list[dict]:
    return list(m.get("approvals") or [])


def all_of(slug: str) -> list[dict]:
    return _all(store.meta(slug))


def pending(slug: str) -> list[dict]:
    return [a for a in all_of(slug) if a.get("status") == "pending"]


def open_gate(slug: str, gate: str, *, title: str, detail: dict,
              **keys) -> dict:
    """승인 한 건을 연다. 같은 대상에 이미 열려 있으면 그것을 돌려준다.

    같은 대상을 두 번 열지 않는 이유: 재개하면 같은 지점을 다시 지난다.
    그때마다 새 기록이 생기면 화면에 같은 승인 요청이 줄줄이 쌓인다.
    """
    rec_box: dict = {}

    def fn(m: dict):
        rows = _all(m)
        for a in rows:
            if (a.get("status") == "pending" and a.get("gate") == gate
                    and all(a.get(k) == v for k, v in keys.items())):
                rec_box["rec"] = a
                return None
        rec = {"id": uuid.uuid4().hex[:12], "gate": gate, "title": title,
               "status": "pending", "created_at": time.time(),
               "detail": detail, "applied": False, **keys}
        rows.append(rec)
        rec_box["rec"] = rec
        rec_box["new"] = True
        return {"approvals": rows}

    store.update_meta(slug, fn)
    rec = rec_box["rec"]
    if rec_box.get("new"):
        bus.emit("gate", stage="open", approval=rec)
        bus.say("SYSTEM", lang.t("log.gateOpen", title=title,
                                 gate=lang.t(f"gate.name.{gate}")),
                kind="verdict")
    return rec


def decide(slug: str, approval_id: str, decision: str, comment: str = "",
           by: str = "") -> dict:
    """CEO 의 결정을 기록한다. 실행에 알리는 것은 호출부(engine)의 몫이다."""
    return decide_seen(slug, approval_id, decision, comment, by=by)[0]


def decide_seen(slug: str, approval_id: str, decision: str, comment: str = "",
                by: str = "") -> tuple[dict, str | None]:
    """결정을 기록하고, **기록하는 순간의** 실행 상태를 함께 돌려준다 (DAY 26).

    "결정을 쓰고 → 상태를 다시 읽는" 두 걸음이면 그 사이에 다른 인스턴스의
    실행이 쉬러 들어갈 수 있다(`engine._park`). 그러면 이쪽은 "돌고 있다"를
    보고 깨우지 않고, 저쪽은 결정이 오기 전에 쉬었으므로 아무도 안 깨운다.
    같은 메타 잠금(프로세스를 넘는다) 안에서 쓰고 읽으면 둘 중 하나는
    반드시 상대를 본다.
    """
    if decision not in DECISIONS:
        raise GateError(lang.t("gate.badDecision",
                               allowed=", ".join(DECISIONS)))
    comment = (comment or "").strip()[:4000]
    if decision == "reject" and not comment:
        # 반려 사유 없는 반려는 담당자에게 "다시 해"만 전한다. 무엇을
        # 고칠지 모르는 재작업은 같은 결과를 한 번 더 산다.
        raise GateError(lang.t("gate.needComment"))
    box: dict = {}

    def fn(m: dict):
        rows = _all(m)
        for a in rows:
            if a.get("id") != approval_id:
                continue
            if a.get("status") != "pending":
                box["err"] = lang.t("gate.alreadyDecided",
                                    status=a.get("status"))
                box["taken"] = True
                return None
            box["status"] = m.get("status")
            if decision == "hold":
                # 보류는 결정이 아니다 — 열린 채로 두고 표시만 한다.
                a.update(held=True, held_at=time.time(), comment=comment,
                         held_by=by)
            else:
                a.update(status=_STATUS[decision], comment=comment,
                         decided_at=time.time(), decided_by=by, held=False)
            box["rec"] = a
            return {"approvals": rows}
        box["err"] = lang.t("gate.notFound")
        return None

    store.update_meta(slug, fn)
    if "err" in box:
        raise (AlreadyDecided if box.get("taken") else ApprovalNotFound)(box["err"])
    rec = box["rec"]
    # 결정은 **실행이 쉬는 중에도** 로그에 남아야 한다. 이 스레드에는
    # 실행이 묶여 있지 않으므로 잠깐 묶었다 푼다.
    prev = bus.current()
    bus.bind(slug)
    try:
        held = decision == "hold"
        bus.emit("gate", stage="held" if held else "closed", approval=rec)
        key = "log.gate.held" if held else "log.gate." + rec["status"]
        bus.say("USER", lang.t(key, title=rec["title"])
                + (f" — {comment}" if comment else ""), kind="verdict")
    finally:
        if prev is None:
            bus.release()
        else:
            bus.bind(prev)
    return rec, box.get("status")


def unapplied(m: dict, gate: str | None = None) -> bool:
    """이 메타에 실행이 아직 반영하지 않은 결정이 있나. 잠금 안에서 부른다."""
    return any(a.get("status") != "pending" and not a.get("applied")
               and (gate is None or a.get("gate") == gate)
               for a in _all(m))


def has_unapplied_decisions(slug: str, gate: str | None = None) -> bool:
    return unapplied(store.meta(slug), gate)


def take_decided(slug: str, gate: str) -> list[dict]:
    """결정됐지만 실행이 아직 반영하지 않은 것을 꺼내고 반영됨으로 표시한다."""
    box: list[dict] = []

    def fn(m: dict):
        rows = _all(m)
        changed = False
        for a in rows:
            if (a.get("gate") == gate and a.get("status") != "pending"
                    and not a.get("applied")):
                a["applied"] = True
                box.append(dict(a))
                changed = True
        return {"approvals": rows} if changed else None

    store.update_meta(slug, fn)
    return box


def find_plan(slug: str, h: str) -> dict | None:
    """이 계획(해시)에 대한 가장 최근 결정. 반영된 반려는 없던 것으로 친다 —
    전략가가 고친 계획이 우연히 같은 해시면 같은 반려로 무한히 돈다."""
    for a in reversed(all_of(slug)):
        if a.get("gate") != "plan" or a.get("plan_hash") != h:
            continue
        if a.get("status") == "rejected" and a.get("applied"):
            continue
        return a
    return None


def mark_applied(slug: str, approval_id: str) -> None:
    def fn(m: dict):
        rows = _all(m)
        for a in rows:
            if a.get("id") == approval_id and not a.get("applied"):
                a["applied"] = True
                return {"approvals": rows}
        return None
    store.update_meta(slug, fn)


def close_all(slug: str, status: str = "stopped", comment: str = "") -> int:
    """실행을 멈추면 열려 있던 승인을 닫는다 — 멈춘 실행의 승인 버튼이
    화면에 남으면 눌러도 아무 일이 없다."""
    box = {"n": 0}

    def fn(m: dict):
        rows = _all(m)
        for a in rows:
            if a.get("status") == "pending":
                a.update(status=status, comment=comment,
                         decided_at=time.time(), applied=True)
                box["n"] += 1
        return {"approvals": rows} if box["n"] else None

    store.update_meta(slug, fn)
    return box["n"]
