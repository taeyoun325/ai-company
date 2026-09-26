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


def acquire(stop: dict | None = None, give_up: bool = True) -> int | None:
    """임대를 받을 때까지 기다린다. 받은 세대, 또는 SIGTERM 이면 None.

    `give_up=False` 는 대기 모드(standby)에서 쓴다 — 거기서 끝내면 Cloud Run 이
    인스턴스를 다시 띄울 뿐이다.
    """
    started = time.monotonic()
    seen_gen, seen_at = -1, time.monotonic()
    asked = False
    while not (stop and stop["sig"]):
        try:
            got = _acquire_step(started if give_up else None, seen_gen, seen_at, asked)
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


def _acquire_step(started, seen_gen, seen_at, asked):
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
    free = (doc is None or doc.get("state") == "released"
            or doc.get("holder") == ME or frozen >= STALE)
    if free and not older:
        why = ("없음" if doc is None else "released" if doc.get("state") == "released"
               else f"{frozen:.0f}초 멈춤")
        new = write(_doc("held"), gen)
        if new is not None:
            log(f"받음 ({why}) gen={new}")
            return "got", new
        return "wait", (seen_gen, seen_at, asked)      # 누가 먼저 바꿨다 — 다시 본다
    newer = mine > theirs
    if newer and doc.get("state") != "handoff" and not asked:
        if write({**doc, "state": "handoff", "by": ME, "by_revision": REVISION}, gen) is not None:
            log(f"넘겨 달라고 요청 — 주인 {doc.get('revision')}")
            return "wait", (seen_gen, seen_at, True)
        return "wait", (seen_gen, seen_at, asked)
    if not newer and started is not None and time.monotonic() - started > GIVE_UP:
        log(f"주인({doc.get('revision')})보다 새 리비전이 아니다 — 이 인스턴스는 내려간다")
        sys.exit(3)
    time.sleep(2)
    return "wait", (seen_gen, seen_at, asked)


def release(gen: int) -> None:
    try:
        doc, cur = read()
        if doc and doc.get("holder") == ME:
            if write(_doc("released"), cur) is not None:
                log("내려놓음")
    except Exception as e:              # noqa: BLE001 — 못 놓으면 STALE 뒤에 넘어간다
        log(f"내려놓기 실패 (STALE 뒤 넘어감): {e}")


# ── 앱 ──────────────────────────────────────────────────────────────
def start_app() -> subprocess.Popen:
    return subprocess.Popen(["/app/start.sh"], start_new_session=True)


def stop_app(app: subprocess.Popen, hard: bool) -> None:
    if app.poll() is not None:
        return
    try:
        os.killpg(app.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except ProcessLookupError:
        return
    if hard:
        app.wait()
        return
    try:
        app.wait(timeout=STOP_GRACE)
    except subprocess.TimeoutExpired:
        log("정상 종료가 늦다 — 강제 종료")
        os.killpg(app.pid, signal.SIGKILL)
        app.wait()


def standby_server():
    """넘겨준 뒤에는 **끝내지 않고** 남는다 (DAY 27).

    끝내면 Cloud Run 이 이 (옛) 리비전 인스턴스를 다시 띄운다. 생존 검사
    (/api/deploy)에는 200 을 줘서 재시작을 부르지 않고, 나머지 요청에는 503
    을 준다. 그동안 임대를 다시 볼 수 있으면(`acquire(give_up=False)`) 다시
    받아 앱을 띄운다 — 옛 리비전은 규칙상 새 리비전의 임대를 못 받는다.
    """
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def _reply(self):
            ok = self.path.split("?")[0] == "/api/deploy"
            self.send_response(200 if ok else 503)
            self.send_header("Retry-After", "2")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"standby": true}')
        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _reply

        def log_message(self, *_):
            pass

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def hold(gen: int, stop: dict):
    """앱을 띄우고 임대를 쥔다. "handoff" 또는 끝낼 종료 코드."""
    app = start_app()
    last_ok = time.monotonic()
    next_beat = time.monotonic() + HEARTBEAT
    while True:
        if stop["sig"]:
            log("SIGTERM — 정상 종료")
            stop_app(app, hard=False)
            release(gen)
            return 0
        if app.poll() is not None:
            log(f"앱이 끝났다 (code={app.returncode})")
            release(gen)
            return app.returncode or 1
        if time.monotonic() - last_ok > SELF_FENCE:
            log(f"{SELF_FENCE:.0f}초 동안 임대를 갱신하지 못했다 — 스스로 멈춘다")
            stop_app(app, hard=True)
            return 4
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
                        stop_app(app, hard=False)
                        write(_doc("released"), cur)
                        log("넘겨줌 — 대기 모드")
                        return "handoff"
                    log(f"임대를 잃었다 — 지금 주인 {doc and doc.get('holder')}. 즉시 멈춘다")
                    stop_app(app, hard=True)
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

    gen = acquire(stop)
    while gen is not None:
        rc = hold(gen, stop)
        if rc != "handoff":
            return rc
        srv = standby_server()
        gen = acquire(stop, give_up=False)
        srv.shutdown()
        srv.server_close()
        if gen is not None:
            log("대기 모드에서 다시 받음 — 앱을 띄운다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
