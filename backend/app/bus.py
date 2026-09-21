"""이벤트 버스 → SSE (지시서 §13).

오케스트레이터(백그라운드 스레드)가 밀어넣고 SSE 가 뽑아간다.

## 왜 큐인가

직원 호출은 동기 블로킹 코드인데 웹 서버는 async 다. 둘 사이를 큐 하나로
끊어놓는 게 제일 단순하고, 스레드 로컬로 잡은 실행 범위도 깨지지 않는다
(§7 이탈 기록과 같은 이유).

## 모든 이벤트에 `run` 과 `id` 가 붙는다

`run` 은 어느 프로젝트의 사건인가. 여러 프로젝트를 동시에 돌리면 이게
없이는 화면에서 섞인다. 실행 하나가 스레드 하나이므로 스레드 로컬에
담긴 run 을 emit 이 자동으로 찍는다.

`id` 는 단조 증가하는 일련번호다. SSE 는 끊긴다 — 프록시가 끊고, 노트북이
잠들고, 탭이 백그라운드로 간다. 재연결할 때 `Last-Event-ID` 를 주면
그 뒤부터만 보낸다. 없으면 사용자는 끊긴 동안의 작업 로그를 영영 못 본다.

## 실행별로 이력을 나눠 보관하는 이유

한 덱(deque)에 전부 쌓으면, 바쁜 실행 하나가 다른 실행의 이력을 밀어낸다.
그러면 조용한 프로젝트의 화면이 이유 없이 비어 보인다.

## 구독자가 느리면 어떻게 되나

큐에 상한을 둔다. 브라우저 탭 하나가 멈춰서 안 읽어가면 그 큐만
무한히 자라고, 결국 서버 메모리를 먹는다. 상한에 닿으면 **그 구독자의
오래된 이벤트를 버리고** 버렸다는 사실을 알린다 — 전체를 멈추는 것보다
한 화면이 일부를 놓치는 편이 낫다.
"""
from __future__ import annotations

import itertools
import json
import queue
import threading
import time
from collections import defaultdict, deque
from typing import Any

from app import config

# 실행 하나당 보관할 최근 이벤트 수
HISTORY_LIMIT = 2000
# 한 구독자가 밀리는 것을 허용하는 한계
SUBSCRIBER_LIMIT = 4000

_lock = threading.RLock()
_local = threading.local()
_seq = itertools.count(1)

# run -> 최근 이벤트
_history: dict[str | None, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))


class Subscriber:
    """한 화면의 구독. `run` 을 주면 그 실행의 이벤트만 받는다."""

    def __init__(self, run: str | None = None, after: int = 0):
        self.run = run
        self.q: queue.Queue = queue.Queue()
        self.dropped = 0

    def wants(self, ev: dict) -> bool:
        return self.run is None or ev.get("run") == self.run

    def offer(self, ev: dict) -> None:
        if not self.wants(ev):
            return
        if self.q.qsize() >= SUBSCRIBER_LIMIT:
            # 느린 화면 하나가 서버 메모리를 먹게 두지 않는다.
            try:
                self.q.get_nowait()
                self.dropped += 1
            except queue.Empty:                 # pragma: no cover
                pass
        self.q.put(ev)


_subscribers: list[Subscriber] = []

AGENTS = {
    "SYSTEM": {"name": "시스템", "icon": "⚙️"},
    "USER": {"name": "CEO", "icon": "🙋"},
    # 이전 제품의 보조 에이전트. AI COMPANY 의 직원과 **다른 것**이다.
    "PM": {"name": "PM (Claude)", "icon": "🧭"},
    "DEV": {"name": "개발자 (Claude)", "icon": "🛠️"},
    "QA": {"name": "검증자 (Gemini)", "icon": "🔍"},
}

# 직원 아이콘 (§8). 직원 표에서 이름을 가져오고 아이콘만 여기 둔다 —
# 아이콘은 화면의 것이지 직원 정의의 것이 아니다.
ICONS = {"strategist": "🧭", "developer": "🛠️", "analyst": "🔍",
         "writer": "✍️", "designer": "🎨"}


def roster() -> dict:
    """화면이 말풍선에 붙일 이름·아이콘. 직원 표를 읽는다.

    늦게 import 하는 이유는 순환이다 — `roles` 가 `config` 를 읽고,
    `providers.base` 가 `bus` 를 읽는다.
    """
    out = dict(AGENTS)
    try:
        from app.agents import roles
        for e in roles.EMPLOYEES.values():
            # 이름은 테넌트가 바꿀 수 있다 (DAY 21). 직함은 자리의 것이라
            # 바뀌지 않는다 — 개발자를 뭐라 부르든 src/ 밖에는 못 쓴다.
            out[e.id] = {"name": f"{roles.display_name(e.id)} ({e.role})",
                         "icon": ICONS.get(e.id, "👤")}
    except Exception:                           # noqa: BLE001
        pass
    return out


