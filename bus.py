"""이벤트 버스. 오케스트레이터(백그라운드 스레드)가 밀어넣고 SSE가 뽑아간다.

thread-safe queue를 쓰는 이유: 에이전트 호출은 동기 블로킹 코드인데
웹 서버는 async라서, 둘 사이를 큐 하나로 끊어놓는 게 제일 단순하다.
"""
import json
import queue
import threading
import time
from typing import Any

import config

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()
_history: list[dict] = []

AGENTS = {
    "SYSTEM": {"name": "시스템", "icon": "⚙️"},
    "USER": {"name": "의뢰인", "icon": "🙋"},
    "PM": {"name": "PM (Claude)", "icon": "🧭"},
    "DEV": {"name": "개발자 (Claude)", "icon": "🛠️"},
    "QA": {"name": "검증자 (Gemini)", "icon": "🔍"},
}


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _lock:
        for ev in _history:          # 늦게 접속해도 처음부터 보이게
            q.put(ev)
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def emit(type: str, **payload: Any) -> None:
    ev = {"type": type, "ts": time.time(), **payload}
    with _lock:
        _history.append(ev)
        subs = list(_subscribers)
    for q in subs:
        q.put(ev)
    _trace(ev)


def reset() -> None:
    with _lock:
        _history.clear()


# --- 편의 함수: 화면에 뜨는 말풍선 ---
def say(agent: str, text: str, kind: str = "say") -> None:
    """agent가 채팅에 한 마디 남긴다. kind: say | tool | verdict | error"""
    emit("message", agent=agent, kind=kind, text=text)


def phase(name: str, detail: str = "") -> None:
    emit("phase", name=name, detail=detail)


def state(**kw: Any) -> None:
    """우측 대시보드 갱신 (태스크 보드, 비용, 라운드)."""
    emit("state", **kw)


def _trace(ev: dict) -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    with open(config.LOGS / "trace.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
