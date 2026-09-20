"""계정 · 로그인 수단 · 세션 저장소 (DAY 15).

## 왜 색인 DB 와 파일을 나누나

`database/index.py` 의 색인은 **지워도 되는 것**이다 — 파일이 진실이고,
깨지면 디스크에서 다시 만든다(§12). 계정은 정반대다. **지우면 복구할
방법이 없다.** 둘을 한 파일에 두면 "지워도 되는 파일"과 "지우면 안 되는
파일"이 같은 파일이 된다. 언젠가 누군가 색인을 고치려고 DB 를 지운다.

그래서 `ai_company_auth.db` 를 따로 둔다.

## 왜 테이블이 셋인가

    users        사람 한 명
    identities   그 사람이 로그인하는 수단 (email · 나중에 google)
    sessions     지금 로그인해 있는 브라우저

`identities` 를 users 에서 분리한 이유가 이번 결정의 핵심이다. 지금은
이메일/비밀번호만 만들지만, 구글 로그인을 나중에 끼울 때 **테이블을
바꾸지 않아도 되게** 하려는 것이다. 같은 사람이 이메일로도 구글로도
들어올 수 있고, 둘 다 같은 `user_id` 를 가리킨다.

비밀번호를 users 에 직접 넣었다면, 구글을 붙이는 날 "비밀번호가 없는
사용자"를 위해 컬럼을 NULL 허용으로 바꾸고 기존 행을 이전해야 한다.
그 이전은 데이터가 쌓인 뒤에 하게 되므로 항상 위험하다.

## 세션 토큰을 그대로 저장하지 않는다

DB 가 새면 저장된 토큰이 곧 **남의 로그인 상태**다. 비밀번호를 해시해서
저장하는 것과 같은 이유로, 토큰도 해시해서 저장한다. 토큰은 무작위
32바이트라 사전 공격이 불가능하므로 scrypt 까지는 필요 없고 SHA-256 이면
충분하다.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app import config

_local = threading.local()
_lock = threading.RLock()

# 세션 수명. 짧으면 자주 로그인하고, 길면 훔친 토큰이 오래 산다.
SESSION_TTL = 60 * 60 * 24 * 14        # 14일
TOKEN_BYTES = 32

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    email        TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL,
    disabled     INTEGER NOT NULL DEFAULT 0
);

-- 한 사람이 여러 방법으로 로그인할 수 있다. 구글을 붙일 때 이 표에
-- (provider='google', subject=<구글이 주는 고유 id>) 한 줄이 추가될 뿐,
-- users 는 건드리지 않는다.
CREATE TABLE IF NOT EXISTS identities (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider      TEXT NOT NULL,          -- 'email' | 'google' | ...
    subject       TEXT NOT NULL,          -- 이메일 주소 또는 제공자의 고유 id
    password_hash TEXT,                   -- provider='email' 일 때만
    created_at    REAL NOT NULL,
    UNIQUE (provider, subject)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    user_agent TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_sessions_expiry ON sessions (expires_at);
CREATE INDEX IF NOT EXISTS ix_identities_user ON identities (user_id);
"""


def path() -> Path:
    """설정이 바뀌어도(테스트 등) 따라오도록 매번 계산한다."""
    return Path(config.ROOT / "ai_company_auth.db")