# ── 실행 범위 ───────────────────────────────────────────────────────
def bind(run_id: str) -> None:
    """이 스레드가 내보내는 이벤트에 붙일 실행 id."""
    _local.run = run_id


def current() -> str | None:
    return getattr(_local, "run", None)


def release() -> None:
    _local.run = None


# ── 구독 ────────────────────────────────────────────────────────────
def subscribe(run: str | None = None, after: int = 0) -> Subscriber:
    """구독을 연다.

    `after` 는 마지막으로 받은 이벤트 id(SSE 의 `Last-Event-ID`). 그 뒤의
    이력만 되돌려준다. 0 이면 보관된 전부를 준다 — 늦게 접속한 화면도
    처음부터 볼 수 있어야 하기 때문이다.
    """
    sub = Subscriber(run)
    with _lock:
        for ev in replay(run, after):
            sub.q.put(ev)
        _subscribers.append(sub)
    return sub


def unsubscribe(sub: Subscriber) -> None:
    with _lock:
        if sub in _subscribers:
            _subscribers.remove(sub)


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)


def replay(run: str | None = None, after: int = 0) -> list[dict]:
    with _lock:
        if run is None:
            rows = [e for d in _history.values() for e in d]
        else:
            rows = list(_history.get(run, ()))
    rows = [e for e in rows if e["id"] > after]
    return sorted(rows, key=lambda e: e["id"])


# ── 발행 ────────────────────────────────────────────────────────────
RESERVED = ("id", "type", "ts", "run")


def emit(type: str, **payload: Any) -> dict:
    """이벤트를 발행한다.

    `id` · `type` · `ts` · `run` 은 버스의 것이다. 페이로드가 같은 이름을
    쓰면 조용히 덮어쓰지 않고 거부한다 — 실제로 `approvals` 가 `id` 로
    승인 번호를 실었고, 그게 이벤트 일련번호를 덮어써서 재연결 이어받기가
    깨졌다. 조용한 덮어쓰기는 증상이 엉뚱한 곳에서 나온다.
    """
    clash = [k for k in RESERVED if k in payload]
    if clash:
        raise ValueError(
            f"이벤트 필드 {clash} 는 버스가 쓰는 이름입니다. "
            f"다른 이름으로 실으세요 (예: approval_id).")
    run = current()
    ev = {"id": next(_seq), "type": type, "ts": time.time(), "run": run, **payload}
    with _lock:
        _history[run].append(ev)
        subs = list(_subscribers)
    for s in subs:
        s.offer(ev)
    _trace(ev)
    return ev


def reset(run_id: str | None = None) -> None:
    """한 실행의 지난 이벤트만 지운다. 다른 실행의 기록은 건드리지 않는다."""
    rid = run_id or current()
    with _lock:
        if rid is None:
            _history.clear()
            return
        _history.pop(rid, None)


def history(run_id: str | None = None) -> list[dict]:
    return replay(run_id, 0)


# ── 편의 함수: 화면에 뜨는 말풍선 ──────────────────────────────────
def say(agent: str, text: str, kind: str = "say") -> None:
    """agent 가 채팅에 한 마디 남긴다. kind: say | tool | verdict | error"""
    emit("message", agent=agent, kind=kind, text=text)


def phase(name: str, detail: str = "") -> None:
    emit("phase", name=name, detail=detail)


def state(**kw: Any) -> None:
    """대시보드 갱신 (태스크 보드, 비용, 라운드)."""
    emit("state", **kw)


# ── 트레이스 ────────────────────────────────────────────────────────
# 실행별로 파일을 나눈다. 한 파일에 전부 쌓으면 "이 프로젝트에서 무슨 일이
# 있었나"를 보려고 수십만 줄을 훑어야 하고, 동시 실행이 서로의 줄 사이에
# 끼어든다.
_files: dict[str, Any] = {}


def _trace_path(run: str | None):
    name = f"{run}.jsonl" if run else "trace.jsonl"
    return config.LOGS / name


def _trace(ev: dict) -> None:
    run = ev.get("run")
    try:
        with _lock:
            f = _files.get(run or "")
            if f is None or f.closed:
                config.LOGS.mkdir(parents=True, exist_ok=True)
                f = open(_trace_path(run), "a", encoding="utf-8")
                _files[run or ""] = f
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            f.flush()
    except OSError:
        # 기록에 실패했다고 실행을 멈추지 않는다. 트레이스는 증거물이지
        # 실행의 전제가 아니다.
        pass


def close_trace(run: str | None = None) -> None:
    with _lock:
        key = run or ""
        f = _files.pop(key, None)
    if f is not None and not f.closed:
        f.close()


def close_all_traces() -> None:
    with _lock:
        files = list(_files.values())
        _files.clear()
    for f in files:
        if not f.closed:
            f.close()
