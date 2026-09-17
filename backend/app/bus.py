"""이벤트 버스. 오케스트레이터(백그라운드 스레드)가 밀어넣고 SSE가 뽑아간다.

thread-safe queue를 쓰는 이유: 에이전트 호출은 동기 블로킹 코드인데
웹 서버는 async라서, 둘 사이를 큐 하나로 끊어놓는 게 제일 단순하다.

**모든 이벤트에 `run`(프로젝트 slug)이 붙는다.** 여러 프로젝트를 동시에 돌리면
어느 실행의 사건인지 구분해야 화면에서 섞이지 않는다. 실행 하나가 스레드
하나이므로, 스레드 로컬에 담긴 run을 emit이 자동으로 찍어준다.
"""
import json
import queue
import threading
import time
from collections import deque
from typing import Any

from app import config

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()
_local = threading.local()

# 늦게 접속한 클라이언트에게 되돌려줄 최근 이벤트. 무한히 쌓이면 메모리를 먹는다.
HISTORY_LIMIT = 4000
_history: deque[dict] = deque(maxlen=HISTORY_LIMIT)

AGENTS = {
    "SYSTEM": {"name": "시스템", "icon": "⚙️"},
    "USER": {"name": "의뢰인", "icon": "🙋"},
    "PM": {"name": "PM (Claude)", "icon": "🧭"},
    "DEV": {"name": "개발자 (Claude)", "icon": "🛠️"},
    "QA": {"name": "검증자 (Gemini)", "icon": "🔍"},
}


def bind(run_id: str) -> None:
    """이 스레드가 내보내는 이벤트에 붙일 실행 id."""
    _local.run = run_id


def current() -> str | None:
    return getattr(_local, "run", None)


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _lock:
        for ev in list(_history):    # 늦게 접속해도 처음부터 보이게
            q.put(ev)
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def emit(type: str, **payload: Any) -> None:
    ev = {"type": type, "ts": time.time(), "run": current(), **payload}
    with _lock:
        _history.append(ev)
        subs = list(_subscribers)
    for q in subs:
        q.put(ev)
    _trace(ev)


def reset(run_id: str | None = None) -> None:
    """한 실행의 지난 이벤트만 지운다. 다른 실행의 기록은 건드리지 않는다."""
    rid = run_id or current()
    with _lock:
        if rid is None:
            _history.clear()
            return
        keep = [e for e in _history if e.get("run") != rid]
        _history.clear()
        _history.extend(keep)


def history(run_id: str | None = None) -> list[dict]:
    with _lock:
        if run_id is None:
            return list(_history)
        return [e for e in _history if e.get("run") == run_id]


# --- 편의 함수: 화면에 뜨는 말풍선 ---
def say(agent: str, text: str, kind: str = "say") -> None:
    """agent가 채팅에 한 마디 남긴다. kind: say | tool | verdict | error"""
    emit("message", agent=agent, kind=kind, text=text)


def phase(name: str, detail: str = "") -> None:
    emit("phase", name=name, detail=detail)


def state(**kw: Any) -> None:
    """대시보드 갱신 (태스크 보드, 비용, 라운드)."""
    emit("state", **kw)


def _trace(ev: dict) -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    with open(config.LOGS / "trace.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
