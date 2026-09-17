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
    uvicorn.run(app_main.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
