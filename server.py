"""로컬 웹 서버. 채팅 로그를 SSE로 실시간 스트리밍한다.

  python server.py --mock     API 키 없이 UI 확인
  python server.py            실제 모델로 실행
"""
import json
import queue
import sys

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import approvals
import attachments
import bus
import config
import orchestrator
import scheduler
import screen
import secrets_broker
import store
import timeline

secrets_broker.init()   # 기동 즉시 환경변수에서 키를 꺼내 지운다

MOCK = "--mock" in sys.argv
app = FastAPI(title="AI Agent Company")


class StartReq(BaseModel):
    requirement: str
    attachments: list[str] = []


class DecisionReq(BaseModel):
    decision: str


class ToggleReq(BaseModel):
    on: bool


class ScheduleReq(BaseModel):
    requirement: str
    at: str                       # "HH:MM"
    days: list[int] = []          # 0=월 … 6=일. 비우면 매일
    enabled: bool = True


class SchedulePatch(BaseModel):
    requirement: str | None = None
    at: str | None = None
    days: list[int] | None = None
    enabled: bool | None = None


class KeysReq(BaseModel):
    anthropic: str | None = None
    gemini: str | None = None
    remember: bool = False


class ModelReq(BaseModel):
    qa_model: str


class EditReq(BaseModel):
    path: str
    content: str


@app.get("/")
def index():
    return FileResponse(config.ROOT / "web" / "index.html")


@app.get("/api/agents")
def agents():
    return {"agents": bus.AGENTS, "mock": MOCK, "models": config.MODEL_OF,
            "prices": config.PRICES, "running": orchestrator.is_running(),
            "keys_ready": secrets_broker.ready()}


# ── 설정: API 키와 모델 ─────────────────────────────────────────────
@app.get("/api/settings")
def get_settings():
    """키 원문은 절대 내보내지 않는다. 설정 여부와 마스킹만."""
    return {
        "keys": secrets_broker.status(),
        "models": config.MODEL_OF,
        "stored": secrets_broker.STORE_PATH.exists(),
        "mock": MOCK,
        "ready": secrets_broker.ready(),
    }


@app.post("/api/settings/keys")
def set_keys(req: KeysReq):
    changed = []
    for name in ("anthropic", "gemini"):
        val = getattr(req, name)
        if val is None:
            continue                      # 안 보낸 것은 건드리지 않는다
        secrets_broker.set_key(name, val)
        changed.append(name)
    if req.remember:
        secrets_broker.persist()

    # 키가 바뀌었으니 다음 호출에 새 클라이언트를 만들게 한다.
    # SDK가 아직 설치되지 않았을 수 있다 — 설정 화면은 그 전에 쓰는 화면이다.
    _reset_clients(changed)

    return {"ok": True, "keys": secrets_broker.status(),
            "ready": secrets_broker.ready(),
            "stored": secrets_broker.STORE_PATH.exists()}


def _reset_clients(changed: list[str]) -> None:
    if "anthropic" in changed:
        try:
            from agents import llm
            llm.reset_client()
        except ImportError:
            pass          # anthropic 미설치 — 설치 후 첫 호출에 새로 만들어진다
    if "gemini" in changed:
        try:
            from agents import qa
            qa.reset_client()
        except ImportError:
            pass


@app.post("/api/settings/forget")
def forget_keys():
    """저장 파일을 지운다. 현재 세션의 메모리 키는 유지된다."""
    secrets_broker.forget_stored()
    return {"ok": True, "stored": False}


@app.post("/api/settings/verify/{provider}")
def verify_key(provider: str):
    """실제로 한 번 호출해서 키가 유효한지 본다. 가장 싼 호출로."""
    try:
        if provider == "anthropic":
            from agents import llm
            models = [m.id for m in llm.client().models.list()]
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:40]}
        if provider == "gemini":
            from agents import qa
            models = qa.list_models()
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:60]}
        raise HTTPException(400, "알 수 없는 제공자")
    except HTTPException:
        raise
    except ImportError as e:
        pkg = "anthropic" if provider == "anthropic" else "google-genai"
        return {"ok": False,
                "detail": f"{pkg} 패키지가 설치되지 않았습니다. "
                          f"pip install -r requirements.txt 를 먼저 실행하세요. ({e})"}
    except Exception as e:
        # 오류 메시지에 키가 섞여 나올 수 있다
        return {"ok": False, "detail": secrets_broker.scrub(f"{type(e).__name__}: {e}")}


@app.post("/api/settings/qa-model")
def set_qa_model(req: ModelReq):
    """Gemini 모델 ID는 시점에 따라 바뀐다. 조회한 목록에서 고른 값을 박는다."""
    config.QA_MODEL = req.qa_model
    config.MODEL_OF["QA"] = req.qa_model
    config.PRICES.setdefault(req.qa_model, config.PRICES.get("gemini-2.5-pro", (0.0, 0.0)))
    return {"ok": True, "models": config.MODEL_OF}


@app.post("/api/start")
def start(req: StartReq):
    if not MOCK and not secrets_broker.ready():
        raise HTTPException(400, "API 키가 등록되지 않았습니다. 설정에서 먼저 등록하세요.")
    try:
        slug = orchestrator.start(req.requirement.strip(), mock=MOCK,
                                  attachment_ids=req.attachments)
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    return {"ok": True, "slug": slug}


@app.get("/api/runs")
def runs():
    """지금 돌고 있는 실행 목록. UI의 작업공간 탭이 쓴다."""
    return {"running": orchestrator.running_slugs(),
            "max_concurrent": orchestrator.MAX_CONCURRENT}


