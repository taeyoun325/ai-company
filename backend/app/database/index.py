"""프로젝트 색인 (지시서 §12 · §5).

## 색인은 파일 **위에** 올린다

산출물과 메타데이터의 진실은 `projects/<slug>/` 안의 파일이다. 이 색인은
그것을 빠르게 찾기 위한 사본일 뿐이다. 순서를 반대로 하면 — DB 를 진실로
두고 파일을 부산물로 두면 — 둘이 어긋나는 날 어느 쪽이 맞는지 알 수 없다.

그래서 이렇게 한다:

  - 색인이 없거나 깨지면 **디스크에서 다시 만든다** (`rebuild`)
  - 색인 쓰기가 실패해도 실행은 계속된다. 색인은 검색 편의지 전제가 아니다
  - 삭제는 파일 → 색인 순서. 반대로 하면 색인에 없는 유령 폴더가 남는다

## 왜 SQLite 이고, 왜 ORM 이 없나

개발은 SQLite, 운영은 PostgreSQL(§5). ORM 을 얹으면 그 추상화가 두
데이터베이스의 차이를 덮어주는 대신 **새로운 차이**를 만든다. 여기서
필요한 것은 테이블 하나와 질의 네 개뿐이라, 표준 SQL 을 그대로 쓴다.
옮길 때 고칠 곳은 `_connect()` 와 자리표시자(`?` → `%s`) 둘뿐이다.

## 스레드

SQLite 연결은 만든 스레드에서만 쓸 수 있다. 오케스트레이터는 실행마다
스레드를 만들고 FastAPI 도 스레드풀을 쓰므로, **스레드마다 연결을 따로**
둔다. 하나를 공유하면 "SQLite objects created in a thread…" 로 죽는다.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from app import config
from app.database import store

_local = threading.local()
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    slug          TEXT PRIMARY KEY,
    owner         TEXT NOT NULL DEFAULT 'local',
    name          TEXT NOT NULL DEFAULT '',
    requirement   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'running',
    mode          TEXT NOT NULL DEFAULT 'auto',
    score         INTEGER NOT NULL DEFAULT 0,
    cost          REAL NOT NULL DEFAULT 0,
    credits       REAL NOT NULL DEFAULT 0,
    mock          INTEGER NOT NULL DEFAULT 0,
    file_count    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL DEFAULT 0,
    updated_at    REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_projects_owner_created
    ON projects (owner, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_projects_status ON projects (status);
"""


# 죽은 행을 걷어내며 다시 읽는 횟수 상한. 색인이 통째로 죽어 있어도
# 요청 하나가 영원히 돌면 안 된다.
SWEEPS = 6


def path() -> Path:
    """설정이 바뀌어도(테스트 등) 따라오도록 매번 계산한다."""
    return config.data_dir() / "ai_company.db"


def _connect() -> sqlite3.Connection:
    """PostgreSQL 로 옮길 때 고치는 곳은 여기와 자리표시자뿐이다 (§5)."""
    conn = sqlite3.connect(path(), timeout=10)
    conn.row_factory = sqlite3.Row
    # 실행 스레드가 쓰는 동안 화면이 읽는다. WAL 이 아니면 읽기가 쓰기를 막는다.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def conn() -> sqlite3.Connection:
    """이 스레드의 연결. 없으면 만들고 스키마를 보장한다."""
    c = getattr(_local, "conn", None)
    if c is not None and getattr(_local, "path", None) == str(path()):
        return c
    if c is not None:
        c.close()
    c = _connect()
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


def _row_of(meta: dict) -> tuple:
    slug = meta.get("slug", "")
    return (
        slug,
        meta.get("owner", "local"),
        meta.get("name", ""),
        meta.get("requirement", ""),
        meta.get("status", "running"),
        meta.get("mode", "auto"),
        int(meta.get("score", 0) or 0),
        float(meta.get("cost", 0) or 0),
        float(meta.get("credits", 0) or 0),
        1 if meta.get("mock") else 0,
        len(store.files_of(slug)) if slug else 0,
        float(meta.get("created_at", 0) or 0),
        time.time(),
    )


