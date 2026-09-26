"""Cloud Run 컨테이너 감독자 (DAY 27) — **쓰는 인스턴스를 하나로** 보장한다.

## 왜 필요한가

SQLite 는 Litestream 이 Cloud Storage 로 복제한다. Litestream 은 "같은 경로에
동시에 둘이 복제하면 복원이 불가능해질 수 있다"고 적고, 그걸 막는 건 사용자의
몫이라고 한다(litestream.io/tips). 그런데 Cloud Run 의 최대 인스턴스 수는
**리비전마다** 따로 세지고, 배포 직후에는 옛 리비전 인스턴스가 새 것과 함께
떠 있다(공식 문서). 실제로 DAY 27 에 잰 로그에서 옛 인스턴스가 새 리비전과
**한 시간 가까이** 겹쳐 살아 있었다. `--max-instances 1` 은 보장이 아니다.

## 어떻게 막나 — Cloud Storage 객체 하나로 임대(lease)

`lease.json` 을 조건부 쓰기(ifGenerationMatch)로만 고친다. 같은 세대를 보고
둘이 동시에 쓰면 하나는 412 로 진다 — 그게 원자성의 전부다.

    받기   없거나 released 거나 오래 멈춰 있으면 가져간다 — 단 **옛 리비전은
           새 리비전의 임대를 절대 가져가지 않는다**
           더 새 리비전이면 handoff 를 적고 내려놓기를 기다린다(배포)
           같은 리비전이 쥐고 있으면 기다리기만 한다 — 잠깐 한도를 넘어 뜬
           복제본이 멀쩡한 주인을 끌어내리면 안 된다
           되돌리기는 옛 이미지를 **새 리비전으로** 다시 배포해서 한다
           (트래픽만 옛 리비전으로 돌리면 그 리비전은 임대를 못 받는다)
    넘긴 뒤 끝내지 않고 대기한다(standby) — 끝내면 Cloud Run 이 옛 리비전을
           다시 띄우고, 그게 다시 넘겨 달라고 하는 핑퐁이 실제로 났다
    쥐기   HEARTBEAT 마다 다시 쓴다. 실패하면 읽어 본다:
             handoff  → 앱을 정상 종료(Litestream 이 마지막 WAL 을 올린다) 후 released
             남이 가짐 → **즉시 강제 종료.** 더 쓰면 새 주인의 세대를 덮는다
           SELF_FENCE 초 동안 갱신을 못 하면 스스로 강제 종료한다 —
           가져가는 쪽(STALE 초)보다 **먼저** 멈춰야 겹치지 않는다
    놓기   SIGTERM(Cloud Run 의 정상 종료) → 정상 종료 → released

"오래 멈춤"은 상대의 시계로 재지 않는다. **내가 본 세대가 내 시계로 STALE
초 동안 그대로면** 멈춘 것이다 — 두 기계의 시계가 달라도 틀리지 않는다.

## 무엇을 못 막나

- 주인이 바뀌는 순간 옛 주인에서 돌던 실행은 끊긴다(배포 = 실행 중단).
- 주인이 SIGKILL 로 죽으면 마지막 1초 안의 쓰기는 잃을 수 있다
  (Litestream sync-interval).
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BUCKET = os.environ.get("STATE_BUCKET", "")
OBJECT = os.environ.get("LEASE_OBJECT", "lease.json")
REVISION = os.environ.get("K_REVISION", "local")
HEARTBEAT = float(os.environ.get("LEASE_HEARTBEAT", "10"))
SELF_FENCE = float(os.environ.get("LEASE_SELF_FENCE", "30"))
STALE = float(os.environ.get("LEASE_STALE", "45"))
# 같은 리비전의 주인이 멀쩡하면 이만큼 기다리다 포기한다. Cloud Run 시작
# 검사(기본 240초)보다 짧아야 우리가 먼저 깔끔하게 내려간다.
GIVE_UP = float(os.environ.get("LEASE_GIVE_UP", "200"))
STOP_GRACE = float(os.environ.get("STOP_GRACE", "8"))

META = "http://metadata.google.internal/computeMetadata/v1"
API = "https://storage.googleapis.com"


def log(msg: str) -> None:
    print(f"[lease] {msg}", flush=True)


# ── Cloud Storage (표준 라이브러리만) ─────────────────────────────────
_token: tuple[str, float] = ("", 0.0)


def _meta(path: str) -> str:
    req = urllib.request.Request(f"{META}/{path}", headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode()


def token() -> str:
    global _token
    if time.time() < _token[1] - 60:
        return _token[0]
    d = json.loads(_meta("instance/service-accounts/default/token"))
    _token = (d["access_token"], time.time() + d["expires_in"])
    return _token[0]


def _call(method: str, url: str, body: bytes | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Authorization": f"Bearer {token()}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def read() -> tuple[dict | None, int]:
    """(내용, 세대). 없으면 (None, 0)."""
    name = urllib.parse.quote(OBJECT, safe="")
    st, meta = _call("GET", f"{API}/storage/v1/b/{BUCKET}/o/{name}")
    if st == 404:
        return None, 0
    if st != 200:
        raise RuntimeError(f"lease read {st}: {meta[:200]!r}")
    gen = int(json.loads(meta)["generation"])
    st, body = _call("GET", f"{API}/storage/v1/b/{BUCKET}/o/{name}?alt=media&generation={gen}")
    if st == 404:                       # 읽는 사이에 바뀌었다 — 다시 본다
        return read()
    if st != 200:
        raise RuntimeError(f"lease body {st}: {body[:200]!r}")
    return json.loads(body), gen


def write(doc: dict, if_gen: int) -> int | None:
    """조건부 쓰기. 성공하면 새 세대, 남이 먼저 바꿨으면 None."""
    q = urllib.parse.urlencode({"uploadType": "media", "name": OBJECT,
                                "ifGenerationMatch": str(if_gen)})
    st, body = _call("POST", f"{API}/upload/storage/v1/b/{BUCKET}/o?{q}",
                     json.dumps(doc).encode())
    if st == 412:
        return None
    if st != 200:
        raise RuntimeError(f"lease write {st}: {body[:200]!r}")
    return int(json.loads(body)["generation"])


# ── 임대 ──────────────────────────────────────────────────────────────
ME = ""


def _doc(state: str, **extra) -> dict:
    return {"holder": ME, "revision": REVISION, "state": state, "ts": time.time(), **extra}


def acquire(stop: dict | None = None, give_up: bool = True,
            may_ask=lambda: True) -> int | None:
    """임대를 받을 때까지 기다린다. 받은 세대, 또는 SIGTERM 이면 None.

    `give_up=False` 는 대기 모드(standby)에서 쓴다 — 거기서 끝내면 Cloud Run 이
    인스턴스를 다시 띄울 뿐이다.
    """
    started = time.monotonic()
    seen_gen, seen_at = -1, time.monotonic()
    asked = False
    while not (stop and stop["sig"]):
        try:
            got = _acquire_step(started if give_up else None, seen_gen, seen_at, asked,
                                may_ask)
        except Exception as e:          # noqa: BLE001 — 일시 오류는 다시 본다
            log(f"임대 확인 실패, 다시 본다: {e}")
            time.sleep(2)
            continue
        kind, val = got
        if kind == "got":
            return val
        seen_gen, seen_at, asked = val
    return None


def rev_num(name: str | None) -> int:
    """'ai-company-00006-sp6' → 6. 모르면 0."""
    m = re.search(r"-(\d+)-[a-z0-9]+$", name or "")
    return int(m.group(1)) if m else 0


def _acquire_step(started, seen_gen, seen_at, asked, may_ask=lambda: True):
    """한 번 보고 판단한다. ("got", 세대) 또는 ("wait", (seen_gen, seen_at, asked)).

    리비전 순서 규칙 (DAY 27 실측 뒤): **옛 리비전은 새 리비전의 임대를 절대
    가져가지 않는다.** 처음엔 "리비전이 다르면 넘겨 달라"였다. 넘겨준 옛
    인스턴스가 끝나자 Cloud Run 이 옛 리비전을 다시 띄웠고, 그게 새 주인에게
    다시 넘겨 달라고 했다 — 1분 동안 여섯 번 주인이 바뀌었다(DB 복원 여섯 번).
    되돌리기는 옛 이미지를 **새 리비전으로** 다시 배포해서 한다.
    """
    doc, gen = read()
    if gen != seen_gen:
        seen_gen, seen_at = gen, time.monotonic()
    frozen = time.monotonic() - seen_at
    mine, theirs = rev_num(REVISION), rev_num(doc and doc.get("revision"))
    older = mine < theirs
    # 넘겨주며 놓은 임대는 **요청한 새 리비전 몫**이다. 넘겨준 쪽이 대기 모드에서
    # 방금 놓은 자기 임대를 다시 집어 가면 새 인스턴스는 옛 인스턴스가 끝날
    # 때까지 기다린다(DAY 27 실측 5초). 예약한 쪽이 멈춰 있으면(STALE) 풀린다.
    reserved_for = rev_num(doc and doc.get("for_revision"))
    reserved = (doc is not None and doc.get("state") == "released"
                and reserved_for > mine and frozen < STALE)
    free = (doc is None or doc.get("state") == "released"
            or doc.get("holder") == ME or frozen >= STALE) and not reserved
    if free and not older:
        why = ("없음" if doc is None else "released" if doc.get("state") == "released"
               else f"{frozen:.0f}초 멈춤")
        new = write(_doc("held"), gen)
        if new is not None:
            log(f"받음 ({why}) gen={new}")
            return "got", new
        return "wait", (seen_gen, seen_at, asked)      # 누가 먼저 바꿨다 — 다시 본다
    newer = mine > theirs
    # **내게 요청이 실제로 오기 시작한 뒤에** 넘겨 달라고 한다 (DAY 27 실측).
    # 앞문을 열자마자 요청했더니 Cloud Run 은 몇 초 더 옛 리비전으로 보냈고,
    # 이미 넘겨준 옛 인스턴스가 그 요청에 503 을 냈다(360회 중 5회).
    if newer and doc.get("state") != "handoff" and not asked and may_ask():
        if write({**doc, "state": "handoff", "by": ME, "by_revision": REVISION}, gen) is not None:
            log(f"넘겨 달라고 요청 — 주인 {doc.get('revision')}")
            return "wait", (seen_gen, seen_at, True)
        return "wait", (seen_gen, seen_at, asked)
    if not newer and started is not None and time.monotonic() - started > GIVE_UP:
        log(f"주인({doc.get('revision')})보다 새 리비전이 아니다 — 이 인스턴스는 내려간다")
        sys.exit(3)
    # 넘겨받기를 기다리는 동안은 자주 본다 — 그 시간만큼 앞문에 붙잡힌 요청이 늦는다.
    time.sleep(0.5 if (asked or newer) else 2)
    return "wait", (seen_gen, seen_at, asked)


def release(gen: int) -> None:
    try:
        doc, cur = read()
        if doc and doc.get("holder") == ME:
            if write(_doc("released"), cur) is not None:
                log("내려놓음")
    except Exception as e:              # noqa: BLE001 — 못 놓으면 STALE 뒤에 넘어간다
        log(f"내려놓기 실패 (STALE 뒤 넘어감): {e}")


# ── 무중단 인계 (DAY 27) ─────────────────────────────────────────────
#
# 처음 판: 새 인스턴스는 임대를 받고 DB 를 되살리고 앱을 띄운 **뒤에야** 포트를
# 열었다. Cloud Run 은 그때까지 옛 리비전으로 보냈는데, 옛 인스턴스는 이미
# 넘겨준 뒤라 ~10초 동안 요청이 실패했다(실측 170회 중 1회, 30초 매달림).
#
# 지금: 새 인스턴스는 **임대를 곧 받을 수 있다고 보이면 바로** 앞문(:PORT)을
# 연다. Cloud Run 은 새 리비전으로 요청을 넘기고, 앞문은 그 요청을 **실패시키지
# 않고 붙잡아 둔다**(HOLD). 그 사이 임대 인계 → DB 복원 → 앱 시작이 끝나면
# 붙잡힌 요청을 그대로 흘려보낸다(READY). 실패가 잠깐의 지연이 된다.
#
# 그 지연을 줄이려고 무거운 것은 임대 전에 해 둔다: Next 는 상태가 없으니
# 바로 띄우고, 백엔드는 무거운 라이브러리만 미리 불러 둔 채(backend_boot.py)
# "go" 를 기다린다. 우리 코드(app.main)는 DB 를 만지므로 임대 뒤에만 부른다.
import asyncio
import threading
import urllib.request as _rq

PORT = int(os.environ.get("PORT", "8080"))
NEXT_PORT = int(os.environ.get("NEXT_PORT", "3000"))
BACKEND_HEALTH = "http://127.0.0.1:8000/api/deploy"
HOLD_MAX = float(os.environ.get("HOLD_MAX", "55"))       # Hosting 60초 한도 안
LOOK_EVERY = float(os.environ.get("LEASE_LOOK_EVERY", "1"))
DBS = ("ai_company_auth.db", "ai_company.db")


class Front:
    """앞문. 모드: hold(붙잡기) · ready(Next 로 잇기) · standby(503, 생존 검사만 200)."""

    def __init__(self):
        self.mode = "hold"
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ready: asyncio.Event | None = None
        self.bound = False
        # 생존 검사가 아닌 요청이 한 번이라도 왔는가 — Cloud Run 이 트래픽을
        # 이리로 옮겼다는 증거. 그 뒤에야 옛 주인에게 넘겨 달라고 한다.
        self.first_request = threading.Event()

    def open(self) -> None:
        if self.bound:
            return
        started = threading.Event()

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._ready = asyncio.Event()
            if self.mode == "ready":
                self._ready.set()
            try:
                self._srv = self.loop.run_until_complete(
                    asyncio.start_server(self._handle, "0.0.0.0", PORT, reuse_address=True))
            except OSError as e:
                self.error = e
                started.set()
                return
            started.set()
            self.loop.run_forever()

        self.error: OSError | None = None
        threading.Thread(target=run, daemon=True, name="front").start()
        if not started.wait(10) or self.error is not None:
            # 문을 못 열었는데 연 줄 알면, 시작 검사가 영영 통과하지 않는 이유를
            # 아무도 모른다. 조용히 넘어가지 않고 여기서 멈춘다.
            raise RuntimeError(f"앞문을 열지 못했다 (:{PORT}): {self.error}")
        self.bound = True
        log(f"앞문을 열었다 (:{PORT}, {self.mode})")

    def set(self, mode: str) -> None:
        self.mode = mode
        if self.loop is None:
            return

        def apply():
            if mode == "ready":
                self._ready.set()
            else:
                self._ready.clear()
        self.loop.call_soon_threadsafe(apply)

    async def _handle(self, reader, writer):
        head = b""
        try:
            if self.mode != "ready":
                if self.mode == "standby":
                    return await self._standby(reader, writer)
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 30)
                if _path_of(head) == "/api/deploy":
                    # 붙잡는 동안의 생존 검사 — 붙잡으면 제한 시간(5초)에 걸려
                    # 인스턴스가 재시작된다. 앱이 뜨면 이 경로도 백엔드로 간다.
                    return await self._reply(writer, 200)
                self.first_request.set()
                try:
                    await asyncio.wait_for(self._ready.wait(), HOLD_MAX)
                except asyncio.TimeoutError:
                    return await self._reply(writer, 503)
                if self.mode != "ready":
                    return await self._reply(writer, 503)
            up_r, up_w = await asyncio.open_connection("127.0.0.1", NEXT_PORT)
            if head:
                up_w.write(head)
        except Exception:                                      # noqa: BLE001
            writer.close()
            return

        async def pipe(src, dst):
            try:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()
            except Exception:                                  # noqa: BLE001
                pass
            finally:
                try:
                    dst.close()
                except Exception:                              # noqa: BLE001
                    pass

        await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))

    async def _standby(self, reader, writer):
        """임대가 없는 인스턴스의 답. 생존 검사에는 200(재시작을 부르지 않게)."""
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        except Exception:                                      # noqa: BLE001
            head = b""
        await self._reply(writer, 200 if _path_of(head) == "/api/deploy" else 503)

    @staticmethod
    async def _reply(writer, status: int):
        body = b'{"standby": true}'
        writer.write((f"HTTP/1.1 {'200 OK' if status == 200 else '503 Service Unavailable'}\r\n"
                      "Content-Type: application/json\r\nRetry-After: 2\r\n"
                      f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                      ).encode() + body)
        try:
            await writer.drain()
        finally:
            writer.close()


def _path_of(head: bytes) -> str:
    try:
        return head.split(b" ", 2)[1].decode("latin-1").split("?")[0]
    except Exception:                                          # noqa: BLE001
        return ""


class Procs:
    """자식 프로세스들: Next · 백엔드(미리 데워 둔) · Litestream."""

    def __init__(self):
        self.next: subprocess.Popen | None = None
        self.backend: subprocess.Popen | None = None
        self.litestream: subprocess.Popen | None = None

    def start_next(self) -> None:
        env = {**os.environ, "PORT": str(NEXT_PORT), "HOSTNAME": "127.0.0.1",
               "NODE_ENV": "production"}
        self.next = subprocess.Popen(["node", "server.js"], cwd="/app/web", env=env,
                                     start_new_session=True)

    def warm_backend(self) -> None:
        env = {**os.environ, "SOLE_WRITER": "1"}
        self.backend = subprocess.Popen(
            [sys.executable, "/app/backend_boot.py"], cwd="/app", env=env,
            stdin=subprocess.PIPE, text=True, start_new_session=True)

    def restore(self) -> None:
        db_dir = os.environ.get("DB_DIR", "/app/db")
        os.makedirs(db_dir, exist_ok=True)
        ps = [subprocess.Popen(["litestream", "restore", "-config", "/etc/litestream.yml",
                                "-if-db-not-exists", "-if-replica-exists",
                                os.path.join(db_dir, db)]) for db in DBS]
        for p in ps:
            if p.wait() != 0:
                raise RuntimeError(f"litestream restore 실패 (code={p.returncode})")

    def replicate(self) -> None:
        self.litestream = subprocess.Popen(
            ["litestream", "replicate", "-config", "/etc/litestream.yml"],
            start_new_session=True)

    def go(self) -> None:
        if self.backend is None or self.backend.poll() is not None:
            self.warm_backend()
        self.backend.stdin.write("go\n")
        self.backend.stdin.flush()

    def wait_ready(self, timeout: float = 120) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for p, name in ((self.backend, "백엔드"), (self.next, "Next")):
                if p is not None and p.poll() is not None:
                    raise RuntimeError(f"{name}가 뜨다 죽었다 (code={p.returncode})")
            try:
                with _rq.urlopen(BACKEND_HEALTH, timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:                                  # noqa: BLE001
                pass
            time.sleep(0.2)
        raise RuntimeError("백엔드가 제시간에 뜨지 않았다")

    def dead(self) -> str | None:
        for p, name in ((self.backend, "백엔드"), (self.next, "Next"),
                        (self.litestream, "Litestream")):
            if p is not None and p.poll() is not None:
                return f"{name} (code={p.returncode})"
        return None

    @staticmethod
    def _stop(p: subprocess.Popen | None, hard: bool, grace: float = STOP_GRACE) -> None:
        if p is None or p.poll() is not None:
            return
        try:
            os.killpg(p.pid, signal.SIGKILL if hard else signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            p.wait(timeout=None if hard else grace)
        except subprocess.TimeoutExpired:
            log("정상 종료가 늦다 — 강제 종료")
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()

    def stop_writers(self, hard: bool) -> None:
        """쓰는 쪽을 멈춘다. **순서가 중요하다**: 백엔드가 멈춰 WAL 이 다 적힌 뒤에
        Litestream 이 마지막으로 올린다. 강제(hard)면 올리지 않는다 — 임대를 잃은
        인스턴스가 더 올리면 새 주인의 세대를 덮는다."""
        self._stop(self.backend, hard)
        self.backend = None
        self._stop(self.litestream, hard, grace=30)
        self.litestream = None

    def stop_all(self, hard: bool) -> None:
        self.stop_writers(hard)
        self._stop(self.next, hard)


def expect_lease_soon() -> bool:
    """곧 임대를 받을 수 있어 보이는가 — 그러면 앞문을 먼저 연다.

    같은 리비전의 멀쩡한 주인이 있으면 열지 않는다: 잠깐 한도를 넘어 뜬
    복제본이 문을 열면 Cloud Run 이 거기로 요청을 보내고, 그 요청은 주인이
    놓을 때까지 붙잡혀 있게 된다.
    """
    try:
        doc, _ = read()
    except Exception:                                          # noqa: BLE001
        return False
    if doc is None:
        return True
    mine, theirs = rev_num(REVISION), rev_num(doc.get("revision"))
    if doc.get("state") == "released":
        return mine >= theirs
    return mine > theirs


def serve(gen: int, stop: dict, procs: Procs, front: Front):
    """임대를 쥐고 앱을 돌린다. "handoff" 또는 끝낼 종료 코드."""
    procs.restore()
    procs.replicate()
    procs.go()
    front.open()
    procs.wait_ready()
    front.set("ready")
    log("준비됨 — 붙잡아 둔 요청을 흘려보낸다")
    last_ok = time.monotonic()
    next_beat = time.monotonic() + HEARTBEAT
    next_look = time.monotonic() + LOOK_EVERY
    while True:
        if stop["sig"]:
            log("SIGTERM — 정상 종료")
            front.set("standby")
            procs.stop_all(hard=False)
            release(gen)
            return 0
        if (why := procs.dead()) is not None:
            log(f"자식이 끝났다: {why} — 내려간다")
            front.set("standby")
            procs.stop_all(hard=False)
            release(gen)
            return 1
        if time.monotonic() - last_ok > SELF_FENCE:
            log(f"{SELF_FENCE:.0f}초 동안 임대를 갱신하지 못했다 — 스스로 멈춘다")
            front.set("standby")
            procs.stop_all(hard=True)
            return 4
        # 쓰기(박동)는 HEARTBEAT 마다, **보기는 1초마다**. 넘겨 달라는 요청을
        # 박동 때만 보면 최대 HEARTBEAT 초 늦게 알아챈다(DAY 27 실측 8초) —
        # 그동안 새 인스턴스의 앞문에 요청이 붙잡혀 있다.
        if time.monotonic() >= next_look and time.monotonic() < next_beat:
            next_look = time.monotonic() + LOOK_EVERY
            try:
                _doc_now, cur_now = read()
                if cur_now != gen:
                    next_beat = time.monotonic()        # 바로 아래에서 처리한다
            except Exception:                            # noqa: BLE001
                pass
        if time.monotonic() >= next_beat:
            next_beat = time.monotonic() + HEARTBEAT
            try:
                new = write(_doc("held"), gen)
                if new is not None:
                    gen, last_ok = new, time.monotonic()
                else:
                    doc, cur = read()
                    if doc and doc.get("holder") == ME and doc.get("state") == "handoff":
                        by = doc.get("by_revision")
                        if rev_num(by) <= rev_num(REVISION):
                            # 요청하는 쪽만 규칙을 지키면 안 된다 — 옛 코드의 옛
                            # 리비전이 요청해 온 것을 받아 줬다가 40초 동안 아무도
                            # 서비스하지 않았다(DAY 27 실측). 쥐는 쪽도 거절한다.
                            again = write(_doc("held"), cur)
                            if again is not None:
                                gen, last_ok = again, time.monotonic()
                                log(f"옛 리비전({by})의 요청 — 거절")
                                continue
                        log(f"넘겨 달라는 요청 — {by}")
                        front.set("standby")
                        procs.stop_writers(hard=False)
                        write(_doc("released", for_revision=by, **{"for": doc.get("by")}), cur)
                        log("넘겨줌 — 대기 모드")
                        return "handoff"
                    log(f"임대를 잃었다 — 지금 주인 {doc and doc.get('holder')}. 즉시 멈춘다")
                    front.set("standby")
                    procs.stop_all(hard=True)
                    return 5
            except Exception as e:      # noqa: BLE001 — 일시 오류는 SELF_FENCE 가 판단한다
                log(f"갱신 실패: {e}")
        time.sleep(0.5)


def main() -> int:
    global ME
    if not BUCKET:
        log("STATE_BUCKET 이 없다 — 임대 없이 앱만 띄운다 (상태가 보존되지 않는다)")
        os.execv("/app/start.sh", ["/app/start.sh"])
    ME = f"{_meta('instance/id')[-12:]}@{REVISION}"

    stop = {"sig": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(sig=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(sig=True))

    procs, front = Procs(), Front()
    procs.start_next()
    procs.warm_backend()
    if expect_lease_soon():
        front.open()                 # 붙잡기 모드 — Cloud Run 이 이리로 넘긴다

    gen = acquire(stop, may_ask=front.first_request.is_set)
    try:
        while gen is not None:
            rc = serve(gen, stop, procs, front)
            if rc != "handoff":
                return rc
            procs.warm_backend()     # 다시 받게 되면 곧장 쓸 수 있게
            gen = acquire(stop, give_up=False)
            if gen is not None:
                log("대기 모드에서 다시 받음 — 앱을 띄운다")
                front.set("hold")
        return 0
    finally:
        procs.stop_all(hard=False)


if __name__ == "__main__":
    sys.exit(main())
