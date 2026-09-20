"""권한 게이트 — 파일 변경·명령 실행·화면 조작을 사람이 통제한다.

## 권한 모드 (Claude Code와 같은 5가지)

| 모드 | 뜻 |
|---|---|
| `auto` | 에이전트가 권한 결정을 처리한다. 되돌릴 수 있는 것은 통과, 위험한 것은 물어봄 |
| `manual` | 변경하기 전에 항상 확인 |
| `accept_edits` | 모든 파일 편집 자동 승인. 명령 실행은 여전히 물어봄 |
| `plan` | 변경 금지. 계획만 만든다 |
| `bypass` | 모든 권한 허용 |

## 어떤 모드에서도 지키는 것 하나

`bypass` 에서도 **자격 증명 입력만은 막는다.** 에이전트가 네 비밀번호나 API 키를
아무 화면에나 타이핑하는 것은 되돌릴 수 없고, 되돌릴 수 없는 것에 대해서는
"모든 권한 허용"이 의미를 갖지 않는다고 봤다. 이건 내 판단이고,
`FORBIDDEN_TEXT` 를 비우면 꺼진다 — 다만 권하지 않는다.
"""
import re
import threading
import time
import uuid

from app import bus
from app import screen

TIMEOUT = 120                # 초. 사람이 응답하지 않으면 거부로 처리한다.

MODES = {
    "auto":         ("자동", "에이전트가 권한 결정을 처리합니다"),
    "manual":       ("수동", "변경하기 전에 항상 확인"),
    "accept_edits": ("편집 자동 수락", "모든 파일 편집 자동 승인"),
    "plan":         ("계획", "변경하기 전에 계획 만들기"),
    "bypass":       ("권한 무시", "모든 권한 허용"),
}
DEFAULT_MODE = "auto"
mode = DEFAULT_MODE

# 변경을 일으키는 행동의 종류
FILE_KINDS = {"write", "edit"}
EXEC_KINDS = {"bash"}
SCREEN_KINDS = {"move", "scroll", "click", "double_click", "right_click", "type", "key"}
LOW_RISK = {"move", "scroll"}          # 되돌릴 수 있는 화면 조작

# 어떤 모드에서도 실행하지 않는다. 자격 증명은 사람이 직접 입력해야 한다.
FORBIDDEN_TEXT = re.compile(
    r"(sk-ant-[\w-]{8,}|AIza[\w-]{20,}|password|passwd|비밀번호|"
    r"\b\d{3}-\d{2}-\d{4}\b|\b(?:\d[ -]?){13,19}\b)",
    re.IGNORECASE)

_pending: dict[str, dict] = {}
_events: dict[str, threading.Event] = {}
_lock = threading.Lock()


class Denied(RuntimeError):
    """거부됐거나 금지된 행동."""


class PlanMode(Denied):
    """계획 모드에서 변경을 시도했다."""


def set_mode(name: str) -> str:
    global mode
    if name not in MODES:
        raise ValueError(f"알 수 없는 모드: {name}")
    mode = name
    label, desc = MODES[name]
    bus.say("SYSTEM", f"권한 모드 → **{label}** ({desc})", kind="verdict")
    bus.state(permission_mode=name)
    return mode


def mode_info() -> dict:
    return {"mode": mode,
            "modes": [{"id": k, "label": v[0], "desc": v[1]} for k, v in MODES.items()]}


def _forbidden_reason(action: str, params: dict) -> str | None:
    """모드와 무관하게 막는 것."""
    if action == "type":
        text = params.get("text", "")
        if FORBIDDEN_TEXT.search(text):
            return ("자격 증명이나 민감한 번호로 보이는 값은 에이전트가 입력하지 않습니다. "
                    "직접 입력하세요.")
        if len(text) > 2000:
            return "한 번에 2000자를 넘게 입력하지 않습니다."
    if action == "key":
        keys = params.get("keys") or []
        if isinstance(keys, str):
            keys = [keys]
        low = {str(k).lower() for k in keys}
        if low & {"win", "meta", "cmd"} and low & {"r", "l", "e"}:
            return "시스템 단축키는 실행하지 않습니다."
    return None


def gate(action: str) -> str:
    """현재 모드에서 이 행동을 어떻게 처리할지: allow | ask | block"""
    if mode == "bypass":
        return "allow"
    if mode == "plan":
        return "block" if action in (FILE_KINDS | EXEC_KINDS | SCREEN_KINDS) else "allow"
    if mode == "manual":
        return "ask"
    if mode == "accept_edits":
        return "allow" if action in FILE_KINDS else "ask"
    # auto — 되돌릴 수 있는 것만 통과시키고 나머지는 묻는다
    return "allow" if action in LOW_RISK else "ask"


