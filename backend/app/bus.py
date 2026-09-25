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
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Any

from app import config

# 실행 하나당 보관할 최근 이벤트 수
HISTORY_LIMIT = 2000
# 한 구독자가 밀리는 것을 허용하는 한계
SUBSCRIBER_LIMIT = 4000
# **메모리에 이력을 남겨둘 실행의 수** (DAY 22).
#
# 이벤트 수만 묶어두면 부족했다. 실행 하나가 2000개로 묶여 있어도,
# 끝난 실행의 이력이 지워지지 않아서 **실행 개수만큼 쌓였다.** 실행
# 50개에 3.4MB — 오래 도는 서버에서는 끝없이 자란다.
#
# 오래된 실행부터 내보낸다. 내보낸 뒤에도 잃는 것은 **화면의 실시간
# 로그**뿐이다 — 산출물·점수·태스크는 파일에 있고, 프로젝트 상세 화면은
# 그걸 읽는다. 서버를 한 번 재시작해도 같은 일이 일어나므로, 이건 새로
# 생긴 손실이 아니라 이미 있던 성질이다.
RUN_HISTORY_LIMIT = int(os.getenv("RUN_HISTORY_LIMIT", "24"))

_lock = threading.RLock()
_local = threading.local()
# 일련번호는 **프로세스가 뜬 시각(밀리초)부터** 센다 (DAY 25).
#
# 1 부터 세면 서버를 다시 켤 때마다 번호가 처음으로 돌아간다. 그러면
# (1) 같은 실행의 트레이스 파일에서 재시작 **뒤의** 이벤트가 앞의 것보다
# 작은 번호를 달아, 번호순으로 읽으면 옛 상태가 "마지막"이 된다 — 승인하고
# 재개한 실행을 사무실이 0/3 으로 보여줬다. (2) 브라우저가 들고 있던
# `Last-Event-ID` 보다 작은 번호만 오므로 재연결해도 새 이벤트를 못 받는다.
# 시각에서 시작하면 재시작 뒤의 번호가 항상 더 크다(초당 1000건을 넘게
# 내지 않는 한). 자바스크립트 정수 한도(2^53) 안이다.
_seq = itertools.count(int(time.time() * 1000))

# run -> 최근 이벤트. **삽입 순서가 곧 오래된 순서**다(파이썬 dict 성질).
# 새 이벤트가 올 때마다 그 실행을 맨 뒤로 옮기므로, 앞쪽이 가장 오래
# 건드리지 않은 실행이 된다.
_history: dict[str | None, deque] = {}


def _bucket(run: str | None) -> deque:
    """이 실행의 이벤트 통. 없으면 만들고, 넘치면 오래된 실행을 내보낸다."""
    d = _history.pop(run, None)
    if d is None:
        d = deque(maxlen=HISTORY_LIMIT)
    _history[run] = d                      # 맨 뒤로 = 가장 최근에 쓰임
    while len(_history) > RUN_HISTORY_LIMIT:
        oldest = next(iter(_history))
        if oldest == run:                  # 지금 쓰는 것은 내보내지 않는다
            break
        _history.pop(oldest, None)
    return d


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

