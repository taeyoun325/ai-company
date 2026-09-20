"""가입 · 로그인 · 로그아웃 (DAY 15).

## 이 파일의 한 가지 규칙

**로그인 실패의 이유를 알려주지 않는다.** "그런 이메일 없음"과 "비밀번호
틀림"을 구분해서 답하면, 그 차이가 곧 **가입자 명단 조회 도구**가 된다.
공격자는 이메일 목록을 넣어보며 누가 이 서비스를 쓰는지 알아낸다.

그래서 둘 다 같은 문장으로 답하고, **걸리는 시간도 비슷하게** 맞춘다.
없는 계정에 대해 해싱을 건너뛰면 응답이 빨라져서 시간만으로 구분된다.

## 실패 횟수 제한

비밀번호는 결국 추측당한다. 막는 방법은 **추측 속도를 떨어뜨리는 것**뿐이다.
scrypt 가 한 번의 비용을 올리고, 여기서 횟수를 제한한다.

계정 단위와 IP 단위를 **함께** 센다:
  - 계정만 세면, 한 공격자가 이메일을 바꿔가며 무한히 시도한다
  - IP 만 세면, 한 사무실에서 여러 사람이 로그인할 때 서로를 막는다

## 첫 사용자

계정이 하나도 없을 때 첫 가입자를 막지 않는다. 다만 그 사실을
`is_first_user` 로 알려주므로, 화면이 "이 서버의 첫 계정입니다"라고
말할 수 있다 — 배포된 서버에서 낯선 사람이 그 문구를 보면 뭔가 잘못된
것이고, 그게 보이는 편이 낫다.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from app.auth import passwords, store

PROVIDER = "email"

# 실패 허용 횟수와 잠그는 시간
MAX_ATTEMPTS = 8
WINDOW = 15 * 60            # 15분 동안 센다
LOCKOUT = 15 * 60           # 넘으면 15분 잠근다

# 지나치게 엄격한 이메일 정규식은 멀쩡한 주소를 거부한다. 모양만 본다.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SAME_MESSAGE = "이메일 또는 비밀번호가 올바르지 않습니다."


class AuthError(RuntimeError):
    """로그인·가입 실패. 화면에 그대로 보여줘도 되는 문장만 담는다."""


class RateLimited(AuthError):
    def __init__(self, seconds: int):
        super().__init__(
            f"시도가 너무 많습니다. {max(1, seconds // 60)}분 뒤에 다시 하세요.")
        self.retry_after = seconds


@dataclass
class _Bucket:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


_lock = threading.RLock()
_buckets: dict[str, _Bucket] = {}


def _check_rate(key: str) -> None:
    now = time.time()
    with _lock:
        b = _buckets.get(key)
        if b is None:
            return
        if b.locked_until > now:
            raise RateLimited(int(b.locked_until - now))
        b.failures = [t for t in b.failures if now - t < WINDOW]


def _record_failure(key: str) -> None:
    now = time.time()
    with _lock:
        b = _buckets.setdefault(key, _Bucket())
        b.failures = [t for t in b.failures if now - t < WINDOW]
        b.failures.append(now)
        if len(b.failures) >= MAX_ATTEMPTS:
            b.locked_until = now + LOCKOUT
            b.failures.clear()


def _clear_failures(key: str) -> None:
    with _lock:
        _buckets.pop(key, None)


def reset_rate_limits() -> None:
    """테스트용."""
    with _lock:
        _buckets.clear()


# ── 가입 ────────────────────────────────────────────────────────────
def is_first_user() -> bool:
    return store.user_count() == 0


def sign_up(email: str, password: str, display_name: str = "") -> store.User:
    email = store.normalize_email(email)
    if not _EMAIL.match(email):
        raise AuthError("이메일 주소 형식이 아닙니다.")
    if len(email) > 254:
        raise AuthError("이메일 주소가 너무 깁니다.")

    if issues := passwords.problems(password, email):
        raise AuthError(" ".join(issues))

    # 경쟁 조건이 있다. 두 요청이 동시에 같은 이메일로 들어오면 둘 다
    # 여기를 통과할 수 있다. 그래서 DB 의 UNIQUE 제약이 마지막 방어이고,
    # 아래에서 그 실패를 잡아 같은 메시지로 바꾼다.
    if store.user_by_email(email) is not None:
        raise AuthError("이미 가입된 이메일입니다.")

    import sqlite3
    try:
        user = store.create_user(email, display_name)
        store.add_identity(user.id, PROVIDER, email,
                           passwords.hash_password(password))
    except sqlite3.IntegrityError as e:
        raise AuthError("이미 가입된 이메일입니다.") from e
    return user


# ── 로그인 ──────────────────────────────────────────────────────────
def log_in(email: str, password: str, *, ip: str = "",
           user_agent: str = "") -> tuple[store.User, str]:
    """성공하면 (사용자, 세션 토큰). 실패는 전부 같은 문장으로 올린다."""
    email = store.normalize_email(email)
    keys = [k for k in (f"email:{email}", f"ip:{ip}" if ip else "") if k]
    for k in keys:
        _check_rate(k)

    row = store.identity(PROVIDER, email)
    stored_hash = row["password_hash"] if row else None

    # 없는 계정이어도 해싱을 **거른다.** 건너뛰면 응답이 눈에 띄게 빨라져서,
    # 이메일 존재 여부가 시간만으로 새어나간다.
    ok = passwords.verify(password, stored_hash or _DUMMY_HASH)
    user = store.user_by_id(row["user_id"]) if row else None

    if not row or not ok or user is None or user.disabled:
        for k in keys:
            _record_failure(k)
        raise AuthError(SAME_MESSAGE)

    # 성공한 이 순간이 평문을 쥐고 있는 유일한 시점이다. 해시가 낡았으면
    # 지금 올린다 — 사용자는 아무것도 하지 않아도 보호 수준이 올라간다.
    if stored_hash and passwords.needs_rehash(stored_hash):
        store.update_password_hash(user.id, passwords.hash_password(password))

    for k in keys:
        _clear_failures(k)
    return user, store.new_session(user.id, user_agent)


# 존재하지 않는 계정에 쓸 가짜 해시. 검증은 반드시 실패하지만,
# 실패하기까지 실제와 같은 시간을 쓴다.
_DUMMY_HASH = passwords.hash_password("이 비밀번호로는 아무도 로그인하지 않는다")


def log_out(token: str) -> bool:
    return store.drop_session(token)


def change_password(user_id: str, current: str, new: str) -> None:
    user = store.user_by_id(user_id)
    if user is None:
        raise AuthError("계정을 찾을 수 없습니다.")
    row = store.identity(PROVIDER, user.email)
    if row is None or not passwords.verify(current, row["password_hash"] or ""):
        raise AuthError("현재 비밀번호가 올바르지 않습니다.")
    if issues := passwords.problems(new, user.email):
        raise AuthError(" ".join(issues))
    store.update_password_hash(user.id, passwords.hash_password(new))
    # 훔쳐간 쪽이 계속 들어와 있으면 비밀번호를 바꾼 의미가 없다.
    store.drop_all_sessions(user.id)


def me(token: str) -> store.User | None:
    return store.session_user(token)
