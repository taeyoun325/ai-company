"""고객이 가져온 키 (BYOK — Bring Your Own Key, DAY 19).

## 왜 따로 두는가

`secrets_broker` 가 다루는 키는 **운영자의 키**다. 하나뿐이고, 프로세스
메모리에 있고, 모든 요청이 같은 것을 쓴다. 고객의 키는 전제가 다르다 —
테넌트마다 다르고, 우리가 아니라 **고객이 요금을 낸다**.

이 둘을 한 저장소에 섞으면 언젠가 반드시 이 사고가 난다: 고객 A 의 키로
고객 B 의 실행이 돌아간다. 저장소를 나누는 것이 그 사고를 구조적으로
막는 가장 싼 방법이다.

## 우리 키로 새지 않는다

BYOK 요금제인데 고객 키가 없으면 **실행을 거부한다.** 운영자 키로
조용히 대신 부르면, 할인 요금제를 판 자리에서 우리가 모델 값을 낸다.
그 분기는 `app/tenant.py` 한 곳에 있다.

## 디스크에서는 암호화한다

고객의 키를 평문으로 두면 백업·스냅샷·디스크 교체가 전부 유출 경로가
된다. AES-GCM 으로 봉하고, 연관 데이터에 `owner:provider` 를 넣어
**암호문을 다른 테넌트·다른 제공자 자리로 옮겨 붙이지 못하게** 한다.

## 막지 못하는 것

KEK 가 같은 서버에 있으면(=`BYOK_SECRET` 없이 파일 KEK 를 쓰면) 서버를
통째로 가져간 사람은 키도 가져간다. 이건 암호로 막을 수 있는 문제가
아니다 — 운영자가 `BYOK_SECRET` 을 프로세스 환경으로만 넣어야 하고,
그렇게 했는지는 `status()` 가 말한다. 감추지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import threading
from pathlib import Path

from app import config

# BYOK 로 받을 수 있는 키. secrets_broker.KEYS 와 같은 이름을 쓴다 —
# 이름이 어긋나면 "고객이 넣은 키가 어느 제공자인가"가 두 군데에서
# 다르게 해석된다.
PROVIDERS = ("anthropic", "gemini", "openai")

_lock = threading.RLock()
_cache: dict[str, dict[str, str]] | None = None


def store_path() -> Path:
    return config.data_dir() / ".byok.json"


def kek_path() -> Path:
    return config.data_dir() / ".byok_kek"


# ── 키 암호화 ───────────────────────────────────────────────────────
def _kek() -> bytes:
    """암호화 키. 환경변수가 있으면 그것에서, 없으면 파일에서.

    파일 KEK 를 자동 생성하는 이유: 없으면 BYOK 가 로컬 개발에서 아예
    안 돌고, 그러면 아무도 이 경로를 테스트하지 않는다. 대신 **파일을
    쓰고 있다는 사실을 status() 가 그대로 내보낸다.**
    """
    env = os.getenv("BYOK_SECRET", "").strip()
    if env:
        return hashlib.scrypt(env.encode(), salt=b"ai-company/byok",
                              n=2 ** 14, r=8, p=1, dklen=32)
    path = kek_path()
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)      # 0600
        except OSError:
            pass                      # Windows 에서는 의미가 제한적이다
    return path.read_bytes()[:32]


def kek_from_env() -> bool:
    return bool(os.getenv("BYOK_SECRET", "").strip())


def _aad(owner: str, provider: str) -> bytes:
    return f"{owner}:{provider}".encode()


def _seal(owner: str, provider: str, value: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_kek()).encrypt(nonce, value.encode(), _aad(owner, provider))
    return base64.b64encode(nonce + ct).decode()


def _open(owner: str, provider: str, blob: str) -> str | None:
    """복호화. 실패하면 None — 예외로 올리지 않는다.

    KEK 가 바뀌었거나 파일이 손상되면 복호화는 실패한다. 그때 예외가
    위로 올라가면 설정 화면 전체가 죽어서 사용자는 키를 **다시 넣을
    수도 없다.** 못 읽는 키는 없는 키로 취급하고, 화면이 다시 넣으라고
    말할 수 있게 둔다.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw = base64.b64decode(blob)
        return AESGCM(_kek()).decrypt(raw[:12], raw[12:],
                                      _aad(owner, provider)).decode()
    except Exception:                                          # noqa: BLE001
        return None


# ── 저장소 ──────────────────────────────────────────────────────────
def _oid(owner: str) -> str:
    """파일 안에서 테넌트를 가리키는 이름. 이메일을 그대로 적지 않는다."""
    return hashlib.sha256(owner.encode()).hexdigest()[:32]


def _load() -> dict[str, dict[str, str]]:
    global _cache
    if _cache is None:
        try:
            data = json.loads(store_path().read_text(encoding="utf-8"))
            _cache = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def _save() -> None:
    path = store_path()
    path.write_text(json.dumps(_load(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)            # 0600
    except OSError:
        pass


def set_key(owner: str, provider: str, value: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"알 수 없는 제공자: {provider}")
    value = (value or "").strip()
    with _lock:
        row = _load().setdefault(_oid(owner), {})
        if value:
            row[provider] = _seal(owner, provider, value)
        else:
            row.pop(provider, None)
        _save()


def clear(owner: str, provider: str | None = None) -> None:
    with _lock:
        if provider is None:
            _load().pop(_oid(owner), None)
        else:
            _load().get(_oid(owner), {}).pop(provider, None)
        _save()


def keys_of(owner: str) -> dict[str, str]:
    """이 테넌트의 평문 키. 호출자는 이걸 로그에 찍지 않는다."""
    with _lock:
        row = _load().get(_oid(owner), {})
        out = {}
        for provider, blob in row.items():
            val = _open(owner, provider, blob)
            if val:
                out[provider] = val
        return out


def has(owner: str, provider: str) -> bool:
    return provider in keys_of(owner)


def ready(owner: str) -> bool:
    """실제로 돌릴 수 있는가.

    교차검증(§8)이 이 제품의 핵심이므로 **구현자와 검증자가 서로 다른
    회사**여야 한다. 그래서 키 하나로는 부족하다 — `secrets_broker.REQUIRED`
    와 같은 기준을 쓴다. 기준이 갈라지면 "우리 키로는 되는데 내 키로는
    안 되는" 설명 불가능한 차이가 생긴다.
    """
    from app import secrets_broker
    have = keys_of(owner)
    return all(n in have for n in secrets_broker.REQUIRED)


def missing(owner: str) -> list[str]:
    from app import secrets_broker
    have = keys_of(owner)
    return [n for n in secrets_broker.REQUIRED if n not in have]


def mask(value: str) -> str:
    return "•" * len(value) if len(value) <= 10 else f"{value[:6]}…{value[-4:]}"


def status(owner: str) -> dict:
    """설정 화면에 내려보낼 현황. 원문은 절대 나가지 않는다."""
    have = keys_of(owner)
    return {
        "keys": {n: {"set": n in have,
                     "masked": mask(have[n]) if n in have else None}
                 for n in PROVIDERS},
        "ready": ready(owner),
        "missing": missing(owner),
        # 운영자가 KEK 를 환경에 넣었는가. False 면 서버 디스크를 가져간
        # 사람이 고객 키도 가져간다 — 화면이 그 사실을 말해야 한다.
        "kek_from_env": kek_from_env(),
    }


def reset() -> None:
    """테스트용. 메모리 캐시를 비운다."""
    global _cache
    with _lock:
        _cache = None
