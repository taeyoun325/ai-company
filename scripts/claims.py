"""여러 Claude 세션이 같은 저장소를 건드릴 때 — 잠금과 소유권 표시 (DAY 25).

## 무엇이 있었나

DAY 24 에 두 세션이 **같은 기능(비용 상한)을 다른 설계로 동시에** 만들었다.
하나는 커밋됐고(`credits.check_global_caps`), 다른 하나(`orchestrator/guard.py`)
는 존재하지 않는 함수를 부르는 채로 커밋되지 않고 남았다. 서로 상대가 무엇을
하는지 몰랐다 — 저장소 차원에 "누가 무엇을 잡고 있다"는 표시가 없었다.

## 무엇을 하나

세 가지다. 셋 다 Claude Code 훅(`.claude/settings.json`)으로 자동으로 돈다.

1. **파일 잠금 (자동).** 한 세션이 파일을 고치면(Edit·Write) 그 파일에 이
   세션의 이름표가 붙는다(`auto`, 45분마다 갱신). 다른 세션이 같은 파일을
   고치려 하면 **막고**(PreToolUse 훅이 종료코드 2) 누가 잡고 있는지 말한다.
2. **작업 표시 (수동).** 기능 단위로 먼저 선언한다 —
   `python scripts/claims.py claim "비용 상한" --paths backend/app/usage`.
   그 경로 아래를 다른 세션이 고치면 막힌다. 파일이 달라도 **같은 기능**을
   겹쳐 만드는 일을 막는 것은 이쪽이다.
3. **알림.** 세션이 시작되면(SessionStart) 다른 세션이 잡고 있는 것을
   컨텍스트에 적어준다. 세션이 끝나면(SessionEnd) 그 세션의 표시를 푼다.
4. **셸 명령 (DAY 26).** DAY 25 의 훅은 Edit·Write 만 봤다 — `sed -i` 나
   파이썬 스크립트로 고친 파일은 그냥 지나갔다(이 도구를 만든 날 실제로 그렇게
   고쳤다). 이제 셸 도구(Bash·PowerShell)도 본다:
   - **전(PreToolUse)** — 명령이 다른 세션의 파일을 **분명히** 쓰는 모양이면
     (`> 파일` · `sed -i` · `rm` · `mv` · `cp … 파일` · `Set-Content` 등) 막는다.
     `git commit` 이면 올라간 파일(staged)을 본다.
   - **후(PostToolUse)** — 명령 전후로 파일이 실제로 바뀌었는지 본다. 스크립트
     안에서 쓴 것처럼 명령만 봐서는 모르는 것도 여기서 잡힌다. 다른 세션의
     파일이면 알리고(종료코드 2 — 되돌릴 판단은 사람과), 아니면 이 세션의
     이름표를 붙인다 — 셸로 고친 파일도 다른 세션의 Edit 를 막는다.
5. **커밋 직전 (git pre-commit).** 올라간 파일 중 다른 세션이 잡은 것이 있으면
   커밋을 막는다. 사람이 터미널에서 하는 커밋도 지난다. 세션이 시작될 때
   `.git/hooks/pre-commit` 이 없으면 깐다(남이 깐 훅은 건드리지 않는다).

## 어디에 적나

`git rev-parse --git-common-dir` 아래 `ai-claims.json`. 워크트리가 여러 개여도
공통 폴더는 하나라서 **모든 워크트리의 세션이 같은 표를 본다.** 추적되지 않는
곳이므로 커밋에 섞이지 않는다.

## 막는 쪽으로 틀리지 않는다

이 도구가 망가지면(파이썬 오류·파일 깨짐·잠금 시간 초과) **막지 않고 통과시킨다.**
협업 도구 하나의 결함 때문에 모든 편집이 멈추는 것은 도구가 막으려던 사고보다
나쁘다. 막는 것은 **확실한 충돌**일 때뿐이다.

일부러 겹쳐야 할 때는 `CLAIMS_OVERRIDE=1` 로 통과시킨다(경고는 남긴다).
훅 배선은 `.claude/settings.json` 에 있고, `/hooks` 에서 보고 끌 수 있다.

## 명령

    claims.py claim LABEL --paths P [P ...] [--session S] [--ttl-min N]
    claims.py release [--id ID | --session S | --all]
    claims.py list [--json]
    claims.py check PATH [--session S]
    claims.py prune
    claims.py precommit                      (git pre-commit 훅이 부른다)
    claims.py install-git-hook
    claims.py hook pre-tool-use | post-tool-use | session-start | session-end
                                             (stdin: 훅 JSON)
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

AUTO_TTL_MIN = float(os.getenv("CLAIMS_AUTO_TTL_MIN", "45"))
MANUAL_TTL_MIN = float(os.getenv("CLAIMS_MANUAL_TTL_MIN", str(8 * 60)))
LOCK_WAIT = 3.0
LOCK_STALE = 10.0


# ── 어디 ────────────────────────────────────────────────────────────
_dirs: dict[str, tuple[Path, Path | None]] = {}


def _git_dirs(start: Path) -> tuple[Path, Path | None]:
    """(저장소 꼭대기, 공통 git 폴더). git 을 **한 번만** 부른다 — 훅은 셸
    명령마다 두 번(전·후) 돌므로, 부를 때마다 git 을 세 번 띄우면 그게
    명령보다 오래 걸린다."""
    key = str(start)
    if key in _dirs:
        return _dirs[key]
    fast = _project_dirs(start)
    if fast is not None:
        _dirs[key] = fast
        return fast
    top: Path | None = None
    common: Path | None = None
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel",
                              "--git-common-dir"], cwd=start,
                             capture_output=True, text=True, timeout=5)
        lines = [x.strip() for x in out.stdout.splitlines() if x.strip()]
        if out.returncode == 0 and len(lines) >= 2:
            top = Path(lines[0]).resolve()
            common = Path(lines[1])
            if not common.is_absolute():
                common = start / common
            common = common.resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    res = (top or Path(__file__).resolve().parents[1], common)
    _dirs[key] = res
    return res


def _project_dirs(start: Path) -> tuple[Path, Path] | None:
    """훅이 흔히 도는 자리 — Claude Code 가 알려주는 프로젝트 폴더 안 — 에서는
    git 을 띄우지 않고 안다. `.git` 이 **폴더**일 때만(워크트리의 `.git` 은
    파일이다 — 그때는 git 에 묻는다). 사이에 다른 저장소가 끼어 있으면 모른다고
    한다."""
    proj = os.getenv("CLAUDE_PROJECT_DIR")
    if not proj:
        return None
    try:
        top = Path(proj).resolve()
        here = start.resolve()
        here.relative_to(top)
    except (OSError, ValueError):
        return None
    if not (top / ".git").is_dir():
        return None
    d = here
    while d != top:
        if (d / ".git").exists():
            return None                   # 안쪽의 다른 저장소
        d = d.parent
    return top, (top / ".git").resolve()


def repo_root(start: Path | None = None) -> Path:
    return _git_dirs(start or Path.cwd())[0]


def git_common(root: Path) -> Path | None:
    return _git_dirs(root)[1]


def store_path(root: Path) -> Path:
    override = os.getenv("AI_CLAIMS_FILE")
    if override:
        return Path(override)
    common = git_common(root)
    if common is not None:
        return common / "ai-claims.json"
    return root / ".ai-claims.json"


# ── 표 읽고 쓰기 (프로세스를 넘는 잠금) ─────────────────────────────
class Locked:
    def __init__(self, path: Path):
        self.lock = path.with_suffix(".lock")

    def __enter__(self):
        deadline = time.time() + LOCK_WAIT
        while True:
            try:
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.lock.stat().st_mtime > LOCK_STALE:
                        self.lock.unlink(missing_ok=True)     # 죽은 프로세스가 남긴 잠금
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError(f"claims lock busy: {self.lock}")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.lock.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [c for c in data.get("claims", []) if isinstance(c, dict)]


def save(path: Path, claims: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps({"claims": claims}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    os.replace(tmp, path)


def live(claims: list[dict], now: float | None = None) -> list[dict]:
    now = now or time.time()
    return [c for c in claims if float(c.get("expires_at", 0)) > now]


# ── 경로 맞추기 ─────────────────────────────────────────────────────
def rel(root: Path, p: str | os.PathLike) -> str | None:
    """저장소 기준 상대경로(슬래시). 저장소 밖이면 None."""
    path = Path(p)
    if not path.is_absolute():
        path = (Path.cwd() / path)
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def covers(pattern: str, path: str) -> bool:
    """`pattern` 이 `path` 를 덮는가 — 같은 파일 · 그 폴더 아래 · 글롭."""
    pattern = pattern.strip("/")
    if not pattern:
        return False
    if path == pattern or path.startswith(pattern + "/"):
        return True
    return fnmatch.fnmatch(path, pattern)


def conflicts(claims: list[dict], path: str, session: str) -> list[dict]:
    return [c for c in live(claims)
            if c.get("session") != session
            and any(covers(p, path) for p in c.get("paths", []))]


def describe(c: dict, now: float | None = None) -> str:
    now = now or time.time()
    mins = int((now - float(c.get("touched_at", c.get("created_at", now)))) // 60)
    who = c.get("session", "?")[:8]
    kind = "파일 편집 중" if c.get("kind") == "auto" else "작업 선언"
    paths = ", ".join(c.get("paths", [])[:4])
    return (f"[{kind}] '{c.get('label', '')}' — 세션 {who} "
            f"({c.get('host', '?')}, {mins}분 전) · {paths}")


# ── 명령 ────────────────────────────────────────────────────────────
def cmd_claim(args, root: Path, path: Path) -> int:
    paths = [r for p in args.paths if (r := rel(root, p) or p.strip("/"))]
    now = time.time()
    rec = {"id": uuid.uuid4().hex[:8], "session": args.session or "cli",
           "label": args.label, "paths": paths, "kind": "manual",
           "created_at": now, "touched_at": now,
           "expires_at": now + args.ttl_min * 60, "host": socket.gethostname()}
    with Locked(path):
        claims = live(load(path))
        clash = [c for c in claims if c.get("session") != rec["session"]
                 and any(covers(a, b) or covers(b, a)
                         for a in c.get("paths", []) for b in paths)]
        if clash and not os.getenv("CLAIMS_OVERRIDE"):
            print("이미 다른 세션이 잡고 있습니다:", file=sys.stderr)
            for c in clash:
                print("  " + describe(c), file=sys.stderr)
            return 1
        claims.append(rec)
        save(path, claims)
    print(f"claimed {rec['id']}: {rec['label']} · {', '.join(paths)}")
    return 0


def cmd_release(args, root: Path, path: Path) -> int:
    with Locked(path):
        claims = load(path)
        if args.all:
            keep = []
        elif args.id:
            keep = [c for c in claims if c.get("id") != args.id]
        else:
            keep = [c for c in claims if c.get("session") != (args.session or "cli")]
        save(path, live(keep))
    print(f"released {len(claims) - len(keep)}")
    return 0


def cmd_list(args, root: Path, path: Path) -> int:
    claims = live(load(path))
    if args.json:
        print(json.dumps(claims, ensure_ascii=False, indent=1))
        return 0
    if not claims:
        print("(잡힌 것 없음)")
    for c in claims:
        print(f"{c.get('id')}  " + describe(c))
    return 0


def cmd_check(args, root: Path, path: Path) -> int:
    target = rel(root, args.path)
    if target is None:
        return 0
    found = conflicts(load(path), target, args.session or "cli")
    for c in found:
        print(describe(c))
    return 1 if found else 0


def cmd_prune(args, root: Path, path: Path) -> int:
    with Locked(path):
        claims = load(path)
        kept = live(claims)
        save(path, kept)
    print(f"pruned {len(claims) - len(kept)}")
    return 0


# ── git 이 본 것 ─────────────────────────────────────────────────────
def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def git_dirty(root: Path) -> set[str]:
    """고쳐졌거나 새로 생긴 파일(무시 목록 제외). 저장소 기준 슬래시 경로."""
    out = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
               "--no-renames")
    if not out:
        return set()
    return {e[3:] for e in out.split("\0") if len(e) > 3}


def git_staged(root: Path) -> list[str]:
    out = _git(root, "diff", "--cached", "--name-only", "-z")
    return [x for x in (out or "").split("\0") if x]


def git_tracked_changes(root: Path) -> list[str]:
    """`git commit -a` 가 올릴 것 — 추적 중인 파일의 고친 것."""
    out = _git(root, "diff", "--name-only", "-z")
    return [x for x in (out or "").split("\0") if x]


def _stat(root: Path, rel_path: str) -> list[int] | None:
    try:
        st = (root / rel_path).stat()
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".next"}
EXPAND_LIMIT = 3000


def _expand(root: Path, patterns: list[str]) -> set[str]:
    """예약 경로(파일·폴더) → 그 아래 파일들. 너무 많으면 거기서 멈춘다."""
    out: set[str] = set()
    for pat in patterns:
        pat = pat.strip("/")
        if not pat or any(ch in pat for ch in "*?["):
            continue                     # 글롭은 펼치지 않는다 — 전·후 비교 대상 밖
        target = root / pat
        if target.is_file():
            out.add(pat)
        elif target.is_dir():
            for dirpath, dirnames, filenames in os.walk(target):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for f in filenames:
                    out.add((Path(dirpath) / f).relative_to(root).as_posix())
                    if len(out) >= EXPAND_LIMIT:
                        return out
    return out


# ── 셸 명령이 **분명히** 쓰는 파일 ────────────────────────────────────
# 명령을 완전히 해석하는 것은 불가능하다(스크립트 안의 쓰기는 명령에 안
# 보인다 — 그건 후 훅이 잡는다). 여기서는 틀릴 여지가 없는 모양만 막는다.
# 읽기(`cat 파일`)나 원본으로만 쓰는 복사(`cp 파일 /tmp`)는 막지 않는다.
_SEGMENT = re.compile(r"&&|\|\||[;|\n]")
_REDIRECT = re.compile(r"(?<![0-9&<>])>{1,2}\s*(\"[^\"]+\"|'[^']+'|[^\s;&|<>]+)")
_ANY_ARG = {"rm", "del", "erase", "unlink", "truncate", "shred", "tee", "mv",
            "move", "remove-item", "ri", "clear-content", "clc", "set-content",
            "sc", "add-content", "ac", "out-file", "move-item", "mi",
            "rename-item", "ren", "rni", "new-item", "ni"}
_LAST_ARG = {"cp", "copy", "copy-item", "cpi", "install", "ln"}
_GIT_WRITES = {"checkout", "restore", "rm", "mv", "reset", "apply"}
COMMIT = re.compile(r"\bgit\b(?:\s+-[cC]\s+\S+)*\s+commit\b")


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def write_targets(command: str) -> list[str]:
    """명령이 분명히 쓰는(또는 지우는) 경로들. 해석은 호출부가 한다."""
    out: list[str] = []
    for m in _REDIRECT.finditer(command):
        out.append(m.group(1).strip("\"'"))
    for seg in _SEGMENT.split(command):
        toks = _tokens(seg)
        while toks and ("=" in toks[0] and not toks[0].startswith("-")
                        or toks[0] in ("sudo", "command", "exec", "&")):
            toks = toks[1:]
        if not toks:
            continue
        verb = toks[0].lower().rsplit("/", 1)[-1]
        args = [t for t in toks[1:] if not t.startswith("-") and not t.startswith(">")]
        if verb == "sed" and any(t == "-i" or t.startswith("-i") or t == "--in-place"
                                 for t in toks[1:]):
            out.extend(args[1:])        # 첫 인자는 식이다
        elif verb in _ANY_ARG:
            out.extend(args)
        elif verb in _LAST_ARG and len(args) >= 2:
            out.append(args[-1])
        elif verb == "git" and len(args) >= 2 and args[0] in _GIT_WRITES:
            out.extend(args[1:])
    return [t for t in out if t and t not in (".", "..")]


def _shell_state(path: Path, session: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session)[:80]
    return path.parent / "ai-claims-shell" / f"{safe}.json"


def _block(lines: list[str]) -> int:
    lines += [
        "겹쳐 고치면 한쪽 작업이 조용히 사라집니다(DAY 24 의 guard.py).",
        "사용자에게 어느 세션이 맡을지 물어보세요. 사용자가 허락하면: "
        "python scripts/claims.py release --id <ID>",
    ]
    print("\n".join(lines), file=sys.stderr)
    return 2


def hook_pre_shell(data: dict, root: Path, path: Path) -> int:
    """셸 명령 **전** — 분명한 쓰기·커밋을 막고, 비교할 기준을 찍어둔다."""
    session = str(data.get("session_id") or "")
    command = str((data.get("tool_input") or {}).get("command") or "")
    if not session or not command:
        return 0
    cwd = Path(data.get("cwd") or root)
    now = time.time()
    claims = live(load(path), now)
    others = [c for c in claims if c.get("session") != session]
    override = bool(os.getenv("CLAIMS_OVERRIDE"))

    if others and COMMIT.search(command):
        files = git_staged(root)
        if re.search(r"\scommit\b[^;&|\n]*\s(-a\b|--all\b|-[a-zA-Z]*a[a-zA-Z]*\b)",
                     command):
            files += git_tracked_changes(root)
        hits = [(f, c) for f in dict.fromkeys(files)
                for c in conflicts(claims, f, session)]
        if hits and not override:
            lines = ["다른 Claude 세션이 잡은 파일이 커밋에 들어가 있어 막았습니다:"]
            lines += [f"  {f} ← " + describe(c, now) for f, c in hits]
            lines += ["그 파일을 커밋에서 빼거나(git restore --staged <파일>), "
                      "사용자와 정하세요."]
            return _block(lines)

    if others:
        hits = []
        for raw in write_targets(command):
            target = rel(root, cwd / raw if not Path(raw).is_absolute() else raw)
            if target is None:
                continue
            hits += [(target, c) for c in conflicts(claims, target, session)]
        if hits and not override:
            lines = ["다른 Claude 세션이 잡은 파일을 셸 명령이 고치려 해서 막았습니다:"]
            lines += [f"  {t} ← " + describe(c, now) for t, c in hits]
            return _block(lines)

    # 전에는 **다른 세션의 파일**만 찍는다 — 지워지거나 바뀌었는지 볼 기준이다.
    # 이 세션이 바꾼 파일은 후에 git 이 "고쳐짐"이라고 한 것 중 시각이 명령
    # 시작보다 늦은 것으로 가른다. 전에 git 을 한 번 더 띄우지 않는다 — 셸
    # 명령마다 두 번(전·후) 도는 훅이라 한 번이 곧 체감 지연이다.
    watch = _expand(root, [p for c in others for p in c.get("paths", [])])
    state = {"t": now, "files": {f: _stat(root, f) for f in sorted(watch)}}
    sp = _shell_state(path, session)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(state), encoding="utf-8")
    return 0


TAG_LIMIT = 200


def hook_post_shell(data: dict, root: Path, path: Path) -> int:
    """셸 명령 **후** — 실제로 바뀐 파일을 본다.

    다른 세션의 파일이 바뀌었으면 알린다(2). 그 세션이 같은 사이에 Edit 로
    고친 것(이름표의 `touched_at` 이 명령 시작보다 늦다)은 그 세션의 일이므로
    세지 않는다. 나머지 바뀐 파일에는 이 세션의 이름표를 붙인다.
    """
    session = str(data.get("session_id") or "")
    if not session:
        return 0
    sp = _shell_state(path, session)
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    finally:
        try:
            sp.unlink(missing_ok=True)
        except OSError:
            pass
    t0 = float(state.get("t") or 0)
    t0_ns = int(t0 * 1e9)
    before: dict = state.get("files") or {}
    fresh = set()
    for f in git_dirty(root) - set(before):
        st = _stat(root, f)
        if st is not None and st[0] >= t0_ns:
            fresh.add(f)             # 명령이 도는 동안 쓰였다
    changed = sorted({f for f in before if _stat(root, f) != before[f]} | fresh)
    if not changed:
        return 0
    now = time.time()
    hits: list[tuple[str, dict]] = []
    theirs: set[str] = set()
    with Locked(path):
        claims = live(load(path), now)
        for f in changed:
            for c in conflicts(claims, f, session):
                theirs.add(f)
                if float(c.get("touched_at", 0)) <= t0:
                    hits.append((f, c))
        mine = [f for f in changed if f not in theirs][:TAG_LIMIT]
        for f in mine:
            c = next((c for c in claims if c.get("session") == session
                      and c.get("kind") == "auto" and c.get("paths") == [f]), None)
            if c is None:
                claims.append({"id": uuid.uuid4().hex[:8], "session": session,
                               "label": f, "paths": [f], "kind": "auto",
                               "created_at": now, "touched_at": now,
                               "expires_at": now + AUTO_TTL_MIN * 60,
                               "host": socket.gethostname(), "via": "shell"})
            else:
                c["touched_at"] = now
                c["expires_at"] = now + AUTO_TTL_MIN * 60
        if mine:
            save(path, claims)
    if not hits:
        return 0
    lines = ["방금 셸 명령이 다른 Claude 세션이 잡은 파일을 바꿨습니다:"]
    lines += [f"  {f} ← " + describe(c, now) for f, c in hits]
    lines += ["그 세션의 작업을 덮었을 수 있습니다. 되돌리기 전에 사용자에게 "
              "알리고 어느 쪽을 남길지 정하세요."]
    print("\n".join(lines), file=sys.stderr)
    return 2


# ── 커밋 직전 (git pre-commit) ────────────────────────────────────────
HOOK_MARK = "ai-claims pre-commit"
HOOK_BODY = f"""#!/bin/sh
# {HOOK_MARK} — scripts/claims.py 가 깔았다. 다른 Claude 세션이 잡은 파일이
# 커밋에 섞이지 않게 한다. 도구가 없거나 망가지면 막지 않는다.
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -f "$root/scripts/claims.py" ] || exit 0
# 막는 것은 종료코드 3(확실한 충돌)일 때뿐이다. 파이썬이 없거나(윈도우의
# 스토어 안내 stub 은 9009 를 낸다) 도구가 죽으면(1) 통과시킨다.
for py in python python3 py; do
  if command -v "$py" >/dev/null 2>&1; then
    "$py" "$root/scripts/claims.py" precommit
    [ $? -eq 3 ] && exit 1
    exit 0
  fi
