"""지갑 저장소 (DAY 22).

## 왜 파일에서 옮겼나

지갑은 JSON 파일 하나에 통째로 있었다. 바꿀 때마다 **전부 읽고 전부
쓰는** 방식이라 두 가지가 걸렸다:

1. **두 인스턴스가 동시에 쓰면 나중 것이 이긴다.** A 가 차감하고 B 가
   자기 사본으로 덮으면 A 의 차감이 사라진다. 돈이 조용히 복구된다.
2. 한 대에서도 **같은 프로세스 안의 두 실행**이 동시에 끝나면 같은 일이
   난다. 지금은 잠금으로 막고 있지만, 잠금은 프로세스 안에서만 유효하다.

SQLite 로 옮기면 차감이 **한 줄의 UPDATE** 가 된다:

    UPDATE wallets SET spent = spent + ? WHERE owner = ?

읽고-고치고-쓰는 세 단계가 하나로 줄어드니 사이에 끼어들 틈이 없다.
프로젝트 색인이 이미 쓰는 파일에 표 하나를 더한다 — DB 를 늘리지
않는다.

## 옛 파일은 지우지 않는다

`.credits.json` 이 있으면 **한 번만** 읽어 옮기고, 파일은 그대로 둔다.
지우는 코드는 되돌릴 수 없고, 옮기다 무언가 틀렸을 때 원본이 있어야
한다. 옮긴 뒤로는 아무도 그 파일을 읽지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from app import config

_lock = threading.RLock()
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    owner      TEXT PRIMARY KEY,
    plan       TEXT NOT NULL,
    granted    REAL NOT NULL DEFAULT 0,
    spent      REAL NOT NULL DEFAULT 0,
    topped_up  REAL NOT NULL DEFAULT 0,
    byok_usd   REAL NOT NULL DEFAULT 0,
    renewed_at REAL NOT NULL DEFAULT 0
);
"""

# 요금제를 오가며 무한히 크레딧을 받는 것을 막으려면, "이 요금제로 크레딧을
# 받은 적이 있는가"를 어딘가 적어둬야 한다 — 없으면 A→B→A→B 로 누를 때마다
# 매번 "새 요금제로 바뀌었다"로 보여서 계속 더해진다. 기존 DB 에는 이 칸이
# 없으므로 ALTER TABLE 로 얹는다 (없을 때만 — 이미 있으면 예외를 무시한다).
_MIGRATIONS = (
    "ALTER TABLE wallets ADD COLUMN granted_plans TEXT NOT NULL DEFAULT ''",
)


