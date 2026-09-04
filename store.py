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
