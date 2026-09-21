"""옮길 때 고칠 곳이 정말 그것뿐인가 (§5 · DAY 22).

## 왜 이 파일이 생겼나

README 와 STATUS 에 이렇게 적혀 있었다 — "PostgreSQL 로 옮길 때 고칠
곳은 `_connect()` 와 자리표시자 둘뿐이다." 그건 **주장이었고 아무도
확인하지 않았다.**

확인해보니 틀렸다. 지갑을 SQLite 로 옮기면서(DAY 22) `INSERT OR IGNORE`
를 썼는데, 그건 SQLite 에만 있는 문법이다. 하루 만에 주장이 깨진 것이다.

주장은 이렇게 깨진다 — 문서에 적어두고 아무도 다시 보지 않는다. 그래서
**기계가 지키게 한다.** 새 SQL 이 이식성을 깨면 여기서 걸린다.

## 여기서 막지 않는 것

연결을 만드는 곳(`_connect`)과 `PRAGMA`, `sqlite3` 모듈을 직접 쓰는 것은
**그대로 둔다.** 그게 "고칠 곳"으로 지목된 자리이고, 옮길 때 실제로
고쳐야 하는 곳이다. 이 테스트는 그 자리가 **늘어나지 않는지**를 본다.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

APP = Path(__file__).resolve().parents[1] / "app"

# SQLite 에만 있는 SQL 문법. PostgreSQL 에서는 그대로 돌지 않는다.
SQLITE_ONLY = {
    "INSERT OR IGNORE": r"INSERT\s+OR\s+IGNORE",
    "INSERT OR REPLACE": r"INSERT\s+OR\s+REPLACE",
    "AUTOINCREMENT": r"\bAUTOINCREMENT\b",
    "GROUP_CONCAT(... ,)": r"GROUP_CONCAT\s*\([^)]*,\s*'",
    "strftime('%s'": r"strftime\s*\(\s*'%s'",
}

# `sqlite3` 모듈을 직접 다루는 것이 허용된 파일. 여기가 곧 "고칠 곳"이다.
ADAPTERS = {"database/index.py", "auth/store.py", "usage/wallet_store.py"}


def _strip_prose(text: str) -> str:
    """주석과 문서 문자열을 지운다.

    "`INSERT OR IGNORE` 를 쓰지 마세요"라고 **설명하는 문장**까지 위반으로
    잡으면, 규칙을 적어두는 일이 규칙 위반이 된다.
    """
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    text = re.sub(r"'''[\s\S]*?'''", "", text)
    return "\n".join(line.split("#")[0] for line in text.splitlines())


def _sources():
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(APP).as_posix()
        if rel.startswith("legacy/"):
            continue
        yield rel, _strip_prose(p.read_text(encoding="utf-8"))


def test_no_sqlite_only_sql():
    """SQLite 에만 있는 문법을 쓰면 옮길 때 고칠 곳이 늘어난다."""
    found = []
    for rel, text in _sources():
        for name, pattern in SQLITE_ONLY.items():
            if re.search(pattern, text, re.I):
                found.append(f"{rel}: {name}")
    assert not found, (
        "SQLite 전용 문법이 쓰였다. PostgreSQL 에도 있는 표현으로 바꾸세요 "
        f"(예: ON CONFLICT ... DO NOTHING): {found}")


def test_sqlite_stays_behind_the_adapters():
    """`sqlite3` 를 직접 쓰는 파일이 늘어나면, 옮길 때 고칠 곳도 늘어난다.

    늘려야 할 이유가 있으면 이 목록에 적고 커밋 메시지에 이유를 남긴다 —
    조용히 늘어나는 것만 막는다.
    """
    users = {rel for rel, text in _sources() if "sqlite3" in text}
    assert users <= ADAPTERS, (
        f"sqlite3 을 직접 쓰는 파일이 늘었다: {sorted(users - ADAPTERS)}")


def test_placeholders_are_the_documented_difference():
    """자리표시자가 `?` 라는 사실은 문서가 말한 '고칠 곳' 중 하나다.
    실제로 그런지 본다 — 아니라면 문서가 틀린 것이다."""
    sql_files = [text for rel, text in _sources() if rel in ADAPTERS]
    assert any("?" in t for t in sql_files)
    # `%s` (psycopg 방식)가 섞여 있으면 지금 코드가 이미 깨져 있다는 뜻이다.
    for rel, text in _sources():
        if rel in ADAPTERS:
            assert "VALUES (%s" not in text, f"{rel}: 자리표시자가 섞였다"
