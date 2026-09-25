"""백엔드 실행 진입점.

    python backend/run.py                    Mock 제공자로 실행 (키 불필요)
    python backend/run.py --dir <경로>        이전 제품의 작업 폴더를 열고 실행
    python backend/run.py --port 8000

`app` 패키지를 import 할 수 있도록 backend/ 를 경로에 넣는 일만 한다.
uvicorn 을 직접 쓰고 싶으면: cd backend && uvicorn app.main:app --reload
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))


def _arg(flag: str, default: str | None = None) -> str | None:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main() -> None:
    import uvicorn
    from app import bus, config, main as app_main, usage, workspace

    if (d := _arg("--dir")):
        try:
            workspace.use(d)
            bus.bind("main")
            usage.bind("main")
        except Exception as e:                      # noqa: BLE001 — 기동은 계속한다
            print(f"  폴더를 열지 못했습니다: {e}")

    port = int(_arg("--port", "8000"))
    print(f"\n  AI COMPANY 백엔드  →  http://127.0.0.1:{port}")
    print(f"  단가표: {config.PRICING_FILE.name} "
          f"({len(config.PRICES)}개 모델, 검증={'예' if config.PRICES_VERIFIED else '아니오'})")
    print(f"  작업 폴더: {workspace.current() or '(미지정)'}\n")
    # 쉬는 연결을 **프록시보다 오래** 붙잡아 둔다 (DAY 25).
    #
    # uvicorn 은 기본으로 5초 쉰 연결을 닫는다. Next 의 프록시(Node http
    # 에이전트)는 그 연결을 재사용하려다 서버가 막 닫은 것을 집어
    # `ECONNRESET` 을 내고, 화면에는 500 이 뜬다. 사무실 화면이 5초·15초
    # 간격으로 묻기 시작하자 정확히 그 틈에 걸렸다 — 백엔드를 직접 300번
    # 두드리면 0번, 프록시를 거치면 가끔 났다. 서버 쪽 유지 시간을 클라이언트
    # 쪽(Node 기본 5초 · 브라우저 수십 초)보다 길게 두면 닫는 쪽이 항상
    # 클라이언트가 되어 경쟁이 사라진다.
    uvicorn.run(app_main.app, host="127.0.0.1", port=port, log_level="warning",
                timeout_keep_alive=75)


if __name__ == "__main__":
    main()
