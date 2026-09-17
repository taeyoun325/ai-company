"""비밀키 브로커 — 키에 접근하는 유일한 지점.

## 왜 필요한가

이전에는 API 키가 `os.environ`에 프로세스 수명 내내 남아 있었다.
`runner.py`가 자식 프로세스로 넘길 때 세탁하긴 했지만, 그건 **한 곳의 방어**다.
어딘가에서 `subprocess`를 세탁 없이 부르거나, 예외 트레이스백에 환경이 찍히거나,
디버거가 환경을 덤프하면 키가 그대로 드러난다.

그래서 기동 시 **환경변수에서 키를 꺼내고 지운다**(`os.environ.pop`).
이후 키는 이 모듈의 메모리에만 있고, 여기를 거쳐야만 얻을 수 있다.
`runner.py`의 세탁은 그대로 둔다 — 방어는 겹칠수록 좋다.

## 막지 못하는 것

같은 프로세스 안의 파이썬 코드는 `secrets_broker._store`를 직접 읽을 수 있다.
파이썬에 진짜 캡슐화는 없다. 이 모듈이 막는 것은 *실수로 새는 경로*이지
*악의적인 같은 프로세스 코드*가 아니다. 생성된 코드는 애초에 별도 프로세스에서
돌고 그쪽은 환경이 세탁돼 있다.
"""
import json
import os
import stat
from pathlib import Path

from app import config

# 브로커가 관리하는 키 목록. (이름, 환경변수, 사람이 읽는 이름)
KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY", "Anthropic (Claude)"),
    "gemini": ("GEMINI_API_KEY", "Google (Gemini)"),
}

STORE_PATH = config.ROOT / ".secrets.json"

_store: dict[str, str] = {}
_loaded = False


def _harvest_env() -> None:
    """환경변수에서 키를 꺼내 브로커로 옮기고, 환경에서는 지운다."""
    for name, (env_var, _) in KEYS.items():
        val = os.environ.pop(env_var, None)      # pop — 읽고 나서 지운다
        if val and val.strip():
            _store[name] = val.strip()


def _load_file() -> None:
    if not STORE_PATH.exists():
        return
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for name in KEYS:
        val = data.get(name)
        if isinstance(val, str) and val.strip():
            _store.setdefault(name, val.strip())   # 환경변수가 우선


def init() -> None:
    """기동 시 한 번. 환경변수 → 저장 파일 순으로 키를 모은다."""
    global _loaded
    if _loaded:
        return
    _harvest_env()
    _load_file()
    _loaded = True


def get(name: str) -> str | None:
    """키를 꺼낸다. 여기가 유일한 통로다."""
    init()
    return _store.get(name)


def require(name: str) -> str:
    key = get(name)
    if not key:
        label = KEYS.get(name, (None, name))[1]
        raise RuntimeError(
            f"{label} API 키가 없습니다. 설정 화면에서 등록하거나 "
            f"{KEYS[name][0]} 환경변수를 설정하세요.")
    return key


def has(name: str) -> bool:
    return bool(get(name))


def ready() -> bool:
    """실제 모델로 돌릴 수 있는 상태인가."""
    return all(has(n) for n in KEYS)


def mask(name: str) -> str | None:
    """화면에 보여줄 형태. 원문은 절대 밖으로 내보내지 않는다."""
    key = get(name)
    if not key:
        return None
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:6]}…{key[-4:]}"


def status() -> dict:
    init()
    return {name: {"label": label, "set": has(name), "masked": mask(name)}
            for name, (_env, label) in KEYS.items()}


def set_key(name: str, value: str) -> None:
    init()
    if name not in KEYS:
        raise ValueError(f"알 수 없는 키 이름: {name}")
    value = (value or "").strip()
    if value:
        _store[name] = value
    else:
        _store.pop(name, None)


def clear(name: str) -> None:
    set_key(name, "")


def persist() -> Path:
    """디스크에 저장한다. .gitignore 대상이고 소유자만 읽게 권한을 좁힌다."""
    init()
    STORE_PATH.write_text(
        json.dumps({k: v for k, v in _store.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    try:
        os.chmod(STORE_PATH, stat.S_IRUSR | stat.S_IWUSR)   # 0600
    except OSError:
        pass          # Windows에서는 의미가 제한적이다
    return STORE_PATH


def forget_stored() -> None:
    """저장 파일을 지운다. 메모리의 키는 남는다(현재 세션은 계속 동작)."""
    if STORE_PATH.exists():
        STORE_PATH.unlink()


def scrub(text: str) -> str:
    """로그·오류 메시지에서 키가 보이면 가린다. 마지막 안전망."""
    out = text
    for key in _store.values():
        if key and len(key) > 8:
            out = out.replace(key, "[REDACTED]")
    return out