# 직원이 아닌 화자들. 이름은 **부를 때** 번역표에서 가져온다 — 여기에
# 박아두면 영어 로그에서 "시스템" 이 제일 자주 보이는 한국어가 된다.
AGENTS = {
    "SYSTEM": {"name": "who.system", "icon": "⚙️"},
    "USER": {"name": "CEO", "icon": "🙋"},
    # 이전 제품의 보조 에이전트. AI COMPANY 의 직원과 **다른 것**이다.
    "PM": {"name": "PM (Claude)", "icon": "🧭"},
    "DEV": {"name": "who.legacyDev", "icon": "🛠️"},
    "QA": {"name": "who.legacyQa", "icon": "🔍"},
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
    # `who.` 로 시작하는 이름은 번역표의 키다. 여기서 문장으로 바꾼다 —
    # 표에 없는 이름(CEO · PM)은 그대로 쓴다.
    from app import lang
    out = {k: {**v,
               "name": lang.t(v["name"]) if v["name"].startswith("who.")
               else v["name"]}
           for k, v in AGENTS.items()}
    try:
        from app.agents import roles
        for e in roles.EMPLOYEES.values():
            # 이름은 테넌트가 바꿀 수 있다 (DAY 21). 직함은 자리의 것이라
            # 바뀌지 않는다 — 개발자를 뭐라 부르든 src/ 밖에는 못 쓴다.
            # 다만 직함 **글자**는 보는 사람의 언어로 나간다(DAY 22):
            # 로그의 말하는 이 표시가 여기서 나오므로, 이 한 줄이 한국어면
            # 영어 로그의 모든 말풍선에 한국어 직함이 붙는다.
            out[e.id] = {"name": roles.display(e.id),
                         "icon": ICONS.get(e.id, "👤")}
    except Exception:                           # noqa: BLE001
        pass
    return out


# ── 실행 범위 ───────────────────────────────────────────────────────
def bind(run_id: str) -> None:
    """이 스레드가 내보내는 이벤트에 붙일 실행 id."""
    _local.run = run_id
    # 새 실행은 이전 실행의 "마지막으로 맡았던 사람"을 물려받지 않는다
    # (스레드 풀이 스레드를 재사용하면 `_local` 이 남아 있다). 물려받으면
    # 새 실행의 첫 단계가 엉뚱하게 "누구에게서 전달받음"으로 찍힌다.
    _local.phase_owner = None
    _local.phase_display = None


def current() -> str | None:
    return getattr(_local, "run", None)


def release() -> None:
    _local.run = None
    _local.phase_owner = None
    _local.phase_display = None


@contextmanager
def scoped(run_id: str | None):
    """잠깐 `run_id` 로 묶었다가 **원래대로** 되돌린다.

    `bind()` 와 달리 단계 담당자(`phase_owner`)를 지우지 않는다 — 같은
    실행이면 아무것도 바꾸지 않는다. 스트리밍처럼 한 호출이 여러 스레드를
    거쳐 이어질 때(`astream` 은 조각마다 스레드 풀의 아무 스레드에서 돈다)
    그 조각 동안만 실행을 세운다.
    """
    prev = current()
    if prev == run_id:
        yield
        return
    owner = getattr(_local, "phase_owner", None)
    display = getattr(_local, "phase_display", None)
    _local.run = run_id
    try:
        yield
    finally:
        _local.run = prev
        _local.phase_owner = owner
        _local.phase_display = display


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
        _bucket(run).append(ev)
        subs = list(_subscribers)
    for s in subs:
        s.offer(ev)
    _trace(ev)
    return ev


def reset(run_id: str | None = None) -> None:
    """한 실행의 지난 이벤트만 지운다. 다른 실행의 기록은 건드리지 않는다.

    트레이스 파일도 함께 지운다. 같은 slug 로 다시 돌리면(재시도·재실행)
    이전 판의 줄이 파일에 남아있고, 파일을 그대로 따라가는 다른 인스턴스는
    새 실행과 옛 실행을 구분하지 못한다 — 메모리는 이미 그렇게 비웠으니
    파일도 같은 이야기를 해야 한다.
    """
    rid = run_id or current()
    with _lock:
        if rid is None:
            _history.clear()
            return
        _history.pop(rid, None)
    close_trace(rid)
    try:
        _trace_path(rid).unlink(missing_ok=True)
    except OSError:
        # 다른 프로세스가 아직 그 파일을 쓰고 있을 수 있다(Windows 는
        # 열린 파일을 못 지운다). 지우기는 정리일 뿐 실행의 전제가 아니다.
        pass


def history(run_id: str | None = None) -> list[dict]:
    return replay(run_id, 0)


# ── 편의 함수: 화면에 뜨는 말풍선 ──────────────────────────────────
def say(agent: str, text: str, kind: str = "say") -> None:
    """agent 가 채팅에 한 마디 남긴다. kind: say | tool | verdict | error"""
    emit("message", agent=agent, kind=kind, text=text)


# 단계 → 담당자. 프론트(Office.tsx · page.tsx 의 PHASE_OWNER)와 같은
# 대응이다. 대부분은 항상 같은 사람이 맡는다 — IMPLEMENT · MANUAL 처럼
# 맡는 사람이 매번 바뀌는 단계만 호출하는 쪽이 `owner` 로 직접 넘긴다.
PHASE_OWNER: dict[str, str | None] = {
    "PLAN": "strategist", "REPLAN": "strategist", "FINALIZE": "strategist",
    "WRITE_TESTS": "analyst", "REVIEW": "analyst",
    "TEST": None, "IMPLEMENT": None, "MANUAL": None,
}


def phase(name: str, detail: str = "", owner: str | None = None,
          lane: str | None = None) -> None:
    """단계가 바뀌었다.

    로그를 쭉 읽으면 "지금 무슨 일이 벌어지고 있나"가 대화 중간에 묻힌다.
    그래서 단계가 바뀌는 순간(= 한 직원의 몫이 끝나고 다음 직원에게
    넘어가는 순간)에만 한 줄 헤드라인을 붙인다. 모델을 불러 매 줄을
    요약하면 비용이 끝없이 나간다(§11 과 같은 규칙, narrator.py 참고) —
    이건 표 하나로 정해지는 규칙 기반이라 공짜고 즉시 나간다.

    `owner` 를 안 주면 `PHASE_OWNER` 표를 본다. 둘 다 없으면(TEST 처럼
    특정 직원이 아니라 자동화가 하는 단계) 헤드라인 없이 단계 이름만
    나간다 — 화면은 그 경우 원래 하던 대로 보여준다.
    """
    from app import lang
    from app.agents import roles

    resolved = owner if owner is not None else PHASE_OWNER.get(name)
    try:
        owner_name = roles.display_name(resolved) if resolved else None
    except Exception:                                       # noqa: BLE001
        owner_name = None                  # 헤드라인은 있으면 좋은 것이다

    prev_owner = getattr(_local, "phase_owner", None)
    prev_name = getattr(_local, "phase_display", None)

    headline = None
    if owner_name:
        if prev_owner and prev_name and resolved != prev_owner:
            headline = lang.t("bus.handoff", frm=prev_name, to=owner_name)
        elif prev_owner is None:
            headline = lang.t("bus.started", who=owner_name)

        _local.phase_owner = resolved
        _local.phase_display = owner_name
    # 담당자가 없는 단계(TEST 처럼 자동화가 하는 단계)는 "마지막으로 맡은
    # 사람"을 지우지 않는다. 지우면 TEST 다음 REVIEW 가 "최유나 완료 —
    # 최유나에게 전달"이 아니라 매번 "시작"으로만 보인다 — IMPLEMENT 가
    # 끝나고 REVIEW 로 진짜 넘어간 것인데, 그 사이에 자동화가 한 번
    # 끼었다는 이유로 인계 정보가 사라지면 안 된다.

    # `lane` 은 병렬로 도는 태스크 중 **어느 줄의** 단계인가 (DAY 25).
    # 태스크가 둘 이상 동시에 돌면 단계 이벤트가 섞여 온다 — 화면과 지표가
    # "지금 무슨 단계인가"를 줄마다 따로 접으려면 이게 있어야 한다.
    extra = {"lane": lane} if lane is not None else {}
    emit("phase", name=name, detail=detail, headline=headline, **extra)


def state(**kw: Any) -> None:
    """대시보드 갱신 (태스크 보드, 비용, 라운드)."""
    emit("state", **kw)


def handoff(from_id: str, to_id: str, phase: str, **detail: Any) -> None:
    """한 직원의 몫이 끝나고 다음으로 넘어갈 때, **왜** 넘어가는지를 구조로 남긴다.

    `say()` 는 `message_to_team` 한 줄만 채팅에 남긴다. 그런데 직원이
    실제로 돌려주는 값에는 그보다 많은 것이 있다 — 무엇을 확인했고
    확인하지 못했는지(`self_check`), 검증자가 무엇을 지적했는지
    (`findings`), 어떤 인수기준이 충족됐는지(`met`/`unmet`). 이게 한
    줄로 뭉개지면 "왜 이렇게 됐나"를 나중에 로그로 되짚을 방법이
    없어진다. `**detail` 은 호출부가 스키마에서 그대로 뽑아 넘긴다 —
    여기서 스키마마다 분기하면 스키마를 늘릴 때마다 여기도 고쳐야 한다.

    모델을 새로 부르지 않는다(§11 과 같은 원칙) — 이미 받은 답을
    구조 그대로 기록만 한다.
    """
    emit("handoff", **{"from": from_id, "to": to_id, "phase": phase, **detail})


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


# ── 인스턴스를 넘나드는 조회 (DAY 23) ──────────────────────────────
#
# `replay`/`subscribe` 는 이 프로세스의 메모리만 본다. 실행이 인스턴스
# A 에서 돌면, 그 이벤트는 A 의 `_history`·`_subscribers` 에만 쌓인다.
# 화면이 인스턴스 B 에 붙으면(로드밸런서가 매번 같은 인스턴스로 보내준다는
# 보장이 없다) A 가 쌓은 건 B 눈에 안 보인다.
#
# 실행은 프로세스 하나(스레드 하나)에서만 돈다 — 그 프로세스가 쓰는
# 트레이스 파일이 그 실행의 유일한 진실이다. 그러니 `run` 이 있는 조회는
# 메모리 대신 파일을 읽으면 **어느 인스턴스에서 보든** 같은 답이 나온다.
# 전체 조회(`run=None`, 대시보드)는 여러 파일을 아이디 충돌 없이 합치는
# 문제라 아직 이걸로 못 고친다 — `id` 가 프로세스마다 따로 세진 일련번호라서.
FILE_POLL_INTERVAL = float(os.getenv("BUS_FILE_POLL_INTERVAL", "0.3"))


def _parse_trace_lines(lines) -> list[dict]:
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # 쓰는 도중에 읽으면 마지막 줄이 잘려 있을 수 있다.
            continue
    return out


def read_trace(run: str, after: int = 0) -> list[dict]:
    """`run` 하나의 이벤트를 트레이스 파일에서 읽는다. 인스턴스를 안 가린다."""
    try:
        with open(_trace_path(run), "r", encoding="utf-8") as f:
            events = _parse_trace_lines(f)
    except FileNotFoundError:
        return []
    events = [e for e in events if e.get("id", 0) > after]
    return sorted(events, key=lambda e: e["id"])


def tail_trace(run: str, after: int = 0):
    """`run` 하나를 계속 따라가며 새 이벤트를 낸다. 새 줄이 없으면 `None`.

    새로 읽은 바이트 위치(`pos`)부터 이어 읽는다 — 매번 파일 전체를 다시
    훑지 않는다. `None` 은 살아있다는 뜻으로만 쓴다: 호출부가 그걸로 SSE
    keepalive 박자를 맞춘다. 서버가 죽지 않는 한 끝나지 않는다; 연결이
    끊기면(제너레이터가 버려지면) 자연히 멈춘다.
    """
    path = _trace_path(run)
    last_id = after
    pos = 0
    while True:
        new_events = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(pos)
                new_events = _parse_trace_lines(f)
                pos = f.tell()
        except FileNotFoundError:
            pass
        fresh = [e for e in new_events if e.get("id", 0) > last_id]
        for ev in sorted(fresh, key=lambda e: e["id"]):
            last_id = ev["id"]
            yield ev
        if not fresh:
            yield None
        time.sleep(FILE_POLL_INTERVAL)
