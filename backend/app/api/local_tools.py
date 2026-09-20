"""로컬 도구 전용 라우트 (DAY 17).

## 이 파일은 AI COMPANY 가 아니다

여기 있는 것들은 이 저장소에 **원래 있던 다른 제품**의 것이다 —
사용자의 컴퓨터에서 사용자의 폴더를 다루는 대화형 개발도구:

  작업 폴더 열기 · 파일 직접 편집 · git diff · 대화형 에이전트 루프 ·
  권한 승인 게이트 · 화면 캡처 · 협업 타임라인 · 예약 실행

지우지 않은 이유는 **DEPLOY_MODE=local 에서는 여전히 쓸모가 있어서**다.
내 컴퓨터에서 내 폴더를 다루는 도구로는 멀쩡히 동작한다.

한 파일로 모은 이유는 그 반대다 — main.py 에 섞여 있으니 다음 사람이
"직원이 5명인가 8명인가", "이 API 는 제품의 것인가 잔재인가"로 헷갈렸다.
경계가 파일 이름으로 보이면 그 질문이 사라진다.

## 전부 `_require_local_tools()` 를 지난다

`DEPLOY_MODE=saas` 에서는 403 이다. 라우트를 아예 안 붙이는 방법도 있지만
그러지 않았다: 모드는 요청 시점에 바뀔 수 있고(환경변수·테스트), 마운트
시점에 정해두면 그 변화가 반영되지 않는다. 관문은 **요청마다** 도는 편이
믿을 만하다.

자세한 것은 docs/security.md §0.
"""
from __future__ import annotations

import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import approvals
from app import attachments
from app import bus
from app import deploy
from app import scheduler
from app import screen
from app import secrets_broker
from app import timeline
from app import usage
from app import workspace
from app.agents import core as agent_core

router = APIRouter(tags=["local-tools"])


class OpenReq(BaseModel):
    path: str


class ModeReq(BaseModel):
    mode: str


class EditReq(BaseModel):
    path: str
    content: str


class SendReq(BaseModel):
    message: str
    attachments: list[str] = []


class DecisionReq(BaseModel):
    decision: str


class ScheduleReq(BaseModel):
    requirement: str
    at: str
    days: list[int] = []
    enabled: bool = True


class SchedulePatch(BaseModel):
    requirement: str | None = None
    at: str | None = None
    days: list[int] | None = None
    enabled: bool | None = None


def _require_local_tools() -> None:
    """로컬 환경을 건드리는 기능의 공통 관문 (§18 · app/deploy.py).

    이 검사를 라우트마다 손으로 넣지 않고 한 함수로 모은 이유: 라우트가
    늘어날 때 하나를 빠뜨리면, 그 하나가 통째로 구멍이 된다.
    """
    if (reason := deploy.allow_local_tools()) is not None:
        raise HTTPException(403, reason)


# ── 작업 폴더 ───────────────────────────────────────────────────────
@router.post("/api/workspace")
def open_workspace(req: OpenReq):
    _require_local_tools()
    try:
        root = workspace.use(req.path)
    except (workspace.Denied, OSError) as e:
        raise HTTPException(400, str(e))
    bus.bind("main")
    usage.bind("main")
    g = workspace.git_status()
    bus.say("SYSTEM", f"작업 폴더를 열었습니다 — `{root}`", kind="verdict")
    if not g.get("repo"):
        bus.say("SYSTEM", g.get("warning", ""), kind="error")
    bus.state(workspace=workspace.summary())
    return workspace.summary()


@router.get("/api/files")
def files(path: str = ".", depth: int = 2):
    _require_local_tools()
    if workspace.current() is None:
        raise HTTPException(400, "작업 폴더를 먼저 여세요")
    try:
        return {"files": workspace.listdir(path, depth=depth)}
    except workspace.Denied as e:
        raise HTTPException(400, str(e))


@router.get("/api/file")
def read_file(path: str):
    _require_local_tools()
    try:
        p = workspace.resolve(path)
    except (workspace.Denied, RuntimeError) as e:
        raise HTTPException(400, str(e))
    if not p.is_file():
        raise HTTPException(404, "없는 파일")
    if workspace.is_secret(p.name):
        raise HTTPException(403, "비밀이 담긴 파일로 보여 열지 않습니다")
    return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace")}


