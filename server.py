"""로컬 웹 서버.

Claude Code의 틀: 작업 폴더를 열고, 대화하듯 에이전트에게 시킨다.
진행 상황은 SSE로 흘러나간다.

  python server.py                실제 모델 (설정에서 키 등록)
  python server.py --dir <경로>    시작할 때 폴더 열기
"""
import json
import queue
import sys

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import agent_core
import approvals
import attachments
import bus
import config
import gemini
import scheduler
import screen
import secrets_broker
import subagents
import timeline
import usage
import workspace

secrets_broker.init()   # 기동 즉시 환경변수에서 키를 꺼내 지운다

app = FastAPI(title="AI Agent Company")


# ── 요청 모델 ───────────────────────────────────────────────────────
class SendReq(BaseModel):
    message: str
    attachments: list[str] = []


class OpenReq(BaseModel):
    path: str


class ModeReq(BaseModel):
    mode: str


class KeysReq(BaseModel):
    anthropic: str | None = None
    gemini: str | None = None
    remember: bool = False


class ModelReq(BaseModel):
    qa_model: str


class DecisionReq(BaseModel):
    decision: str


class EditReq(BaseModel):
    path: str
    content: str


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


@app.get("/")
def index():
    return FileResponse(config.ROOT / "web" / "index.html")


# ── 상태 ────────────────────────────────────────────────────────────
@app.get("/api/state")
def state():
    return {
        "workspace": workspace.summary(),
        "permission": approvals.mode_info(),
        "agents": subagents.roster(),
        "models": config.MODEL_OF,
        "keys_ready": secrets_broker.ready(),
        "busy": agent_core.busy(),
        "turns": len(agent_core.history),
        "screen": screen.status(),
    }


# ── 작업 폴더 ───────────────────────────────────────────────────────
@app.post("/api/workspace")
def open_workspace(req: OpenReq):
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


@app.get("/api/files")
def files(path: str = ".", depth: int = 2):
    if workspace.current() is None:
        raise HTTPException(400, "작업 폴더를 먼저 여세요")
    try:
        return {"files": workspace.listdir(path, depth=depth)}
    except workspace.Denied as e:
        raise HTTPException(400, str(e))


@app.get("/api/file")
def read_file(path: str):
    try:
        p = workspace.resolve(path)
    except (workspace.Denied, RuntimeError) as e:
        raise HTTPException(400, str(e))
    if not p.is_file():
        raise HTTPException(404, "없는 파일")
    if workspace.is_secret(p.name):
        raise HTTPException(403, "비밀이 담긴 파일로 보여 열지 않습니다")
    return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace")}


@app.post("/api/file")
def write_file(req: EditReq):
    """사람이 직접 고친다. 에이전트가 작업 중이면 막는다."""
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


@app.get("/api/diff")
def diff(path: str | None = None):
    if workspace.current() is None:
        raise HTTPException(400, "작업 폴더를 먼저 여세요")
    return {"diff": workspace.git_diff(path)}


# ── 대화 ────────────────────────────────────────────────────────────
@app.post("/api/send")
def send(req: SendReq):
    if not secrets_broker.ready():
        raise HTTPException(400, "API 키가 등록되지 않았습니다. 설정에서 먼저 등록하세요.")
    try:
        agent_core.send(req.message.strip(), req.attachments)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/reset")
def reset_chat():
    if agent_core.busy():
        raise HTTPException(409, "에이전트가 작업 중입니다.")
    agent_core.reset()
    return {"ok": True}


# ── 권한 모드 ───────────────────────────────────────────────────────
@app.get("/api/permission")
def get_permission():
    return approvals.mode_info()