# ── 저장소 ──────────────────────────────────────────────────────────
@app.get("/api/projects")
def projects():
    return {"projects": store.list_projects()}


@app.get("/api/projects/{slug}")
def project(slug: str):
    m = store.meta(slug)
    if not m:
        raise HTTPException(404, "없는 프로젝트")
    m["files"] = store.files_of(slug)
    return m


@app.get("/api/projects/{slug}/file")
def project_file(slug: str, path: str, version: int = 0):
    """version 0 = 현재 파일. 그 외는 이력."""
    try:
        return {"path": path, "version": version,
                "content": store.version_text(slug, path, version)}
    except (ValueError, OSError):
        raise HTTPException(404, "없는 파일 또는 버전")


@app.get("/api/projects/{slug}/versions")
def project_versions(slug: str, path: str):
    return {"path": path, "versions": store.versions(slug, path)}


@app.get("/api/projects/{slug}/diff")
def project_diff(slug: str, path: str, a: int, b: int = 0):
    try:
        return {"path": path, "a": a, "b": b, "rows": store.diff(slug, path, a, b)}
    except (ValueError, OSError):
        raise HTTPException(404, "비교할 수 없는 버전")


@app.post("/api/projects/{slug}/file")
def edit_file(slug: str, req: EditReq):
    """사람이 직접 고친다.

    사람은 에이전트의 신뢰 경계 위에 있으므로 src/ 와 tests/ 를 모두 쓸 수 있다.
    다만 에이전트가 도는 중에는 막는다 — 같은 파일을 동시에 쓰면 한쪽이 사라진다.
    """
    if orchestrator.is_running():
        raise HTTPException(409, "에이전트가 작업 중입니다. 끝난 뒤에 편집하세요.")
    from tools import fs as _fs
    try:
        _fs.use(slug)
        info = _fs.write(req.path, req.content, "SYSTEM")
    except _fs.Denied as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        raise HTTPException(500, f"쓰기 실패: {e}")
    return {"ok": True, **info, "files": store.files_of(slug)}


@app.get("/api/projects/{slug}/preview")
def project_preview(slug: str):
    """무엇을 보여줄 수 있는지 판단한다. 실행은 하지 않는다."""
    import runner
    d = store.dir_of(slug)
    if not d.exists():
        raise HTTPException(404, "없는 프로젝트")
    html = runner.find_html(d)
    if html:
        return {"kind": "html", "path": html, "content": store.read_file(slug, html)}
    entry = runner.find_entry(d)
    if entry:
        return {"kind": "python", "path": entry}
    return {"kind": "none", "path": None}


@app.post("/api/projects/{slug}/preview/run")
def project_preview_run(slug: str):
    """진입점을 실제로 실행한다. pytest와 동일한 격리를 쓴다."""
    import runner
    if orchestrator.is_running():
        raise HTTPException(409, "에이전트가 작업 중입니다. 끝난 뒤에 실행하세요.")
    d = store.dir_of(slug)
    entry = runner.find_entry(d)
    if not entry:
        raise HTTPException(400, "실행할 진입점을 찾지 못했습니다")
    return runner.run_entry(d, entry)


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
    st["auto_approve_low_risk"] = approvals.auto_approve_low_risk
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


# ── 승인 게이트 ─────────────────────────────────────────────────────
@app.get("/api/approvals")
def list_approvals():
    return {"pending": approvals.pending(),
            "auto_approve_low_risk": approvals.auto_approve_low_risk}


@app.post("/api/approvals/{aid}")
def decide_approval(aid: str, req: DecisionReq):
    if req.decision not in ("approve", "deny"):
        raise HTTPException(400, "decision은 approve 또는 deny")
    if not approvals.decide(aid, req.decision):
        raise HTTPException(404, "이미 처리됐거나 없는 요청")
    return {"ok": True}


@app.post("/api/approvals/deny-all")
def deny_all_approvals():
    """비상 정지."""
    return {"denied": approvals.deny_all("사용자 비상 정지")}


@app.post("/api/approvals/auto")
def set_auto_approve(req: ToggleReq):
    """저위험(이동·스크롤) 자동 승인 토글. 클릭·입력에는 적용되지 않는다."""
    return {"auto_approve_low_risk": approvals.set_auto_approve(req.on)}


# ── 협업 타임라인 (B5) ──────────────────────────────────────────────
@app.get("/api/projects/{slug}/timeline")
def project_timeline(slug: str):
    if not store.meta(slug):
        raise HTTPException(404, "없는 프로젝트")
    tl = timeline.build(slug)
    tl["summary"] = timeline.summary(slug)
    return tl


# ── 예약 실행 (B6) ──────────────────────────────────────────────────
@app.get("/api/schedules")
def list_schedules():
    from datetime import datetime
    now = datetime.now()
    items = [{**i, "when": scheduler.next_due(i, now)} for i in scheduler.listing()]
    return {"schedules": items, "mock": MOCK}


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
                    yield ": keepalive\n\n"      # 프록시 타임아웃 방지
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _scheduled_start(requirement: str) -> str:
    """예약이 착수할 때 쓰는 경로. 몰래 실제 모델을 부르지 않게 같은 검사를 통과시킨다."""
    if not MOCK and not secrets_broker.ready():
        raise RuntimeError("API 키가 없어 예약을 실행하지 않았습니다")
    return orchestrator.start(requirement, mock=MOCK)


scheduler.configure(_scheduled_start)
scheduler.start()


if __name__ == "__main__":
    print(f"\n  http://127.0.0.1:8000   {'[MOCK 모드]' if MOCK else ''}\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