def describe(action: str, params: dict) -> str:
    if action in ("write", "edit"):
        return f"{'생성/덮어쓰기' if action == 'write' else '부분 수정'}: {params.get('path')}"
    if action == "bash":
        return f"명령 실행: {params.get('command')}"
    if action == "type":
        t = params.get("text", "")
        return f'입력: "{t if len(t) <= 60 else t[:60] + "…"}"'
    if action == "key":
        keys = params.get("keys")
        return f"키: {'+'.join(keys) if isinstance(keys, list) else keys}"
    if action in ("click", "double_click", "right_click", "move"):
        return f"{action} @ ({params.get('x')}, {params.get('y')})"
    if action == "scroll":
        return f"스크롤 {params.get('amount', -3)}"
    return f"{action} {params}"


def request(action: str, params: dict, why: str = "") -> str:
    """행동 하나를 게이트에 통과시킨다. 막히면 Denied.

    파일 쓰기·명령 실행은 호출한 쪽이 직접 실행한다(여기서는 승인만).
    화면 조작만 여기서 실행한다 — screen.perform 이 유일한 경로여야 하기 때문.
    """
    reason = _forbidden_reason(action, params)
    if reason:
        bus.say("SYSTEM", f"**금지된 행동 차단** — {describe(action, params)}\n{reason}",
                kind="error")
        raise Denied(reason)

    decision = gate(action)

    if decision == "block":
        msg = ("계획 모드입니다. 지금은 변경할 수 없습니다. "
               "무엇을 어떻게 바꿀지 계획으로 제시하세요.")
        bus.say("SYSTEM", f"계획 모드 — 차단됨: {describe(action, params)}", kind="verdict")
        raise PlanMode(msg)

    if decision == "allow":
        return _maybe_execute(action, params, f"{MODES[mode][0]} 모드")

    # ask
    aid = uuid.uuid4().hex[:8]
    ev = threading.Event()
    item = {"id": aid, "action": action, "params": params, "why": why,
            "desc": describe(action, params), "run": bus.current(),
            "asked_at": time.time(), "decision": None}
    with _lock:
        _pending[aid] = item
        _events[aid] = ev

    # `id` 를 쓰지 않는 이유: 버스가 이벤트마다 붙이는 일련번호가 `id` 다(§13).
    # 같은 이름으로 실으면 그 번호를 덮어써서 재연결 이어받기가 깨진다.
    bus.emit("approval", approval_id=item["id"],
             **{k: item[k] for k in ("action", "desc", "why")})

    granted = ev.wait(TIMEOUT)
    with _lock:
        result = _pending.pop(aid, {}).get("decision")
        _events.pop(aid, None)

    if not granted or result != "approve":
        note = "거부됨" if granted else f"{TIMEOUT}초 안에 응답이 없어 거부"
        bus.emit("approval_done", approval_id=aid, decision="deny")
        bus.say("SYSTEM", f"취소 — {item['desc']} ({note})", kind="error")
        raise Denied(note)

    bus.emit("approval_done", approval_id=aid, decision="approve")
    return _maybe_execute(action, params, "승인됨")


def _maybe_execute(action: str, params: dict, how: str) -> str:
    """화면 조작만 여기서 실행한다. 파일·명령은 호출한 쪽이 한다."""
    if action in SCREEN_KINDS:
        result = screen.perform(action, **params)
        bus.say("SYSTEM", f"화면 조작 — {result} ({how})", kind="tool")
        return result
    return how


def decide(aid: str, decision: str) -> bool:
    with _lock:
        item = _pending.get(aid)
        if not item:
            return False
        item["decision"] = decision
        ev = _events.get(aid)
    if ev:
        ev.set()
    return True


def pending() -> list[dict]:
    with _lock:
        return [{k: v for k, v in i.items() if k != "decision"}
                for i in _pending.values()]


def deny_all(note: str = "사용자 중단") -> int:
    """비상 정지 — 대기 중인 모든 행동을 거부한다."""
    with _lock:
        items = list(_pending.values())
        for i in items:
            i["decision"] = "deny"
        evs = list(_events.values())
    for e in evs:
        e.set()
    if items:
        bus.say("SYSTEM", f"{len(items)}개 행동을 모두 거부했습니다 ({note})", kind="error")
    return len(items)
