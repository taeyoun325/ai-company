"""로컬 웹 서버. 채팅 로그를 SSE로 실시간 스트리밍한다.

  python server.py --mock     API 키 없이 UI 확인
  python server.py            실제 모델로 실행
"""
import json
import queue
import sys

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import bus
import config
import orchestrator
import store

MOCK = "--mock" in sys.argv
app = FastAPI(title="AI Agent Company")


class StartReq(BaseModel):
    requirement: str


@app.get("/")
def index():
    return FileResponse(config.ROOT / "web" / "index.html")


@app.get("/api/agents")
def agents():
    return {"agents": bus.AGENTS, "mock": MOCK, "models": config.MODEL_OF,
            "prices": config.PRICES, "running": orchestrator.is_running()}


@app.post("/api/start")
def start(req: StartReq):
    orchestrator.start(req.requirement.strip(), mock=MOCK)
    return {"ok": True}


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
def project_file(slug: str, path: str):
    try:
        return {"path": path, "content": store.read_file(slug, path)}
    except (ValueError, OSError):
        raise HTTPException(404, "없는 파일")


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


if __name__ == "__main__":
    print(f"\n  http://127.0.0.1:8000   {'[MOCK 모드]' if MOCK else ''}\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
