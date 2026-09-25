"""프로젝트 저장소 (지시서 §12).

projects/
  20260921-1432-계산기/
    .meta.json        ← 요구사항, 완성도, 태스크, 비용
    src/ tests/ docs/ design/
    .history/         ← 덮어쓰기 직전 내용. 회차별 diff 의 재료

## 왜 파일인가

산출물이 곧 파일이기 때문이다. 메타데이터를 DB 에 넣고 파일을 디스크에
두면 둘이 어긋나는 날이 온다. DAY 12 에 SQLite 색인을 **파일 위에** 올린다 —
색인이 깨져도 산출물은 남아 있어야 한다. 그 반대는 성립하지 않는다.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from app import config, safeio

META = ".meta.json"
HISTORY = ".history"
AREAS = ("src", "tests", "docs", "design")

# 프로젝트당 잠금 하나. 실행 스레드가 태스크마다 메타를 쓰는 동안,
# 20초 심장박동(engine.py BEAT_EVERY)이 같은 파일에 끼어들면 읽고-고치고-
# 쓰는 사이에 한쪽의 갱신이 사라진다 — 나중에 쓴 쪽이 이긴다. 잠금은
# 한 프로세스 안에서만 유효하다; 여러 인스턴스가 같은 프로젝트를 동시에
# 쓰는 경우는 여전히 이 잠금의 범위 밖이다.
_meta_locks_guard = threading.Lock()
_meta_locks: dict[str, threading.Lock] = {}


def _meta_lock(slug: str) -> threading.Lock:
    with _meta_locks_guard:
        lock = _meta_locks.get(slug)
        if lock is None:
            lock = _meta_locks[slug] = threading.Lock()
        return lock


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣 ]", "", text).strip()
    s = re.sub(r"\s+", "-", s)[:28]
    return s or "project"


def new_project(requirement: str, owner: str = "local") -> str:
    """새 프로젝트 폴더를 만들고 slug 를 돌려준다.

    ## 같은 초에 같은 요구사항이 들어오면

    slug 는 `시각-요구사항` 이라 **1초 안에 같은 문장으로 두 번 시작하면
    같은 이름**이 된다. 그러면 둘째가 첫째의 폴더에 겹쳐 쓰고, 첫째의
    메타데이터와 대화 이력이 조용히 덮인다. 사용자는 프로젝트 하나를
    잃었다는 사실조차 모른다.

    드물어 보이지만 실제로 난다 — 화면에서 버튼을 두 번 누르거나,
    같은 문장으로 다시 시작할 때. 비어 있는 이름을 찾을 때까지 뒤에
    번호를 붙인다.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{_slug(requirement)}"
    slug = base
    n = 2
    while exists(slug):
        slug = f"{base}-{n}"
        n += 1
    d = config.PROJECTS / slug
    for area in AREAS:
        (d / area).mkdir(parents=True, exist_ok=True)
    save_meta(slug, {
        "slug": slug,
        "name": _slug(requirement),
        "requirement": requirement,
        "owner": owner,
        "created_at": time.time(),
        "status": "running",
        "score": 0,
        "tasks": [],
        "usage": {},
        "cost": 0.0,
        "credits": 0.0,
        "mock": False,
    })
    return slug


def dir_of(slug: str) -> Path:
    return config.PROJECTS / slug


def exists(slug: str) -> bool:
    return (dir_of(slug) / META).exists()


def meta(slug: str) -> dict:
    p = dir_of(slug) / META
    if not p.exists():
        return {}
    # 윈도우에서는 **다른 스레드가 이름 바꾸기로 덮어쓰는 찰나**에 열면
    # PermissionError 가 난다(safeio._replace 와 같은 이유 · DAY 25). 잠깐
    # 기다렸다 다시 읽는다. 여기서 빈 딕셔너리를 돌려주면 안 된다 —
    # `save_meta` 가 그 빈 값에 패치만 얹어 **메타 전체를 지운다.**
    for attempt in range(20):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01 * (attempt + 1))
    return {}


