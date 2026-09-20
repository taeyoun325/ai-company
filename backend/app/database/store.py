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
import time
from datetime import datetime
from pathlib import Path

from app import config

META = ".meta.json"
HISTORY = ".history"
AREAS = ("src", "tests", "docs", "design")


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣 ]", "", text).strip()
    s = re.sub(r"\s+", "-", s)[:28]
    return s or "project"


def new_project(requirement: str, owner: str = "local") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = f"{stamp}-{_slug(requirement)}"
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
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_meta(slug: str, patch: dict) -> dict:
    """메타데이터를 파일에 쓰고 색인을 따라 갱신한다.

    **파일이 먼저다.** 색인 쓰기가 실패해도 산출물과 메타데이터는 남는다 —
    색인은 검색 편의지 진실이 아니다(§12).
    """
    d = dir_of(slug)
    d.mkdir(parents=True, exist_ok=True)
    m = meta(slug)
    m.update(patch)
    (d / META).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
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


def snapshot_version(slug: str, path: str, content: str, note: str = "") -> int:
    d = _hist_dir(slug, path)
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("v*.txt"))) + 1
    (d / f"v{n:03d}.txt").write_text(content, encoding="utf-8")
    if note:
        (d / f"v{n:03d}.note").write_text(note, encoding="utf-8")
    return n


def versions(slug: str, path: str) -> list[dict]:
    """오래된 것부터. 마지막 항목(version 0)은 항상 현재 파일이다."""
    d = _hist_dir(slug, path)
    out = []
    if d.exists():
        for f in sorted(d.glob("v*.txt")):
            note = f.with_suffix(".note")
            out.append({
                "version": int(f.stem[1:]),
                "note": note.read_text(encoding="utf-8") if note.exists() else "",
                "lines": len(f.read_text(encoding="utf-8", errors="replace").splitlines()),
            })
    try:
        cur = read_file(slug, path)
        out.append({"version": 0, "note": "현재", "lines": len(cur.splitlines())})
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