def conn() -> sqlite3.Connection:
    """이 스레드의 연결. SQLite 연결은 만든 스레드에서만 쓸 수 있다."""
    c = getattr(_local, "conn", None)
    if c is not None and getattr(_local, "path", None) == str(path()):
        return c
    if c is not None:
        c.close()
    c = sqlite3.connect(path(), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")     # ON DELETE CASCADE 가 실제로 돌게
    with c:
        c.executescript(SCHEMA)
    _local.conn = c
    _local.path = str(path())
    return c


def close() -> None:
    c = getattr(_local, "conn", None)
    if c is not None:
        c.close()
    _local.conn = None
    _local.path = None


# ── 값 ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    created_at: float
    disabled: bool = False

    def public(self) -> dict:
        """화면에 내려보낼 형태. 여기에 비밀번호 관련 필드를 절대 넣지 않는다."""
        return {"id": self.id, "email": self.email,
                "display_name": self.display_name, "created_at": self.created_at}


def _user_of(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(id=row["id"], email=row["email"],
                display_name=row["display_name"], created_at=row["created_at"],
                disabled=bool(row["disabled"]))


def normalize_email(email: str) -> str:
    """대소문자와 공백을 정리한다.

    `Taeyoun@Example.com` 으로 가입하고 `taeyoun@example.com` 으로 로그인하면
    사용자는 "비밀번호가 틀렸다"고 읽는다. 저장 시점에 한 형태로 맞춘다.
    """
    return email.strip().lower()


# ── 사용자 ──────────────────────────────────────────────────────────
def create_user(email: str, display_name: str = "") -> User:
    email = normalize_email(email)
    user = User(id=uuid.uuid4().hex, email=email,
                display_name=display_name.strip() or email.split("@")[0],
                created_at=time.time())
    with _lock, conn() as c:
        c.execute(
            "INSERT INTO users (id, email, display_name, created_at, disabled) "
            "VALUES (?, ?, ?, ?, 0)",
            (user.id, user.email, user.display_name, user.created_at))
    return user


def user_by_email(email: str) -> User | None:
    with _lock, conn() as c:
        return _user_of(c.execute("SELECT * FROM users WHERE email = ?",
                                  (normalize_email(email),)).fetchone())


def user_by_id(user_id: str) -> User | None:
    with _lock, conn() as c:
        return _user_of(c.execute("SELECT * FROM users WHERE id = ?",
                                  (user_id,)).fetchone())


def user_count() -> int:
    with _lock, conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def set_display_name(user_id: str, name: str) -> None:
    with _lock, conn() as c:
        c.execute("UPDATE users SET display_name = ? WHERE id = ?",
                  (name.strip(), user_id))


# ── 로그인 수단 ─────────────────────────────────────────────────────
def add_identity(user_id: str, provider: str, subject: str,
                 password_hash: str | None = None) -> None:
    with _lock, conn() as c:
        c.execute(
            "INSERT INTO identities (id, user_id, provider, subject, "
            "password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, provider, subject, password_hash,
             time.time()))


def identity(provider: str, subject: str) -> sqlite3.Row | None:
    with _lock, conn() as c:
        return c.execute(
            "SELECT * FROM identities WHERE provider = ? AND subject = ?",
            (provider, subject)).fetchone()


def identities_of(user_id: str) -> list[dict]:
    """이 사람이 쓰는 로그인 수단. 화면이 '구글 연결됨'을 보여줄 때 쓴다."""
    with _lock, conn() as c:
        rows = c.execute(
            "SELECT provider, subject, created_at FROM identities "
            "WHERE user_id = ? ORDER BY created_at", (user_id,)).fetchall()
    return [{"provider": r["provider"], "subject": r["subject"],
             "created_at": r["created_at"]} for r in rows]


def update_password_hash(user_id: str, password_hash: str) -> None:
    with _lock, conn() as c:
        c.execute("UPDATE identities SET password_hash = ? "
                  "WHERE user_id = ? AND provider = 'email'",
                  (password_hash, user_id))


# ── 세션 ────────────────────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_session(user_id: str, user_agent: str = "",
                ttl: float = SESSION_TTL) -> str:
    """세션을 만들고 **평문 토큰**을 돌려준다.

    평문은 여기서 딱 한 번 나가고 다시는 얻을 수 없다. 저장된 것은
    해시뿐이라, DB 가 새도 남의 로그인 상태가 되지 않는다.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = time.time()
    with _lock, conn() as c:
        c.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, "
            "expires_at, user_agent) VALUES (?, ?, ?, ?, ?)",
            (_hash_token(token), user_id, now, now + ttl, user_agent[:200]))
    return token


def session_user(token: str) -> User | None:
    """토큰으로 사용자를 찾는다. 만료됐거나 비활성 계정이면 None."""
    if not token:
        return None
    with _lock, conn() as c:
        row = c.execute(
            "SELECT s.expires_at, u.* FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_hash_token(token),)).fetchone()
    if row is None or row["expires_at"] < time.time():
        return None
    user = _user_of(row)
    # 계정을 막았는데 이미 로그인한 브라우저가 계속 돌아가면 막은 의미가 없다.
    return None if user is None or user.disabled else user


def drop_session(token: str) -> bool:
    with _lock, conn() as c:
        cur = c.execute("DELETE FROM sessions WHERE token_hash = ?",
                        (_hash_token(token),))
    return cur.rowcount > 0


def drop_all_sessions(user_id: str) -> int:
    """이 사람의 모든 브라우저에서 로그아웃. 비밀번호를 바꾸면 이것부터 한다 —
    훔쳐간 쪽이 계속 들어와 있으면 비밀번호를 바꾼 의미가 없다."""
    with _lock, conn() as c:
        cur = c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return cur.rowcount


def purge_expired() -> int:
    with _lock, conn() as c:
        cur = c.execute("DELETE FROM sessions WHERE expires_at < ?",
                        (time.time(),))
    return cur.rowcount
