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
    claims.py hook pre-tool-use | session-start | session-end   (stdin: 훅 JSON)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
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
def repo_root(start: Path | None = None) -> Path:
    here = start or Path.cwd()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here,
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(__file__).resolve().parents[1]


def store_path(root: Path) -> Path:
    override = os.getenv("AI_CLAIMS_FILE")
    if override:
        return Path(override)
    try:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root,
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            common = Path(out.stdout.strip())
            if not common.is_absolute():
                common = root / common
            return common.resolve() / "ai-claims.json"
    except (OSError, subprocess.SubprocessError):
        pass
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


# ── 훅 ──────────────────────────────────────────────────────────────
def _hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def hook_pre_tool_use(data: dict, root: Path, path: Path) -> int:
    """다른 세션이 잡은 파일이면 막는다(2). 아니면 이 세션의 이름표를 붙인다(0)."""
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


def hook_session_start(data: dict, root: Path, path: Path) -> int:
    session = str(data.get("session_id") or "")
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


HOOKS = {"pre-tool-use": hook_pre_tool_use, "session-start": hook_session_start,
         "session-end": hook_session_end}


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
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
    p = sub.add_parser("hook")
    p.add_argument("event", choices=sorted(HOOKS))
    args = ap.parse_args(argv)

    if args.cmd == "hook":
        # 훅은 **절대 도구 결함으로 막지 않는다** — 막는 것은 확실한 충돌뿐.
        try:
            data = _hook_input()
            root = repo_root(Path(data["cwd"]) if data.get("cwd") else None)
            return HOOKS[args.event](data, root, store_path(root))
        except Exception as e:                                 # noqa: BLE001
            print(f"claims hook skipped: {type(e).__name__}: {e}", file=sys.stderr)
            return 0

    root = repo_root()
    path = store_path(root)
    return {"claim": cmd_claim, "release": cmd_release, "list": cmd_list,
            "check": cmd_check, "prune": cmd_prune}[args.cmd](args, root, path)


if __name__ == "__main__":
    sys.exit(main())