UPSERT = """
INSERT INTO projects
  (slug, owner, name, requirement, status, mode, score, cost, credits,
   mock, file_count, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(slug) DO UPDATE SET
  owner=excluded.owner, name=excluded.name, requirement=excluded.requirement,
  status=excluded.status, mode=excluded.mode, score=excluded.score,
  cost=excluded.cost, credits=excluded.credits, mock=excluded.mock,
  file_count=excluded.file_count, updated_at=excluded.updated_at
"""


def upsert(meta: dict) -> bool:
    """색인을 갱신한다. 실패해도 True/False 만 돌려주고 예외는 올리지 않는다.

    색인 쓰기가 실행을 멈추면, 검색 편의 때문에 산출물을 잃는다.
    """
    if not meta.get("slug"):
        return False
    try:
        with _lock, conn() as c:
            c.execute(UPSERT, _row_of(meta))
        return True
    except sqlite3.Error:
        return False


def remove(slug: str) -> bool:
    try:
        with _lock, conn() as c:
            c.execute("DELETE FROM projects WHERE slug = ?", (slug,))
        return True
    except sqlite3.Error:
        return False


SORTS = {
    "created": "created_at",
    "updated": "updated_at",
    "cost": "cost",
    "score": "score",
}


def search(owner: str | None = None, status: str | None = None,
           q: str | None = None, sort: str = "created", desc: bool = True,
           limit: int = 50, offset: int = 0) -> dict:
    """목록과 전체 개수를 함께 돌려준다.

    개수를 같이 주는 이유: 화면이 "다음 페이지가 있는가"를 알아야 하는데,
    한 페이지를 받아보고 판단하면 마지막 페이지에서 한 번 더 요청한다.

    정렬 키를 **화이트리스트로** 고정한다. 문자열을 그대로 SQL 에 넣으면
    그게 곧 주입 통로다 — 자리표시자로는 컬럼명을 넘길 수 없다.
    """
    col = SORTS.get(sort, "created_at")
    order = "DESC" if desc else "ASC"
    where, args = [], []
    if owner:
        where.append("owner = ?")
        args.append(owner)
    if status:
        where.append("status = ?")
        args.append(status)
    if q:
        where.append("(name LIKE ? OR requirement LIKE ? OR slug LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like]
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    take = max(1, min(limit, 200))
    skip = max(0, offset)
    # slug 로 모은다. 죽은 행을 지우면 같은 offset 이 앞으로 당겨지므로,
    # 다음 쓸기에서 **이미 담은 행이 다시 나온다.** 목록으로 모으면 그게
    # 그대로 중복이 되고, 화면에는 같은 프로젝트가 두 번 보인다.
    live: dict[str, sqlite3.Row] = {}
    total = 0

    # 색인은 **사본**이고 파일이 진실이다 (§12). 파일이 사라진 행을 그대로
    # 내보내면, 목록에는 있는데 누르면 "없는 프로젝트"가 되는 항목이 남고,
    # 사용자는 자기가 지운 것과 그 항목을 연결짓지 못한다.
    #
    # 걸러내는 것만으로는 모자라다 — 한 페이지가 통째로 죽은 행이면 빈
    # 목록이 나간다. 살아 있는 것을 채울 때까지 다시 읽되, **횟수를
    # 묶는다**: 색인이 통째로 죽어 있어도 요청 하나가 영원히 돌면 안 된다.
    for _ in range(SWEEPS):
        try:
            with _lock, conn() as c:
                total = c.execute(
                    f"SELECT COUNT(*) FROM projects {clause}", args).fetchone()[0]
                rows = c.execute(
                    f"SELECT * FROM projects {clause} "
                    f"ORDER BY {col} {order} LIMIT ? OFFSET ?",
                    [*args, take, skip]).fetchall()
        except sqlite3.Error:
            # 색인이 깨졌으면 디스크가 진실이다. 빈 화면 대신 파일에서 읽는다.
            return _from_disk(owner, status, q, limit, offset)

        stale = []
        for r in rows:
            if store.exists(r["slug"]):
                live.setdefault(r["slug"], r)
            else:
                stale.append(r["slug"])
        if stale:
            _forget(stale)
            total = max(0, total - len(stale))
        # 더 읽을 것이 없거나, 페이지를 채웠으면 끝
        if not stale or len(rows) < take or len(live) >= take:
            break

    return {"projects": [dict(r) for r in list(live.values())[:take]],
            "total": total, "limit": limit, "offset": offset,
            "source": "index"}


def _forget(slugs) -> None:
    """파일이 없어진 행을 색인에서 지운다. 실패해도 목록은 이미 걸러졌다."""
    try:
        with _lock, conn() as c:
            c.executemany("DELETE FROM projects WHERE slug = ?",
                          [(s,) for s in slugs])
    except sqlite3.Error:
        pass


def _from_disk(owner, status, q, limit, offset) -> dict:
    rows = store.list_projects(owner)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if q:
        needle = q.lower()
        rows = [r for r in rows
                if needle in (r.get("name", "") + r.get("requirement", "")
                              + r.get("slug", "")).lower()]
    return {"projects": rows[offset:offset + limit], "total": len(rows),
            "limit": limit, "offset": offset, "source": "disk"}


def get(slug: str) -> dict | None:
    try:
        with _lock, conn() as c:
            r = c.execute("SELECT * FROM projects WHERE slug = ?",
                          (slug,)).fetchone()
        return dict(r) if r else None
    except sqlite3.Error:
        return None


# ── 프로젝트 한 건이 실제로 얼마였나 (DAY 22) ──────────────────────
#
# ## 왜 이것이 중요한가
#
# 바깥 제품들에 대해 가장 많이 나오는 불평이 이것이다(docs/market.md):
# **"크레딧이 얼마인지는 알겠는데, 그게 뭘 사주는지는 모르겠다."**
#
# 우리도 같은 문제를 갖고 있다 — 요금제 화면의 "월 N건"은 추정이다.
# 다른 점은 하나, 우리는 그게 추정이라고 적었다. 그리고 우리는 호출
# 단위로 원가를 이미 집계하고 있으므로, **실제로 끝난 프로젝트들의
# 비용**을 보면 추정을 실측으로 바꿀 수 있다. 시장 전체가 못 하고 있는
# 것이고 우리에게는 데이터가 이미 있다.
#
# ## 평균이 아니라 중앙값과 p90
#
# 평균은 한 번의 사고(재작업 열 번)에 끌려간다. 사용자가 알고 싶은
# 것은 "보통 얼마"와 "나쁠 때 얼마"이지 "합계를 개수로 나눈 값"이 아니다.
#
# ## Mock 은 빼고 센다
#
# Mock 프로젝트의 원가는 0 이다. 그걸 섞으면 "프로젝트 한 건에 0원"이
# 되고, 그 숫자를 근거로 요금제를 고른 사람은 첫 달에 놀란다.
MIN_SAMPLES = 3            # 이보다 적으면 실측이라 부르지 않는다


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def project_costs(owner: str | None = None) -> dict:
    """끝난 프로젝트들의 실제 원가 분포.

    `measured` 가 False 면 **아직 셀 만큼 돌지 않았다**는 뜻이다. 화면은
    그때 추정값을 쓰고, 추정이라고 말해야 한다.
    """
    where = ["status = 'done'", "mock = 0", "cost > 0"]
    args: list = []
    if owner:
        where.append("owner = ?")
        args.append(owner)
    clause = "WHERE " + " AND ".join(where)
    try:
        with _lock, conn() as c:
            rows = c.execute(
                f"SELECT cost FROM projects {clause} "
                f"ORDER BY created_at DESC LIMIT 200", args).fetchall()
    except sqlite3.Error:
        rows = []

    costs = [float(r["cost"]) for r in rows]
    return {
        "samples": len(costs),
        "measured": len(costs) >= MIN_SAMPLES,
        "median_usd": round(_percentile(costs, 0.5), 4),
        "p90_usd": round(_percentile(costs, 0.9), 4),
        "max_usd": round(max(costs), 4) if costs else 0.0,
        "min_samples": MIN_SAMPLES,
    }


def stats(owner: str | None = None) -> dict:
    """대시보드 요약 (§12).

    합계를 파이썬에서 세지 않고 SQL 로 세는 이유: 프로젝트가 수백 개가
    되면 목록을 전부 읽어 더하는 비용이 목록 자체보다 커진다.
    """
    where, args = ("WHERE owner = ?", [owner]) if owner else ("", [])
    try:
        with _lock, conn() as c:
            r = c.execute(
                f"SELECT COUNT(*) AS n, "
                f"       COALESCE(SUM(cost), 0) AS cost, "
                f"       COALESCE(SUM(credits), 0) AS credits, "
                f"       COALESCE(AVG(NULLIF(score, 0)), 0) AS avg_score, "
                f"       SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done, "
                f"       SUM(CASE WHEN status='stopped' THEN 1 ELSE 0 END) AS stopped, "
                f"       SUM(CASE WHEN mock=1 THEN 1 ELSE 0 END) AS mock "
                f"FROM projects {where}", args).fetchone()
        return {"projects": r["n"], "cost": round(r["cost"], 4),
                "credits": round(r["credits"], 2),
                "avg_score": round(r["avg_score"], 1),
                "done": r["done"] or 0, "stopped": r["stopped"] or 0,
                "mock": r["mock"] or 0}
    except sqlite3.Error:
        rows = store.list_projects(owner)
        return {"projects": len(rows),
                "cost": round(sum(r.get("cost", 0) for r in rows), 4),
                "credits": round(sum(r.get("credits", 0) for r in rows), 2),
                "avg_score": 0.0,
                "done": sum(1 for r in rows if r.get("status") == "done"),
                "stopped": sum(1 for r in rows if r.get("status") == "stopped"),
                "mock": sum(1 for r in rows if r.get("mock"))}


def rebuild() -> int:
    """디스크를 훑어 색인을 다시 만든다. 몇 건을 넣었는지 돌려준다.

    색인이 깨졌거나, 다른 곳에서 복사해 온 `projects/` 폴더를 붙였을 때.
    **파일이 진실**이라는 규칙이 실제로 성립하려면 이 길이 있어야 한다.
    """
    rows = store.list_projects()
    with _lock, conn() as c:
        c.execute("DELETE FROM projects")
        c.executemany(UPSERT, [_row_of(m) for m in rows if m.get("slug")])
    return len(rows)


def ensure_ready() -> dict:
    """기동 시 한 번. 색인이 비어 있는데 디스크에 프로젝트가 있으면 재구축한다.

    처음 켰을 때, 혹은 DB 파일만 지워졌을 때 화면이 "프로젝트 없음"으로
    보이는 일을 막는다 — 산출물은 멀쩡히 있는데 목록만 비어 있으면
    사용자는 잃어버렸다고 생각한다.
    """
    try:
        with _lock, conn() as c:
            n = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    except sqlite3.Error:
        n = 0
    on_disk = len(store.list_projects())
    # 비었을 때만 채우면, **부분적으로** 빈 색인은 아무도 채우지 않는다.
    # 디스크에 있는데 색인에 없는 프로젝트는 목록에서 영영 사라진 것과
    # 같다 — 산출물은 멀쩡히 있는데 사용자는 잃어버렸다고 생각한다.
    # 색인은 사본이므로, 사본이 모자라면 진실에서 다시 만든다.
    if on_disk > n:
        return {"rebuilt": rebuild(), "indexed": n, "on_disk": on_disk,
                "reason": "디스크에 있는데 색인에 없음"}
    return {"rebuilt": 0, "indexed": n, "on_disk": on_disk}
