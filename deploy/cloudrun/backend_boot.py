"""백엔드를 **미리 데워 두고** 신호를 기다린다 (DAY 27).

supervisor.py 가 임대를 받기 전에 띄운다. 무거운 웹 라이브러리(FastAPI ·
pydantic · uvicorn)는 상태를 만지지 않으므로 먼저 불러 둔다. 우리 코드
(`app.main`)는 불러오는 순간 색인을 확인하고 끊긴 실행을 정리한다 — 그건
**임대를 받고 DB 를 되살린 뒤에만** 해야 한다. 그래서 stdin 의 "go" 를 기다린다.

인계 동안 요청은 앞문에 붙잡혀 있으므로, 여기서 줄인 시간이 곧 그 요청들의
지연에서 빠진다.

## 모델 SDK 는 데우지 않는다 (2026-10-09)

예전에는 anthropic · openai · google.genai 까지 여기서 불렀다. 그런데 **이 데우기가
기동의 제일 긴 줄**이었다(실측: 데워 둠 9.8초 — DB 복원은 2.5초에 끝나고 그 뒤로
7초를 기다렸다). 세 SDK 가 그 대부분이다(로컬 실측 3.3초 / 웹 라이브러리 1초).
키 없이 도는 Mock 에서는 셋 다 쓰지 않고, 우리 코드도 이제 처음 부를 때 부른다.
그래서 기동 줄에서 빼고, 실제 키로 도는 자세면 **서버가 뜬 뒤 뒤에서** 부른다 —
첫 모델 호출이 그만큼 늦지 않게.
"""
import os
import sys
import threading
import time

t0 = time.monotonic()
for mod in ("fastapi", "starlette", "pydantic", "uvicorn", "anyio", "httpx", "multipart"):
    try:
        __import__(mod)
    except Exception:                                          # noqa: BLE001
        pass                    # 없어도 된다 — app.main 이 부를 때 다시 부딪힌다
print(f"[boot] 데워 둠 {time.monotonic() - t0:.1f}s — 신호를 기다린다", flush=True)

if sys.stdin.readline().strip() != "go":
    sys.exit(0)

import uvicorn  # noqa: E402


def _warm_sdks() -> None:
    """실제 키로 도는 자세일 때만, 서버가 뜬 뒤 뒤에서 SDK 를 불러 둔다."""
    time.sleep(3)
    t = time.monotonic()
    for mod in ("anthropic", "openai", "google.genai"):
        try:
            __import__(mod)
        except Exception:                                      # noqa: BLE001
            pass
    print(f"[boot] 모델 SDK 뒤에서 데움 {time.monotonic() - t:.1f}s", flush=True)


if os.getenv("PROVIDER_MODE", "auto").strip().lower() != "mock":
    threading.Thread(target=_warm_sdks, name="warm-sdks", daemon=True).start()

print("[boot] 시작", flush=True)
uvicorn.run("app.main:app", app_dir="/app/backend", host="127.0.0.1", port=8000,
            timeout_keep_alive=75, proxy_headers=True, forwarded_allow_ips="127.0.0.1",
            # 인계 때 옛 인스턴스가 붙든 요청을 오래 기다리면 그만큼 새 인스턴스의
            # 붙잡힌 요청이 늦어진다. SSE 는 끊겨도 브라우저가 이어 붙는다.
            timeout_graceful_shutdown=3)
