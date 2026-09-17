"""역할별 쓰기 권한이 있는 파일 툴.

이 파일의 존재 이유는 하나다: **구현자가 검증기를 고칠 수 없게 하는 것.**
DEV는 src/ 에만 쓸 수 있고 tests/ 는 읽지도 못한다. QA만 tests/ 에 쓴다.
그래서 "테스트를 통과시키려고 테스트를 고치는" 우회가 원천 차단된다.
"""
import threading
from pathlib import Path

import store

SRC = "src"
TESTS = "tests"

# 쓰기 위치와 무관하게 어디에도 만들 수 없는 파일들.
# pytest가 자동으로 읽어들이거나 파이썬이 기동 시 자동 import 하는 것들이라,
# 하나라도 허용하면 테스트 실행 환경 자체를 바꿔버릴 수 있다.
FORBIDDEN_NAMES = {
    "conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml",
    "setup.py", "sitecustomize.py", "usercustomize.py", ".pth",
}

# 역할별 쓰기 가능 루트
WRITABLE = {"DEV": (SRC,), "QA": (TESTS,), "SYSTEM": (SRC, TESTS)}
# 역할별 읽기 가능 루트 (DEV는 tests/ 를 볼 수 없다 — 보면 맞춰 짜게 된다)
READABLE = {"DEV": (SRC,), "QA": (SRC, TESTS), "SYSTEM": (SRC, TESTS)}

# 실행 하나가 스레드 하나다. 전역이면 동시 실행이 서로를 덮어쓴다.
_local = threading.local()


class Denied(ValueError):
    """권한 위반. 에이전트에게 그대로 돌려주면 스스로 교정한다."""


def use(slug: str) -> None:
    """이 스레드가 작업할 프로젝트를 지정한다."""
    _local.slug = slug
    for sub in (SRC, TESTS):
        (root() / sub).mkdir(parents=True, exist_ok=True)


def slug() -> str:
    cur = getattr(_local, "slug", None)
    if cur is None:
        raise RuntimeError("이 스레드에서 fs.use(slug)를 먼저 호출해야 합니다")
    return cur


def current() -> str | None:
    return getattr(_local, "slug", None)


def root() -> Path:
    return store.dir_of(slug())


def _resolve(path: str, role: str, write: bool) -> Path:
    r = root().resolve()
    target = (r / path).resolve()          # resolve()가 심링크까지 해석한다
    if not str(target).startswith(str(r) + "\\") and str(target) != str(r):
        if not str(target).startswith(str(r) + "/"):
            raise Denied(f"프로젝트 폴더 밖 경로: {path}")

    rel = target.relative_to(r)
    if not rel.parts:
        raise Denied("루트 자체는 대상이 될 수 없습니다")
    top = rel.parts[0]

    allowed = (WRITABLE if write else READABLE).get(role, ())
    if top not in allowed:
        verb = "쓰기" if write else "읽기"
        raise Denied(f"{role}는 {top}/ 에 {verb} 권한이 없습니다. 허용: {'/, '.join(allowed)}/")

    if write and (target.name in FORBIDDEN_NAMES or target.suffix == ".pth"):
        raise Denied(f"{target.name} 은(는) 테스트 실행 환경을 바꿀 수 있어 금지된 파일명입니다")

    return target


def read(path: str, role: str = "SYSTEM") -> str:
    p = _resolve(path, role, write=False)
    if not p.exists():
        return f"(파일 없음: {path})"
    return p.read_text(encoding="utf-8")


def write(path: str, content: str, role: str = "SYSTEM") -> dict:
    p = _resolve(path, role, write=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    before = p.read_text(encoding="utf-8") if p.exists() else None
    # 덮어쓰기 전 내용을 이력에 남긴다 — 회차별 diff의 재료
    if before is not None and before != content:
        store.snapshot_version(slug(), path, before, note=f"{role} 덮어쓰기 직전")
    p.write_text(content, encoding="utf-8")
    return {"path": path, "created": before is None,
            "old_lines": len(before.splitlines()) if before else 0,
            "new_lines": len(content.splitlines())}


def listdir(role: str = "SYSTEM") -> list[str]:
    allowed = READABLE.get(role, ())
    return [f for f in store.files_of(slug())
            if f.split("/", 1)[0] in allowed]


def snapshot(role: str = "SYSTEM", only: list[str] | None = None) -> dict[str, str]:
    """QA에게 넘길 코드 원문. 기본은 읽기 가능한 전체 — 부분만 보면 회귀를 놓친다."""
    paths = only if only is not None else listdir(role)
    out = {}
    for p in paths:
        try:
            out[p] = read(p, role)
        except Denied:
            continue
    return out
