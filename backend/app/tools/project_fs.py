"""직원별 쓰기 권한이 있는 프로젝트 파일 도구 (지시서 §8 · §18).

## 이 파일의 존재 이유

**구현자가 검증기를 고칠 수 없게 하는 것.** developer 는 `src/` 에만 쓰고
`tests/` 는 읽지도 못한다. analyst 만 `tests/` 에 쓴다. 그래서 "테스트를
통과시키려고 테스트를 고치는" 우회가 원천 차단된다.

읽기까지 막는 이유: 보면 맞춰 짜기 때문이다. 쓰기만 막는 것으로는 부족하다.

## 권한은 여기가 아니라 직원 표에 있다

허용 목록을 여기 또 적으면 두 곳이 어긋나는 날이 온다. `roles.py` 의
`writes` · `reads` 를 그대로 읽는다. 직원을 늘려도 이 파일은 안 고친다.

## 경로 탈출

`resolve()` 로 심링크까지 해석한 뒤 프로젝트 루트 안인지 본다.
`str.startswith` 로 비교하지 않는다 — `projects/calc` 와 `projects/calc-evil`
이 접두사로는 통과해버린다.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from app.agents import roles
from app import lang, safeio
from app.database import store

# 어느 구역에도 만들 수 없는 파일들. pytest 가 자동으로 읽어들이거나
# 파이썬이 기동 시 자동 import 하는 것들이라, 하나라도 허용하면
# 테스트 실행 환경 자체를 바꿔버릴 수 있다.
FORBIDDEN_NAMES = {
    "conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml",
    "setup.py", "sitecustomize.py", "usercustomize.py",
}
FORBIDDEN_SUFFIXES = {".pth"}

# 실행 하나가 스레드 하나다. 전역이면 동시 실행이 서로를 덮어쓴다.
_local = threading.local()


class Denied(ValueError):
    """권한 위반. 직원에게 그대로 돌려주면 스스로 교정한다."""


def use(slug: str) -> None:
    _local.slug = slug
    for area in store.AREAS:
        (store.dir_of(slug) / area).mkdir(parents=True, exist_ok=True)


def slug() -> str:
    cur = getattr(_local, "slug", None)
    if cur is None:
        raise RuntimeError("이 스레드에서 project_fs.use(slug)를 먼저 호출해야 합니다")
    return cur


def current() -> str | None:
    return getattr(_local, "slug", None)


def release() -> None:
    _local.slug = None


def root() -> Path:
    return store.dir_of(slug())


def _areas(employee_id: str, write: bool) -> tuple[str, ...]:
    if employee_id == "SYSTEM":
        return store.AREAS
    try:
        e = roles.get(employee_id)
    except KeyError:
        return ()
    return e.writes if write else e.reads


def _resolve(path: str, employee_id: str, write: bool) -> Path:
    r = root().resolve()
    target = (r / path).resolve()
    if not target.is_relative_to(r) or target == r:
        raise Denied(lang.t("fs.outside", path=path))

    rel = target.relative_to(r)
    top = rel.parts[0]
    if top not in store.AREAS:
        raise Denied(lang.t(
            "fs.notArea", top=top,
            allowed=", ".join(a + "/" for a in store.AREAS)))

    allowed = _areas(employee_id, write)
    if top not in allowed:
        # 직함은 `info()` 에서 가져온다 — 그 쪽이 보는 사람의 언어로 번역된
        # 값이다. `e.role` 은 표에 적힌 원문(한국어)이다.
        label = employee_id
        if roles.exists(employee_id):
            row = roles.get(employee_id).info()
            label = f"{row['name']}({row['role']})"
        raise Denied(lang.t(
            "fs.noWrite" if write else "fs.noRead", who=label, top=top,
            allowed=", ".join(a + "/" for a in allowed) or lang.t("fs.none")))

    if write and (target.name in FORBIDDEN_NAMES
                  or target.suffix in FORBIDDEN_SUFFIXES):
        raise Denied(lang.t("fs.forbiddenName", name=target.name))
    return target


def read(path: str, employee_id: str = "SYSTEM") -> str:
    p = _resolve(path, employee_id, write=False)
    if not p.exists():
        return f"(파일 없음: {path})"
    return p.read_text(encoding="utf-8", errors="replace")


# 산출물 크기 상한 (DAY 22).
#
# 여기에 상한이 하나도 없었다. 모델이 한 번에 쓰는 양은 `max_tokens` 로
# 묶여 있지만, 라운드를 돌며 같은 파일을 계속 불리면 디스크는 계속 찬다 —
# 게다가 덮어쓸 때마다 **직전 판본을 스냅숏**으로 남기므로 한 번 커진
# 파일은 판본마다 그만큼을 더 먹는다.
#
# 이걸로 "자원 고갈"이 끝나지는 않는다. 막는 것은 **직원이 쓰는 파일**이고,
# 실행된 코드가 디스크를 채우는 것은 여전히 컨테이너의 몫이다
# (docs/security.md §3).
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(1 * 1024 * 1024)))
MAX_PROJECT_BYTES = int(os.getenv("MAX_PROJECT_BYTES", str(50 * 1024 * 1024)))


def _deliverable_bytes() -> int:
    """**산출물 구역만** 센다 (src/ tests/ docs/ design/).

    메타데이터와 판본 스냅숏은 빼는 이유: 상한이 말하는 것이 "이 프로젝트가
    만든 것"이어야 사용자가 예측할 수 있기 때문이다. 스냅숏은 산출물에서
    파생되고 라운드 수로 묶여 있다.
    """
    base = root()
    total = 0
    for area in store.AREAS:
        for f in (base / area).rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:                                    # pragma: no cover
                continue
    return total


def _check_size(target: Path, content: str) -> None:
    size = len(content.encode("utf-8"))
    if size > MAX_FILE_BYTES:
        raise Denied(lang.t("fs.tooBig", kb=size // 1024,
                            max=MAX_FILE_BYTES // 1024))
    # 이미 있는 파일을 덮어쓰는 경우, 늘어나는 만큼만 센다 — 아니면 상한에
    # 닿은 프로젝트는 고칠 수조차 없다.
    existing = target.stat().st_size if target.exists() else 0
    if _deliverable_bytes() - existing + size > MAX_PROJECT_BYTES:
        raise Denied(lang.t("fs.projectFull", max=MAX_PROJECT_BYTES // 1024))


def write(path: str, content: str, employee_id: str = "SYSTEM",
          *, round: int = 0, reason: str = "") -> dict:
    """파일을 쓴다. 덮어쓰는 경우 **직전 내용과 경위**를 함께 남긴다.

    `round` 와 `reason` 을 받는 이유: 나중에 이 파일을 짚고 "몇 번째
    라운드에서, 어떤 지적을 받고 고쳤나"를 따라갈 수 있어야 한다.
    """
    p = _resolve(path, employee_id, write=True)
    _check_size(p, content)
    p.parent.mkdir(parents=True, exist_ok=True)
    before = p.read_text(encoding="utf-8", errors="replace") if p.exists() else None
    if before is not None and before != content:
        store.snapshot_version(
            slug(), path, before,
            note=lang.t("fs.beforeOverwrite", who=employee_id),
            meta={"author": employee_id, "round": round, "reason": reason})
    safeio.write_text(p, content)
    return {"path": path, "created": before is None,
            "old_lines": len(before.splitlines()) if before else 0,
            "new_lines": len(content.splitlines())}


def raw_read(path: str) -> str | None:
    """직원 권한과 무관하게 지금 이 경로의 내용을 읽는다. 없으면 `None`.

    태스크가 시작하기 **전** 상태를 스냅숏하는 데 쓴다 — 그 시점엔 아직
    아무 직원도 관여하지 않았으니 권한 검사가 의미가 없다. 반려가 쌓여
    태스크를 통째로 포기할 때, 이 값으로 되돌린다(`restore_files`).
    """
    r = root().resolve()
    target = (r / path).resolve()
    if not target.is_relative_to(r) or not target.exists():
        return None
    return target.read_text(encoding="utf-8", errors="replace")


def restore_files(baseline: dict[str, str | None]) -> list[str]:
    """`baseline` 이 가리키는 상태로 되돌린다. `None` 이면 그 파일은
    태스크가 시작하기 전엔 없었다는 뜻이라 지운다.

    검증자의 판정 없이 그냥 덮어쓴다 — 이건 직원의 작업이 아니라
    오케스트레이터가 **포기한 시도를 치우는** 행위라서 권한 검사를
    거치지 않는다(§18 자동 롤백).
    """
    r = root().resolve()
    restored: list[str] = []
    for path, content in baseline.items():
        target = (r / path).resolve()
        if not target.is_relative_to(r):
            continue
        if content is None:
            if target.exists():
                target.unlink()
                restored.append(path)
            continue
        if target.exists() and target.read_text(
                encoding="utf-8", errors="replace") == content:
            continue                 # 이미 그 상태다 — 되돌릴 것이 없다
        target.parent.mkdir(parents=True, exist_ok=True)
        safeio.write_text(target, content)
        restored.append(path)
    return restored


def listdir(employee_id: str = "SYSTEM") -> list[str]:
    allowed = _areas(employee_id, write=False)
    return [f for f in store.files_of(slug()) if f.split("/", 1)[0] in allowed]


def snapshot(employee_id: str = "SYSTEM",
             only: list[str] | None = None) -> dict[str, str]:
    """검증자에게 넘길 산출물 원문.

    기본은 읽을 수 있는 **전체**다. 변경분만 보여주면 회귀를 놓친다.
    """
    paths = only if only is not None else listdir(employee_id)
    out: dict[str, str] = {}
    for p in paths:
        try:
            out[p] = read(p, employee_id)
        except Denied:
            continue
    return out