def path() -> Path:
    """프로젝트 색인과 같은 파일. 표만 다르다."""
    return config.data_dir() / "ai_company.db"


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is not None and getattr(_local, "path", None) == str(path()):
        return c
    if c is not None:
        c.close()
    c = sqlite3.connect(path(), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    with c:
        c.executescript(SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                c.execute(stmt)
            except sqlite3.OperationalError:
                pass                      # 칸이 이미 있다
    _local.conn = c
    _local.path = str(path())
    return c


def close() -> None:
    c = getattr(_local, "conn", None)
    if c is not None:
        c.close()
    _local.conn = None
    _local.path = None


def get(owner: str) -> dict | None:
    with _lock, conn() as c:
        row = c.execute("SELECT * FROM wallets WHERE owner = ?",
                        (owner,)).fetchone()
    return dict(row) if row else None


def create(owner: str, plan: str, granted: float) -> dict:
    """없으면 만든다. 이미 있으면 그대로 둔다.

    충돌을 무시하는 이유: 두 요청이 같은 순간에 같은 지갑을 만들려 하면
    하나는 실패해야 하는데, 그 실패가 예외로 올라가면 멀쩡한 요청이
    죽는다. 이미 있으면 그게 답이다.

    `INSERT OR IGNORE` 가 아니라 `ON CONFLICT ... DO NOTHING` 을 쓴다 —
    앞의 것은 SQLite 에만 있고, 뒤의 것은 PostgreSQL 에도 있다. 옮길 때
    고칠 곳을 늘리지 않는다(§5).
    """
    with _lock, conn() as c:
        c.execute(
            "INSERT INTO wallets "
            "(owner, plan, granted, spent, topped_up, byok_usd, renewed_at, "
            "granted_plans) "
            "VALUES (?, ?, ?, 0, 0, 0, ?, ?) "
            "ON CONFLICT (owner) DO NOTHING",
            (owner, plan, granted, time.time(), plan))
    return get(owner) or {}


def add_plan(owner: str, plan: str, credits: float) -> bool:
    """요금제를 바꾼다.

    이 요금제로 크레딧을 받은 게 **처음**이면 그 몫을 더한다. 전에 이미
    받은 적이 있으면(전에 골랐다가 다른 데로 갔다가 돌아온 경우 포함)
    요금제만 바뀌고 크레딧은 다시 주지 않는다 — 두 요금제를 번갈아
    누르면 누를 때마다 크레딧이 쌓이는 길을 막는다. 이미 쓴 것은
    그대로 둔다.

    반환값은 이번 전환에서 크레딧을 실제로 줬는지.
    """
    with _lock, conn() as c:
        row = c.execute(
            "SELECT granted_plans FROM wallets WHERE owner = ?",
            (owner,)).fetchone()
        already = {p for p in (row["granted_plans"] if row else "").split(",")
                   if p}
        if plan in already:
            c.execute("UPDATE wallets SET plan = ? WHERE owner = ?",
                      (plan, owner))
            return False
        already.add(plan)
        c.execute(
            "UPDATE wallets SET plan = ?, granted = granted + ?, "
            "renewed_at = ?, granted_plans = ? WHERE owner = ?",
            (plan, credits, time.time(), ",".join(sorted(already)), owner))
        return True


def add_spent(owner: str, credits: float) -> None:
    """차감. **읽지 않고 더한다** — 그게 이 파일이 생긴 이유다."""
    with _lock, conn() as c:
        c.execute("UPDATE wallets SET spent = spent + ? WHERE owner = ?",
                  (credits, owner))


def add_topup(owner: str, credits: float) -> None:
    with _lock, conn() as c:
        c.execute("UPDATE wallets SET topped_up = topped_up + ? "
                  "WHERE owner = ?", (credits, owner))


def add_byok_usd(owner: str, usd: float) -> None:
    with _lock, conn() as c:
        c.execute("UPDATE wallets SET byok_usd = byok_usd + ? WHERE owner = ?",
                  (usd, owner))


def refund(owner: str, credits: float) -> None:
    """돌려준다. 쓴 것보다 많이 돌려주지 않는다."""
    with _lock, conn() as c:
        c.execute("UPDATE wallets SET spent = MAX(0, spent - ?) "
                  "WHERE owner = ?", (credits, owner))


def clear() -> None:
    """테스트용."""
    with _lock, conn() as c:
        c.execute("DELETE FROM wallets")


# ── 옛 파일에서 옮기기 ──────────────────────────────────────────────
_migrated = False


def migrate_from(file: Path) -> int:
    """`.credits.json` 을 한 번만 읽어 옮긴다. 파일은 지우지 않는다.

    이미 표에 있는 소유자는 건드리지 않는다 — 옮기기가 두 번 돌아도
    잔액이 두 배가 되지 않아야 한다.
    """
    global _migrated
    if _migrated:
        return 0
    _migrated = True
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(data, dict):
        return 0
    moved = 0
    for owner, row in data.items():
        if not isinstance(row, dict) or get(owner) is not None:
            continue
        plan_name = row.get("plan", "free")
        with _lock, conn() as c:
            c.execute(
                "INSERT INTO wallets "
                "(owner, plan, granted, spent, topped_up, byok_usd, renewed_at,"
                " granted_plans)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (owner) DO NOTHING",
                (owner, plan_name,
                 float(row.get("granted", 0)), float(row.get("spent", 0)),
                 float(row.get("topped_up", 0)), float(row.get("byok_usd", 0)),
                 float(row.get("renewed_at", time.time())), plan_name))
        moved += 1
    return moved


def reset_migration() -> None:
    """테스트용. 옮기기를 다시 할 수 있게 한다."""
    global _migrated
    _migrated = False
