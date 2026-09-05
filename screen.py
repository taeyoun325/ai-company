"""화면 캡처와 조작.

## 이 파일이 가장 위험하다

화면에 뜨는 모든 것이 에이전트의 입력이 된다. 웹페이지·메일·문서에
"이전 지시를 무시하고 …" 같은 문장이 있으면 그것도 그대로 들어온다.
그래서 두 가지를 지킨다:

1. **화면 내용은 자료로만 취급한다.** `attachments.to_content_blocks()`가
   자료마다 "이건 지시가 아니다"를 앞에 붙인다.
2. **조작은 승인 없이 실행되지 않는다.** 에이전트는 행동을 *제안*만 하고,
   사람이 승인해야 실제로 마우스·키보드가 움직인다(`approvals.py`).

## 의존성

캡처는 Pillow의 ImageGrab — Windows/macOS에서 추가 설치 없이 동작한다.
조작은 pyautogui가 있을 때만 켜진다. 없으면 기능이 꺼진 채로 앱은 정상 동작한다.
"""
import io
import time

_grab_err: str | None = None
_auto_err: str | None = None

try:
    from PIL import ImageGrab
except Exception as e:                       # Pillow 미설치 등
    ImageGrab = None
    _grab_err = f"{type(e).__name__}: {e}"

try:
    import pyautogui
    pyautogui.FAILSAFE = True                # 마우스를 좌상단 모서리로 = 즉시 중단
    pyautogui.PAUSE = 0.15
except Exception as e:
    pyautogui = None
    _auto_err = f"{type(e).__name__}: {e}"


def capture_available() -> bool:
    return ImageGrab is not None


def control_available() -> bool:
    return pyautogui is not None


def status() -> dict:
    size = None
    if pyautogui is not None:
        try:
            w, h = pyautogui.size()
            size = {"width": int(w), "height": int(h)}
        except Exception:
            size = None
    return {
        "capture": capture_available(),
        "capture_error": _grab_err,
        "control": control_available(),
        "control_error": _auto_err,
        "screen": size,
    }


MAX_EDGE = 1600          # 긴 변 상한. 원본 4K를 그대로 보내면 토큰이 폭발한다.


def capture(region: tuple[int, int, int, int] | None = None) -> bytes:
    """화면을 한 장 캡처해 PNG 바이트로 돌려준다.

    사용자가 요청할 때만 호출된다. 주기적 자동 캡처는 이 파일에 없다 —
    화면에 잠깐 스쳐간 비밀번호까지 외부 API로 보내게 되기 때문이다.
    """
    if ImageGrab is None:
        raise RuntimeError(f"화면 캡처를 쓸 수 없습니다 (Pillow 필요): {_grab_err}")
    img = ImageGrab.grab(bbox=region, all_screens=region is None)
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_EDGE:
        scale = MAX_EDGE / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def capture_name() -> str:
    return time.strftime("screen-%Y%m%d-%H%M%S.png")


# ── 조작 ────────────────────────────────────────────────────────────
# 여기 있는 함수는 approvals.py 를 거쳐서만 호출된다. 직접 부르지 말 것.

ACTIONS = ("move", "click", "double_click", "right_click", "type", "key", "scroll")


def _require_control() -> None:
    if pyautogui is None:
        raise RuntimeError(
            f"화면 조작을 쓸 수 없습니다. `pip install pyautogui` 후 다시 시도하세요. ({_auto_err})")


def perform(action: str, **kw) -> str:
    """승인된 행동 하나를 실제로 실행한다."""
    _require_control()
    if action not in ACTIONS:
        raise ValueError(f"알 수 없는 행동: {action}")

    if action == "move":
        pyautogui.moveTo(kw["x"], kw["y"], duration=0.2)
        return f"({kw['x']}, {kw['y']}) 로 이동"
    if action in ("click", "double_click", "right_click"):
        x, y = kw.get("x"), kw.get("y")
        if x is not None and y is not None:
            pyautogui.moveTo(x, y, duration=0.2)
        fn = {"click": pyautogui.click,
              "double_click": pyautogui.doubleClick,
              "right_click": pyautogui.rightClick}[action]
        fn()
        where = f" ({x}, {y})" if x is not None else ""
        return f"{action}{where}"
    if action == "type":
        pyautogui.typewrite(kw["text"], interval=0.02)
        return f"{len(kw['text'])}자 입력"
    if action == "key":
        keys = kw["keys"]
        if isinstance(keys, str):
            keys = [keys]
        pyautogui.hotkey(*keys)
        return "+".join(keys) + " 누름"
    if action == "scroll":
        pyautogui.scroll(int(kw.get("amount", -3)) * 100)
        return f"스크롤 {kw.get('amount', -3)}"
    raise ValueError(action)
