"""저장소 — 제작한 프로그램을 프로젝트별 폴더에 나눠 담는다.

projects/
  2026-09-05-1432-계산기/
    .meta.json        ← 요구사항, 완성도, 태스크, 비용
    calculator.py
    test_calculator.py
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

import config

META = ".meta.json"
HISTORY = ".history"


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣 ]", "", text).strip()
    s = re.sub(r"\s+", "-", s)[:28]
    return s or "project"


def new_project(requirement: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    slug = f"{stamp}-{_slug(requirement)}"
    d = config.PROJECTS / slug
    (d / "src").mkdir(parents=True, exist_ok=True)
    (d / "tests").mkdir(parents=True, exist_ok=True)
    save_meta(slug, {
        "slug": slug,
        "name": _slug(requirement),
        "requirement": requirement,
        "created_at": time.time(),
        "status": "running",
        "score": 0,
        "tasks": [],
        "usage": {},
        "cost": 0.0,
    })
    return slug


def dir_of(slug: str) -> Path:
    return config.PROJECTS / slug


def meta(slug: str) -> dict:
    p = dir_of(slug) / META
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_meta(slug: str, patch: dict) -> dict:
    d = dir_of(slug)
    d.mkdir(parents=True, exist_ok=True)
    m = meta(slug)
    m.update(patch)
    (d / META).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m


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
    if not str(target).startswith(str(root)) or not target.is_file():
        raise ValueError("잘못된 경로")
    return target.read_text(encoding="utf-8", errors="replace")


def list_projects() -> list[dict]:
    config.PROJECTS.mkdir(parents=True, exist_ok=True)
    out = []
    for d in config.PROJECTS.iterdir():
        if not d.is_dir():
            continue
        m = meta(d.name)
        if not m:
            continue
        m["file_count"] = len(files_of(d.name))
        out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", 0), reverse=True)


# ── 파일 이력 ──────────────────────────────────────────────────────
# 에이전트가 파일을 덮어쓰기 직전 내용을 남긴다. 회차별 diff의 재료.

def _hist_dir(slug: str, path: str) -> Path:
    # 경로 구분자를 파일명에 안전한 형태로 눕힌다
    flat = path.replace("\\", "/").replace("/", "__")
    return dir_of(slug) / HISTORY / flat


def snapshot_version(slug: str, path: str, content: str, note: str = "") -> int:
    """쓰기 직전 내용을 새 버전으로 남기고 버전 번호를 돌려준다."""
    d = _hist_dir(slug, path)
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("v*.txt"))) + 1
    (d / f"v{n:03d}.txt").write_text(content, encoding="utf-8")
    if note:
        (d / f"v{n:03d}.note").write_text(note, encoding="utf-8")
    return n


def versions(slug: str, path: str) -> list[dict]:
    """오래된 것부터. 마지막 항목은 항상 현재 파일이다."""
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
    """version 0 은 현재 파일."""
    if version == 0:
        return read_file(slug, path)
    f = _hist_dir(slug, path) / f"v{version:03d}.txt"
    if not f.exists():
        raise ValueError("없는 버전")
    return f.read_text(encoding="utf-8", errors="replace")


def diff(slug: str, path: str, a: int, b: int) -> list[dict]:
    """단순 통합 diff. difflib 은 표준 라이브러리라 의존성이 늘지 않는다."""
    import difflib
    old = version_text(slug, path, a).splitlines()
    new = version_text(slug, path, b).splitlines()
    rows = []
    for line in difflib.unified_diff(old, new, lineterm="", n=3):
        if line.startswith("+++") or line.startswith("---"):
            continue
        kind = ("hunk" if line.startswith("@@")
                else "add" if line.startswith("+")
                else "del" if line.startswith("-")
                else "same")
        rows.append({"kind": kind, "text": line})
    return rows