@router.post("/api/file")
def write_file(req: EditReq):
    """사람이 직접 고친다. 에이전트가 작업 중이면 막는다."""
    _require_local_tools()
    if agent_core.busy():
        raise HTTPException(409, "에이전트가 작업 중입니다. 끝난 뒤에 편집하세요.")
    try:
        p = workspace.resolve(req.path)
    except (workspace.Denied, RuntimeError) as e:
        raise HTTPException(400, str(e))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content, encoding="utf-8")
    bus.state(changed=workspace.git_status().get("changed", []))
    return {"ok": True, "path": req.path}


@router.get("/api/diff")
def diff(path: str | None = None):
    _require_local_tools()
    if workspace.current() is None:
        raise HTTPException(400, "작업 폴더를 먼저 여세요")
    return {"diff": workspace.git_diff(path)}


# ── 대화 ────────────────────────────────────────────────────────────
@router.post("/api/send")
def send(req: SendReq):
    # 이전 제품의 대화형 루프. 사용자의 로컬 폴더를 직접 고치므로
    # SaaS 에서는 열어두면 안 된다.
    _require_local_tools()
    if not secrets_broker.ready():
        raise HTTPException(400, "API 키가 등록되지 않았습니다. 설정에서 먼저 등록하세요.")
    try:
        agent_core.send(req.message.strip(), req.attachments)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@router.post("/api/reset")
def reset_chat():
    if agent_core.busy():
        raise HTTPException(409, "에이전트가 작업 중입니다.")
    agent_core.reset()
    return {"ok": True}


# ── 권한 모드 ───────────────────────────────────────────────────────
@router.get("/api/permission")
def get_permission():
    return approvals.mode_info()


@router.post("/api/permission")
def set_permission(req: ModeReq):
    try:
        approvals.set_mode(req.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return approvals.mode_info()


@router.get("/api/approvals")
def list_approvals():
    return {"pending": approvals.pending(), **approvals.mode_info()}


@router.post("/api/approvals/deny-all")
def deny_all_approvals():
    return {"denied": approvals.deny_all("사용자 비상 정지")}


@router.post("/api/approvals/{aid}")
def decide_approval(aid: str, req: DecisionReq):
    if req.decision not in ("approve", "deny"):
        raise HTTPException(400, "decision은 approve 또는 deny")
    if not approvals.decide(aid, req.decision):
        raise HTTPException(404, "이미 처리됐거나 없는 요청")
    return {"ok": True}



# ── 화면 ────────────────────────────────────────────────────────────
@router.get("/api/screen/status")
def screen_status():
    _require_local_tools()
    st = screen.status()
    st.update(approvals.mode_info())
    st["pending"] = approvals.pending()
    return st


@router.post("/api/screen/capture")
def screen_capture():
    """사용자가 누를 때만 한 장 찍는다. 주기적 자동 캡처는 만들지 않았다.

    SaaS 에서는 아예 막힌다 — 서버 화면은 사용자의 것이 아니다.
    """
    _require_local_tools()
    try:
        png = screen.capture()
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    meta = attachments.save(screen.capture_name(), png, source="screen")
    meta["data_url"] = attachments.data_url(meta["id"])
    return meta


# ── 타임라인 · 예약 ─────────────────────────────────────────────────
@router.get("/api/timeline")
def get_timeline():
    tl = timeline.build("main")
    tl["summary"] = timeline.summary("main")
    return tl


@router.get("/api/schedules")
def list_schedules():
    from datetime import datetime
    now = datetime.now()
    return {"schedules": [{**i, "when": scheduler.next_due(i, now)}
                          for i in scheduler.listing()]}


@router.post("/api/schedules")
def add_schedule(req: ScheduleReq):
    try:
        return scheduler.add(req.requirement, req.at, req.days, req.enabled)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/api/schedules/{sid}")
def patch_schedule(sid: str, req: SchedulePatch):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        it = scheduler.update(sid, **fields)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not it:
        raise HTTPException(404, "없는 예약")
    return it


@router.delete("/api/schedules/{sid}")
def delete_schedule(sid: str):
    if not scheduler.remove(sid):
        raise HTTPException(404, "없는 예약")
    return {"ok": True}




# ── 예약 실행 ───────────────────────────────────────────────────────
def _scheduled_send(requirement: str) -> str:
    """예약이 착수할 때. 키와 작업 폴더가 준비돼 있어야 한다."""
    if not secrets_broker.ready():
        raise RuntimeError("API 키가 없어 예약을 실행하지 않았습니다")
    if workspace.current() is None:
        raise RuntimeError("작업 폴더가 열려 있지 않아 예약을 실행하지 않았습니다")
    agent_core.send(requirement)
    return "main"


scheduler.configure(_scheduled_send)
scheduler.start()




scheduler.configure(_scheduled_send)
scheduler.start()
