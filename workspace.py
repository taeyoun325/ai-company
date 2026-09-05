"""작업 폴더 — 에이전트가 실제로 손대는 곳.

이전 설계는 `projects/<slug>/` 안에서만 놀았다. 이제는 사용자의 진짜 폴더를 연다.
그래서 이 파일의 경로 검사가 이전보다 훨씬 중요해졌다: 여기가 뚫리면
에이전트가 홈 디렉터리 전체를 건드릴 수 있다.

git 저장소면 변경 전 상태를 기록해 둔다. 되돌릴 수 있어야 마음 놓고 맡긴다.
"""
import subprocess
import threading
from pathlib import Path

import config

# 이름만으로도 실행 환경을 바꿔버리는 파일들. 이전 설계에서 그대로 가져온다.
DANGEROUS_NAMES = {"sitecustomize.py", "usercustomize.py"}

# 처음부터 안 보여주는 것들 — 목록이 잡음으로 차고, 비밀이 섞이기도 한다
HIDDEN = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
          ".mypy_cache", ".ruff_cache", "dist", "build", ".next", ".idea", ".vscode"}
SECRET_NAMES = {".env", ".secrets.json", "id_rsa", "id_ed25519", ".npmrc", ".netrc"}

# 작업 폴더는 하나뿐이고 웹 요청은 매번 다른 스레드에서 온다.
# 스레드 로컬로 두면 --dir 로 연 폴더가 요청 핸들러에 안 보인다.
_lock = threading.Lock()
_root: Path | None = None
_recent: list[str] = []


class Denied(ValueError):
    """작업 폴더 밖이거나 금지된 대상."""


def use(path: str) -> Path:
    """작업 폴더를 연다. 프로세스 전체에 적용된다."""
    global _root
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise Denied(f"폴더가 아닙니다: {path}")
    with _lock:
        _root = root
    s = str(root)
    if s in _recent:
        _recent.remove(s)
    _recent.insert(0, s)
    del _recent[8:]
    return root


def root() -> Path:
    if _root is None:
        raise RuntimeError("작업 폴더를 먼저 여세요 (workspace.use)")
    return _root


def current() -> Path | None:
    return _root


def recent() -> list[str]:
    return list(_recent)


def resolve(rel: str) -> Path:
    """작업 폴더 기준 상대경로를 안전하게 절대경로로.

    resolve() 가 심링크까지 해석하므로, 링크로 밖을 가리키는 경로도 걸린다.
    """
    r = root()
    target = (r / rel).resolve()
    try:
        target.relative_to(r)
    except ValueError:
        raise Denied(f"작업 폴더 밖 경로는 다룰 수 없습니다: {rel}")
    if target.name in DANGEROUS_NAMES:
        raise Denied(f"{target.name} 은(는) 파이썬 실행 환경을 바꿀 수 있어 금지됩니다")
    return target


def rel(path: Path) -> str:
    return str(path.relative_to(root())).replace("\\", "/")


def is_secret(name: str) -> bool:
    return name in SECRET_NAMES or name.endswith(".pem") or name.endswith(".key")


def listdir(sub: str = ".", depth: int = 2, limit: int = 400) -> list[dict]:
    """파일 트리. 잡음 폴더는 접어서 보여준다."""
    base = resolve(sub)
    out: list[dict] = []

    def walk(d: Path, level: int) -> None:
        if level > depth or len(out) >= limit:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if len(out) >= limit:
                return
            if p.name in HIDDEN:
                out.append({"path": rel(p), "kind": "skipped", "level": level})
                continue
            if p.is_dir():
                out.append({"path": rel(p), "kind": "dir", "level": level})
                walk(p, level + 1)
            else:
                out.append({"path": rel(p), "kind": "file", "level": level,
                            "bytes": p.stat().st_size,
                            "secret": is_secret(p.name)})

    walk(base, 0)
    return out


# ── git ─────────────────────────────────────────────────────────────
def _git(*args: str, timeout: int = 15) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=root(), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def is_git_repo() -> bool:
    code, _ = _git("rev-parse", "--is-inside-work-tree")
    return code == 0


def git_status() -> dict:
    """되돌릴 수 있는 상태인지 알려준다."""
    if not is_git_repo():
        return {"repo": False,
                "warning": "git 저장소가 아닙니다. 에이전트의 변경을 되돌릴 방법이 없습니다."}
    _, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    code, dirty = _git("status", "--porcelain")
    changed = [l[3:] for l in dirty.splitlines() if l.strip()] if code == 0 else []
    return {"repo": True, "branch": branch, "changed": changed[:60],
            "changed_count": len(changed)}


def git_diff(path: str | None = None) -> str:
    args = ["diff", "--no-color"]
    if path:
        args += ["--", path]
    _, out = _git(*args)
    return out[:20000]


def summary() -> dict:
    r = current()
    if r is None:
        return {"open": False, "recent": recent()}
    g = git_status()
    return {"open": True, "path": str(r), "name": r.name,
            "git": g, "recent": recent()}