@app.post("/api/permission")
def set_permission(req: ModeReq):
    try:
        approvals.set_mode(req.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return approvals.mode_info()


@app.get("/api/approvals")
def list_approvals():
    return {"pending": approvals.pending(), **approvals.mode_info()}


@app.post("/api/approvals/deny-all")
def deny_all_approvals():
    return {"denied": approvals.deny_all("사용자 비상 정지")}


@app.post("/api/approvals/{aid}")
def decide_approval(aid: str, req: DecisionReq):
    if req.decision not in ("approve", "deny"):
        raise HTTPException(400, "decision은 approve 또는 deny")
    if not approvals.decide(aid, req.decision):
        raise HTTPException(404, "이미 처리됐거나 없는 요청")
    return {"ok": True}


# ── 설정: API 키와 모델 ─────────────────────────────────────────────
@app.get("/api/settings")
def get_settings():
    return {"keys": secrets_broker.status(), "models": config.MODEL_OF,
            "stored": secrets_broker.STORE_PATH.exists(),
            "ready": secrets_broker.ready()}


@app.post("/api/settings/keys")
def set_keys(req: KeysReq):
    changed = []
    for name in ("anthropic", "gemini"):
        val = getattr(req, name)
        if val is None:
            continue
        secrets_broker.set_key(name, val)
        changed.append(name)
    if req.remember:
        secrets_broker.persist()
    if "anthropic" in changed:
        try:
            from agents import llm
            llm.reset_client()
        except ImportError:
            pass
    if "gemini" in changed:
        gemini.reset_client()
    return {"ok": True, "keys": secrets_broker.status(),
            "ready": secrets_broker.ready(),
            "stored": secrets_broker.STORE_PATH.exists()}


@app.post("/api/settings/forget")
def forget_keys():
    secrets_broker.forget_stored()
    return {"ok": True, "stored": False}


@app.post("/api/settings/verify/{provider}")
def verify_key(provider: str):
    try:
        if provider == "anthropic":
            from agents import llm
            models = [m.id for m in llm.client().models.list()]
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:40]}
        if provider == "gemini":
            models = gemini.list_models()
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:60]}
        raise HTTPException(400, "알 수 없는 제공자")
    except HTTPException:
        raise
    except ImportError as e:
        pkg = "anthropic" if provider == "anthropic" else "google-genai"
        return {"ok": False,
                "detail": f"{pkg} 패키지가 설치되지 않았습니다. "
                          f"pip install -r requirements.txt 를 실행하세요. ({e})"}
    except Exception as e:
        return {"ok": False, "detail": secrets_broker.scrub(f"{type(e).__name__}: {e}")}


@app.post("/api/settings/qa-model")
def set_qa_model(req: ModelReq):
    config.QA_MODEL = req.qa_model
    config.MODEL_OF["QA"] = req.qa_model
    config.PRICES.setdefault(req.qa_model, config.PRICES.get("gemini-2.5-pro", (0.0, 0.0)))
    return {"ok": True, "models": config.MODEL_OF}


# ── 첨부 자료 ───────────────────────────────────────────────────────
@app.get("/api/attachments")
def list_attachments():
    return {"attachments": attachments.listing()}


@app.post("/api/attachments")
async def upload_attachment(file: UploadFile = File(...)):
    data = await file.read()
    try:
        return attachments.save(file.filename or "upload.bin", data, source="upload")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/attachments/{aid}/preview")
def attachment_preview(aid: str):
    url = attachments.data_url(aid)
    if not url:
        raise HTTPException(404, "미리볼 수 없는 첨부")
    return {"id": aid, "data_url": url}


@app.delete("/api/attachments/{aid}")
def delete_attachment(aid: str):
    if not attachments.delete(aid):
        raise HTTPException(404, "없는 첨부")
    return {"ok": True}


# ── 화면 ────────────────────────────────────────────────────────────
@app.get("/api/screen/status")
def screen_status():
    st = screen.status()
    st.update(approvals.mode_info())
    st["pending"] = approvals.pending()
    return st


@app.post("/api/screen/capture")
def screen_capture():
    """사용자가 누를 때만 한 장 찍는다. 주기적 자동 캡처는 만들지 않았다."""
    try:
        png = screen.capture()
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    meta = attachments.save(screen.capture_name(), png, source="screen")
    meta["data_url"] = attachments.data_url(meta["id"])
    return meta


# ── 타임라인 · 예약 ─────────────────────────────────────────────────
@app.get("/api/timeline")
def get_timeline():
    tl = timeline.build("main")
    tl["summary"] = timeline.summary("main")
    return tl


@app.get("/api/schedules")
def list_schedules():
    from datetime import datetime
    now = datetime.now()
    return {"schedules": [{**i, "when": scheduler.next_due(i, now)}
                          for i in scheduler.listing()]}


@app.post("/api/schedules")
def add_schedule(req: ScheduleReq):
    try:
        return scheduler.add(req.requirement, req.at, req.days, req.enabled)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/schedules/{sid}")
def patch_schedule(sid: str, req: SchedulePatch):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        it = scheduler.update(sid, **fields)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not it:
        raise HTTPException(404, "없는 예약")
    return it


@app.delete("/api/schedules/{sid}")
def delete_schedule(sid: str):
    if not scheduler.remove(sid):
        raise HTTPException(404, "없는 예약")
    return {"ok": True}


# ── 이벤트 스트림 ───────────────────────────────────────────────────
@app.get("/api/stream")
def stream():
    def gen():
        q = bus.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


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


if __name__ == "__main__":
    if "--dir" in sys.argv:
        try:
            workspace.use(sys.argv[sys.argv.index("--dir") + 1])
            bus.bind("main")
            usage.bind("main")
        except (IndexError, workspace.Denied, OSError) as e:
            print(f"  폴더를 열지 못했습니다: {e}")
    cur = workspace.current()
    print("\n  http://127.0.0.1:8000")
    print(f"  작업 폴더: {cur or '(설정에서 열기)'}\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