def touched_at(slug: str) -> float:
    """이 실행이 마지막으로 움직인 시각.

    메타 파일은 단계마다 다시 쓰이므로, 그 파일의 수정 시각이 곧 "마지막
    움직임"이다. 끝난 실행에서는 끝난 시각이고, `created_at` 과 빼면
    **얼마나 걸렸는지**가 나온다 — 화면이 세 번째로 묻는 것이다.
    """
    p = dir_of(slug) / META
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def save_meta(slug: str, patch: dict) -> dict:
    """메타데이터를 파일에 쓰고 색인을 따라 갱신한다.

    **파일이 먼저다.** 색인 쓰기가 실패해도 산출물과 메타데이터는 남는다 —
    색인은 검색 편의지 진실이 아니다(§12).
    """
    d = dir_of(slug)
    d.mkdir(parents=True, exist_ok=True)
    with _meta_lock(slug):
        m = meta(slug)
        m.update(patch)
        # 원자적으로 쓴다 (app/safeio.py). 여기서 잘리면 프로젝트 하나가
        # 통째로 "없는 프로젝트"가 된다 — 산출물은 멀쩡한데 메타만 깨져서.
        safeio.write_json(d / META, m)
    _reindex(m)
    return m


def update_meta(slug: str, fn) -> dict:
    """읽고-고치고-쓰기를 **잠금 안에서 한 번에** 한다 (DAY 25).

    `save_meta` 는 최상위 키를 덮어쓴다. 목록 안의 한 칸(승인 기록 하나의
    상태)을 고치려면 목록을 읽어서 고쳐 다시 써야 하는데, 그 사이에 다른
    스레드가 같은 목록에 한 줄을 더하면 둘 중 하나가 사라진다 — 승인 버튼을
    눌렀는데 실행이 그 결정을 못 보는 사고가 된다.

    `fn(meta)` 는 잠금 안에서 불리고, 돌려준 딕셔너리가 패치로 합쳐진다.
    `fn` 안에서 `save_meta` 를 부르면 안 된다(같은 잠금을 다시 잡는다).
    """
    d = dir_of(slug)
    d.mkdir(parents=True, exist_ok=True)
    with _meta_lock(slug):
        m = meta(slug)
        patch = fn(m) or {}
        m.update(patch)
        safeio.write_json(d / META, m)
    _reindex(m)
    return m


def _reindex(m: dict) -> None:
    # 늦게 import 한다 — index 가 store 를 읽으므로 모듈 수준에서 하면 순환이다.
    try:
        from app.database import index
        index.upsert(m)
    except Exception:                      # noqa: BLE001
        pass


def files_of(slug: str) -> list[str]:
    root = dir_of(slug)
    if not root.exists():
        return []
    return sorted(
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*")
        if p.is_file() and p.name != META
        # 도구 부산물(__pycache__ 등)과 오케스트레이터 소유 설정은 산출물이 아니다
        and p.name != "pytest.ini"
        and not any(part.startswith((".", "__")) for part in p.relative_to(root).parts)
    )


def read_file(slug: str, path: str) -> str:
    root = dir_of(slug).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("잘못된 경로")
    return target.read_text(encoding="utf-8", errors="replace")


def list_projects(owner: str | None = None) -> list[dict]:
    config.PROJECTS.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(config.PROJECTS.iterdir()):
        if not d.is_dir():
            continue
        m = meta(d.name)
        if not m:
            continue
        if owner is not None and m.get("owner", "local") != owner:
            continue
        m["file_count"] = len(files_of(d.name))
        out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", 0), reverse=True)