done
exit 0
"""
BLOCKED = 3


def cmd_precommit(args, root: Path, path: Path) -> int:
    """올라간 파일 중 **다른 세션**이 잡은 것이 있으면 커밋을 막는다(3).

    지금 커밋하는 세션은 `CLAUDE_CODE_SESSION_ID`(Claude Code 가 셸에 넣는다)
    로 안다. 사람이 터미널에서 하면 그 값이 없으므로 모든 세션의 표시를 본다.
    """
    try:
        session = os.getenv("CLAUDE_CODE_SESSION_ID") or ""
        now = time.time()
        claims = live(load(path), now)
        hits = [(f, c) for f in git_staged(root)
                for c in conflicts(claims, f, session)]
    except Exception as e:                                     # noqa: BLE001
        print(f"claims pre-commit skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if not hits:
        return 0
    if os.getenv("CLAIMS_OVERRIDE"):
        print(f"CLAIMS_OVERRIDE: 다른 세션이 잡은 파일 {len(hits)}개를 커밋합니다.",
              file=sys.stderr)
        return 0
    lines = ["커밋을 막았습니다 — 다른 Claude 세션이 잡고 있는 파일이 들어 있습니다:"]
    lines += [f"  {f} ← " + describe(c, now) for f, c in hits]
    lines += ["그 세션과 먼저 정하세요. 빼려면: git restore --staged <파일>",
              "일부러 함께 커밋하려면: CLAIMS_OVERRIDE=1 git commit ..."]
    print("\n".join(lines), file=sys.stderr)
    return BLOCKED


def ensure_git_hook(root: Path) -> str:
    """`.git/hooks/pre-commit` 을 깐다. 남이 깐 훅은 건드리지 않는다.

    돌려주는 값: installed · current · foreign · unavailable.
    """
    common = git_common(root)
    if common is None or (os.getenv("AI_CLAIMS_FILE")
                          and not os.getenv("AI_CLAIMS_GIT_HOOK")):
        return "unavailable"            # 시험 중에는 실제 저장소 훅을 건드리지 않는다
    target = common / "hooks" / "pre-commit"
    if target.exists():
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "foreign"
        if HOOK_MARK not in text:
            return "foreign"
        if text == HOOK_BODY:
            return "current"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(HOOK_BODY, encoding="utf-8", newline="\n")
    try:
        target.chmod(0o755)
    except OSError:
        pass
    return "installed"


def cmd_install_git_hook(args, root: Path, path: Path) -> int:
    status = ensure_git_hook(root)
    print(status)
    return 0 if status in ("installed", "current") else 1


# ── 훅 ──────────────────────────────────────────────────────────────
SHELL_TOOLS = ("Bash", "PowerShell")


def _hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def hook_pre_tool_use(data: dict, root: Path, path: Path) -> int:
    """다른 세션이 잡은 파일이면 막는다(2). 아니면 이 세션의 이름표를 붙인다(0)."""
    if data.get("tool_name") in SHELL_TOOLS:
        return hook_pre_shell(data, root, path)
    session = str(data.get("session_id") or "")
    tool_input = data.get("tool_input") or {}
    target_raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not session or not target_raw:
        return 0
    cwd = data.get("cwd")
    target_path = Path(target_raw)
    if not target_path.is_absolute() and cwd:
        target_path = Path(cwd) / target_path
    target = rel(root, target_path)
    if target is None:
        return 0                                   # 저장소 밖 — 우리 일이 아니다
    now = time.time()
    with Locked(path):
        claims = live(load(path), now)
        found = conflicts(claims, target, session)
        if found and not os.getenv("CLAIMS_OVERRIDE"):
            lines = [f"다른 Claude 세션이 이 파일을 잡고 있어 편집을 막았습니다: {target}"]
            lines += ["  " + describe(c, now) for c in found]
            lines += [
                "겹쳐 만들면 한쪽 설계가 조용히 버려집니다(DAY 24 의 guard.py).",
                "사용자에게 어느 세션이 맡을지 물어보세요. 사용자가 허락하면: "
                "python scripts/claims.py release --id <ID>",
            ]
            print("\n".join(lines), file=sys.stderr)
            return 2
        # 이 세션의 이름표 — 같은 파일이면 시각만 갱신한다.
        mine = next((c for c in claims if c.get("session") == session
                     and c.get("kind") == "auto" and c.get("paths") == [target]), None)
        if mine is None:
            claims.append({"id": uuid.uuid4().hex[:8], "session": session,
                           "label": target, "paths": [target], "kind": "auto",
                           "created_at": now, "touched_at": now,
                           "expires_at": now + AUTO_TTL_MIN * 60,
                           "host": socket.gethostname()})
        else:
            mine["touched_at"] = now
            mine["expires_at"] = now + AUTO_TTL_MIN * 60
        save(path, claims)
    if found:
        print(f"CLAIMS_OVERRIDE: {len(found)}건의 다른 세션 표시를 무시하고 편집합니다.",
              file=sys.stderr)
    return 0


def hook_post_tool_use(data: dict, root: Path, path: Path) -> int:
    if data.get("tool_name") in SHELL_TOOLS:
        return hook_post_shell(data, root, path)
    return 0


def hook_session_start(data: dict, root: Path, path: Path) -> int:
    session = str(data.get("session_id") or "")
    if ensure_git_hook(root) == "foreign":
        print("알림: .git/hooks/pre-commit 에 다른 훅이 있어 커밋 직전 검사"
              "(scripts/claims.py precommit)를 깔지 않았습니다.")
    others = [c for c in live(load(path)) if c.get("session") != session]
    if not others:
        return 0
    print("다른 Claude 세션이 지금 이 저장소에서 잡고 있는 것 "
          "(겹치는 작업은 먼저 사용자와 정하세요 · scripts/claims.py):")
    for c in others:
        print("- " + describe(c))
    return 0


def hook_session_end(data: dict, root: Path, path: Path) -> int:
    session = str(data.get("session_id") or "")
    if not session:
        return 0
    with Locked(path):
        claims = load(path)
        save(path, live([c for c in claims if c.get("session") != session]))
    return 0


HOOKS = {"pre-tool-use": hook_pre_tool_use, "post-tool-use": hook_post_tool_use,
         "session-start": hook_session_start, "session-end": hook_session_end}


def _run_hook(event: str) -> int:
    # 훅은 **절대 도구 결함으로 막지 않는다** — 막는 것은 확실한 충돌뿐.
    try:
        data = _hook_input()
        root = repo_root(Path(data["cwd"]) if data.get("cwd") else None)
        return HOOKS[event](data, root, store_path(root))
    except Exception as e:                                     # noqa: BLE001
        print(f"claims hook skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
    argv = sys.argv[1:] if argv is None else list(argv)
    # 훅은 셸 명령마다 두 번 돈다 — argparse 를 올리지 않는다(~27ms · DAY 26).
    if len(argv) == 2 and argv[0] == "hook" and argv[1] in HOOKS:
        return _run_hook(argv[1])
    import argparse
    ap = argparse.ArgumentParser(prog="claims.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("claim")
    p.add_argument("label")
    p.add_argument("--paths", nargs="+", required=True)
    p.add_argument("--session")
    p.add_argument("--ttl-min", type=float, default=MANUAL_TTL_MIN)
    p = sub.add_parser("release")
    p.add_argument("--id")
    p.add_argument("--session")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("path")
    p.add_argument("--session")
    sub.add_parser("prune")
    sub.add_parser("precommit")
    sub.add_parser("install-git-hook")
    p = sub.add_parser("hook")
    p.add_argument("event", choices=sorted(HOOKS))
    args = ap.parse_args(argv)

    if args.cmd == "hook":
        return _run_hook(args.event)

    root = repo_root()
    path = store_path(root)
    return {"claim": cmd_claim, "release": cmd_release, "list": cmd_list,
            "check": cmd_check, "prune": cmd_prune, "precommit": cmd_precommit,
            "install-git-hook": cmd_install_git_hook}[args.cmd](args, root, path)


if __name__ == "__main__":
    sys.exit(main())
