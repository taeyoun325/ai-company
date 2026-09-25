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

import calendar
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
CREATE TABLE IF NOT EXISTS spend_log (
    owner TEXT NOT NULL,
    day   TEXT NOT NULL,
    usd   REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, day)
);
"""

# 요금제를 오가며 무한히 크레딧을 받는 것을 막으려면, "이 요금제로 크레딧을
# 받은 적이 있는가"를 어딘가 적어둬야 한다 — 없으면 A→B→A→B 로 누를 때마다
# 매번 "새 요금제로 바뀌었다"로 보여서 계속 더해진다. 기존 DB 에는 이 칸이
# 없으므로 ALTER TABLE 로 얹는다 (없을 때만 — 이미 있으면 예외를 무시한다).
#
# daily_cost_usd · daily_reset_at 은 일일 사용한도(config.MAX_DAILY_COST) 를
# 위한 칸이다. `spent`(크레딧) 는 하루 단위로 리셋되지 않고 평생 누적이라
# 여기 못 쓴다 — 오늘 얼마를 썼는지는 별도로 세야 한다.
_MIGRATIONS = (
    "ALTER TABLE wallets ADD COLUMN granted_plans TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE wallets ADD COLUMN daily_cost_usd REAL NOT NULL DEFAULT 0",
    "ALTER TABLE wallets ADD COLUMN daily_reset_at REAL NOT NULL DEFAULT 0",
)


def _utc_midnight(ts: float) -> float:
    """`ts` 가 속한 UTC 날짜의 자정(그날 00:00:00)을 초로."""
    day = time.gmtime(ts)
    return float(calendar.timegm((day.tm_year, day.tm_mon, day.tm_mday,
                                  0, 0, 0, 0, 0, 0)))


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


def add_plan(owner: str, plan: str, allowance: dict[str, float]) -> float:
    """요금제를 바꾼다. 돌려주는 값은 이번 전환으로 **더 준** 크레딧.

    ## 한 기간에 받는 크레딧은 "고른 요금제 중 가장 큰 것"까지다 (DAY 26)

    DAY 22 까지는 요금제마다 **처음 고를 때 그 몫을 통째로** 더했다. 같은
    요금제를 번갈아 누르는 길은 막았지만, 스타터 → 프로 → 비즈니스를 한 번씩
    누르면 500 + 1,300 + 2,700 이 쌓였다 — 요금제를 바꿀 때마다 잔액이
    올랐다(사용자 신고). 한 달에 비즈니스 요금제 하나를 산 사람이 받을 것은
    2,700 이다.

    이제 지금까지 받은 요금제들의 몫 중 가장 큰 값(`allowance` 로 계산)을
    넘는 **차이만** 더한다:

    - 올리면(스타터 → 프로) 차이(800)만 받는다.
    - 내리거나(프로 → 스타터) 전에 받은 요금제로 돌아오면 아무것도 안 받는다.
    - 쓴 것은 그대로 둔다. 남은 잔액을 깎지도 않는다.

    `granted_plans` 가 그 기간에 고른 요금제의 기록이다. 월 갱신(결제)이
    붙으면 갱신할 때 이 기록을 비운다.
    """
    with _lock, conn() as c:
        row = c.execute(
            "SELECT granted_plans FROM wallets WHERE owner = ?",
            (owner,)).fetchone()
        already = {p for p in (row["granted_plans"] if row else "").split(",")
                   if p}
        had = max((float(allowance.get(p, 0.0)) for p in already), default=0.0)
        add = max(0.0, float(allowance.get(plan, 0.0)) - had)
        already.add(plan)
        c.execute(
            "UPDATE wallets SET plan = ?, granted = granted + ?, "
            "granted_plans = ?"
            + (", renewed_at = ?" if add > 0 else "")
            + " WHERE owner = ?",
            (plan, add, ",".join(sorted(already)),
             *((time.time(),) if add > 0 else ()), owner))
        return add


def add_spent(owner: str, credits: float) -> None:
    """차감. **읽지 않고 더한다** — 그게 이 파일이 생긴 이유다."""
    with _lock, conn() as c:
        c.execute("UPDATE wallets SET spent = spent + ? WHERE owner = ?",
                  (credits, owner))


def daily_cost(owner: str) -> float:
    """오늘(UTC) 이미 쓴 실제 원가(달러). 날짜가 바뀌었으면 0 —
    **쓰지는 않는다**, 다음 `add_daily_cost` 가 리셋과 함께 쓴다."""
    with _lock, conn() as c:
        row = c.execute(
            "SELECT daily_cost_usd, daily_reset_at FROM wallets "
            "WHERE owner = ?", (owner,)).fetchone()
    if row is None or float(row["daily_reset_at"]) < _utc_midnight(time.time()):
        return 0.0
    return float(row["daily_cost_usd"])


def add_daily_cost(owner: str, usd: float) -> float:
    """오늘 실제로 나간 돈(달러)을 더한다. 날짜가 바뀌었으면 0 부터 다시 센다.

    청구 방식(크레딧 · BYOK)과 무관하게 **실제 원가**를 더한다 — 일일
    상한은 사용자가 산 크레딧이 아니라 우리가 실제로 낸 돈을 막는
    안전장치라서다.
    """
    midnight = _utc_midnight(time.time())
    with _lock, conn() as c:
        row = c.execute(
            "SELECT daily_reset_at FROM wallets WHERE owner = ?",
            (owner,)).fetchone()
        stale = row is None or float(row["daily_reset_at"]) < midnight
        if stale:
            c.execute(
                "UPDATE wallets SET daily_cost_usd = ?, daily_reset_at = ? "
                "WHERE owner = ?", (usd, midnight, owner))
            return usd
        c.execute(
            "UPDATE wallets SET daily_cost_usd = daily_cost_usd + ? "
            "WHERE owner = ?", (usd, owner))
        row2 = c.execute(
            "SELECT daily_cost_usd FROM wallets WHERE owner = ?",
            (owner,)).fetchone()
    return float(row2["daily_cost_usd"]) if row2 else usd


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