def delete_project(slug: str) -> bool:
    """프로젝트 폴더를 통째로 지운다.

    `config.PROJECTS` 아래인지 다시 확인한다 — slug 는 사용자 입력에서
    올 수 있고, `../..` 하나면 저장소 밖을 지운다.
    """
    import shutil
    root = config.PROJECTS.resolve()
    d = dir_of(slug).resolve()
    if not d.is_relative_to(root) or d == root or not d.is_dir():
        return False
    # 파일 → 색인 순서. 반대로 하면 색인에 없는 유령 폴더가 남는다.
    shutil.rmtree(d)
    try:
        from app.database import index
        index.remove(slug)
    except Exception:                      # noqa: BLE001
        pass
    return True


# ── 파일 이력 ──────────────────────────────────────────────────────
# 직원이 파일을 덮어쓰기 직전 내용을 남긴다. 회차별 diff 의 재료.

def _hist_dir(slug: str, path: str) -> Path:
    flat = path.replace("\\", "/").replace("/", "__")
    return dir_of(slug) / HISTORY / flat


def snapshot_version(slug: str, path: str, content: str, note: str = "",
                     meta: dict | None = None) -> int:
    """덮어쓰기 직전 내용을 남긴다. **누가·몇 라운드에·왜** 를 함께 적는다.

    그 전에는 자유 문장 하나(`박도현 덮어쓰기 직전`)뿐이었다. 그러면
    "이 파일이 왜 세 번 고쳐졌나"를 사람이 문장에서 읽어내야 하고,
    기계는 아무것도 못 한다 — 정렬도 필터도 안 된다.

    구매 기준에 **감사 가능성**이 올라와 있다(docs/market.md). 파일 하나를
    짚고 그때까지의 경위를 따라갈 수 없으면, 그건 "AI 가 만들어줬다"이지
    "무엇이 어떻게 만들어졌다"가 아니다.
    """
    d = _hist_dir(slug, path)
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("v*.txt"))) + 1
    safeio.write_text(d / f"v{n:03d}.txt", content)
    if note:
        safeio.write_text(d / f"v{n:03d}.note", note)
    if meta:
        safeio.write_json(d / f"v{n:03d}.json", {**meta, "at": time.time()})
    return n


def versions(slug: str, path: str) -> list[dict]:
    """오래된 것부터. 마지막 항목(version 0)은 항상 현재 파일이다."""
    d = _hist_dir(slug, path)
    out = []
    if d.exists():
        for f in sorted(d.glob("v*.txt")):
            note = f.with_suffix(".note")
            meta_file = f.with_suffix(".json")
            row = {
                "version": int(f.stem[1:]),
                "note": note.read_text(encoding="utf-8") if note.exists() else "",
                "lines": len(f.read_text(encoding="utf-8", errors="replace").splitlines()),
                # 옛 판본에는 이것들이 없다. 없으면 빈 값이다 — 없는 것을
                # 지어내면 이력이 거짓말이 된다.
                "author": "", "round": 0, "reason": "", "at": 0.0,
            }
            if meta_file.exists():
                try:
                    row.update(json.loads(meta_file.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    pass
            out.append(row)
    try:
        cur = read_file(slug, path)
        out.append({"version": 0, "note": "", "lines": len(cur.splitlines()),
                    "author": "", "round": 0, "reason": "", "at": 0.0,
                    "current": True})
    except ValueError:
        pass
    return out


def version_text(slug: str, path: str, version: int) -> str:
    if version == 0:
        return read_file(slug, path)
    f = _hist_dir(slug, path) / f"v{version:03d}.txt"
    if not f.exists():
        raise ValueError("없는 버전")
    return f.read_text(encoding="utf-8", errors="replace")


def diff(slug: str, path: str, a: int, b: int) -> list[dict]:
    old = version_text(slug, path, a).splitlines()
    new = version_text(slug, path, b).splitlines()
    rows = []
    for line in difflib.unified_diff(old, new, lineterm="", n=3):
        if line.startswith(("+++", "---")):
            continue
        kind = ("hunk" if line.startswith("@@")
                else "add" if line.startswith("+")
                else "del" if line.startswith("-")
                else "same")
        rows.append({"kind": kind, "text": line})
    return rows
