"""메인 에이전트의 도구 — Claude Code가 쓰는 것과 같은 종류.

읽기는 그냥 하고, **쓰기와 명령 실행은 승인 게이트를 통과해야** 실행된다.
이전 설계의 신뢰 경계(역할별 쓰기 권한)를 버렸으므로, 이제 사람의 승인이
유일한 방어선이다. 그래서 승인 화면에 diff를 함께 보여준다 —
무엇이 바뀌는지 모르고 누르는 승인은 승인이 아니다.
"""
import difflib
import os
import subprocess
import sys

from anthropic import beta_tool

import approvals
import bus
import secrets_broker
import workspace

MAX_READ = 400_000          # 한 파일에서 읽어 모델에 넣는 최대 문자 수
BASH_TIMEOUT = 120

# 물어보지 않고도 되는 명령. 상태를 바꾸지 않는 것만.
SAFE_BASH = ("ls", "dir", "cat", "type", "head", "tail", "wc", "pwd", "echo",
             "git status", "git log", "git diff", "git branch", "git show",
             "python --version", "node --version", "npm --version", "which", "where")


def _preview_diff(path, old: str, new: str) -> str:
    d = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                  lineterm="", n=2))
    body = "\n".join(d[2:40]) if len(d) > 2 else "(변경 없음)"
    more = f"\n… 외 {len(d) - 40}줄" if len(d) > 40 else ""
    return body + more


# ── 읽기 ────────────────────────────────────────────────────────────
@beta_tool
def read_file(path: str) -> str:
    """작업 폴더 안의 파일을 읽는다.

    Args:
        path: 작업 폴더 기준 상대경로. 예: src/main.py
    """
    try:
        p = workspace.resolve(path)
    except workspace.Denied as e:
        return f"거부됨: {e}"
    if not p.is_file():
        return f"(파일 없음: {path})"
    if workspace.is_secret(p.name):
        return f"거부됨: {path} 는 비밀이 담긴 파일로 보여 읽지 않습니다."
    bus.say("AGENT", f"읽는 중 — `{path}`", kind="tool")
    text = p.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_READ:
        return text[:MAX_READ] + f"\n\n… (파일이 길어 {len(text)}자 중 앞부분만)"
    return text


@beta_tool
def list_dir(path: str = ".", depth: int = 2) -> str:
    """폴더 구조를 본다.

    Args:
        path: 작업 폴더 기준 상대경로. 기본은 루트.
        depth: 몇 단계까지 내려갈지. 기본 2.
    """
    try:
        rows = workspace.listdir(path, depth=depth)
    except workspace.Denied as e:
        return f"거부됨: {e}"
    bus.say("AGENT", f"폴더 확인 — `{path}` ({len(rows)}개)", kind="tool")
    lines = []
    for r in rows:
        pad = "  " * r["level"]
        if r["kind"] == "dir":
            lines.append(f"{pad}{r['path']}/")
        elif r["kind"] == "skipped":
            lines.append(f"{pad}{r['path']}/ (건너뜀)")
        else:
            mark = " [비밀]" if r.get("secret") else ""
            lines.append(f"{pad}{r['path']} ({r['bytes']}B){mark}")
    return "\n".join(lines) or "(비어 있음)"


@beta_tool
def search(pattern: str, path: str = ".", max_results: int = 60) -> str:
    """파일 내용을 정규식으로 찾는다. grep 과 같다.

    Args:
        pattern: 찾을 정규식.
        path: 어디서부터 찾을지. 기본은 작업 폴더 전체.
        max_results: 최대 결과 수.
    """
    import re
    try:
        base = workspace.resolve(path)
        rx = re.compile(pattern)
    except workspace.Denied as e:
        return f"거부됨: {e}"
    except re.error as e:
        return f"정규식 오류: {e}"

    bus.say("AGENT", f"검색 — `{pattern}`", kind="tool")
    hits = []
    files = [base] if base.is_file() else base.rglob("*")
    for f in files:
        if len(hits) >= max_results:
            break
        if not f.is_file() or any(part in workspace.HIDDEN for part in f.parts):
            continue
        if workspace.is_secret(f.name):
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8",
                                                 errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{workspace.rel(f)}:{i}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        break
        except OSError:
            continue
    return "\n".join(hits) or "(일치 없음)"


@beta_tool
def find_files(glob: str = "**/*.py", max_results: int = 200) -> str:
    """이름 패턴으로 파일을 찾는다.

    Args:
        glob: 예: **/*.py, src/**/*.ts
        max_results: 최대 개수.
    """
    root = workspace.root()
    bus.say("AGENT", f"파일 찾기 — `{glob}`", kind="tool")
    out = []
    for p in root.glob(glob):
        if p.is_file() and not any(part in workspace.HIDDEN for part in p.parts):
            out.append(workspace.rel(p))
            if len(out) >= max_results:
                break
    return "\n".join(sorted(out)) or "(없음)"


# ── 쓰기 — 승인 필요 ────────────────────────────────────────────────
@beta_tool
def write_file(path: str, content: str) -> str:
    """파일을 만들거나 통째로 덮어쓴다. 사람의 승인을 받은 뒤에만 실행된다.

    Args:
        path: 작업 폴더 기준 상대경로.
        content: 파일 전체 내용. 일부만 넣으면 나머지가 사라진다.
    """
    try:
        p = workspace.resolve(path)
    except workspace.Denied as e:
        return f"거부됨: {e}"

    old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    action = "수정" if old else "생성"
    diff = _preview_diff(p, old, content) if old else content[:1200]

    try:
        approvals.request(
            "write", {"path": path, "content": content},
            why=f"{action}: {path}\n```\n{diff}\n```")
    except approvals.PlanMode as e:
        return f"계획 모드: {e}"
    except approvals.Denied as e:
        return f"사용자가 거부했습니다: {e}"

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    bus.say("AGENT", f"`{path}` {action} ({len(content.splitlines())}줄)", kind="tool")
    bus.state(changed=workspace.git_status().get("changed", []))
    return f"ok: {path} ({action})"


@beta_tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """파일의 일부만 바꾼다. old_text 는 파일에 정확히 한 번만 나와야 한다.

    파일 전체를 다시 쓰는 것보다 안전하다 — 나머지 내용이 사라지지 않는다.

    Args:
        path: 작업 폴더 기준 상대경로.
        old_text: 바꿀 기존 텍스트. 공백까지 정확히 일치해야 한다.
        new_text: 새 텍스트.
    """
    try:
        p = workspace.resolve(path)
    except workspace.Denied as e:
        return f"거부됨: {e}"
    if not p.is_file():
        return f"(파일 없음: {path})"

    old = p.read_text(encoding="utf-8", errors="replace")
    n = old.count(old_text)
    if n == 0:
        return "old_text 가 파일에 없습니다. read_file 로 정확한 내용을 먼저 확인하세요."
    if n > 1:
        return f"old_text 가 {n}번 나옵니다. 앞뒤를 더 붙여 유일하게 만드세요."

    new = old.replace(old_text, new_text, 1)
    try:
        approvals.request(
            "edit", {"path": path, "content": new},
            why=f"수정: {path}\n```\n{_preview_diff(p, old, new)}\n```")
    except approvals.PlanMode as e:
        return f"계획 모드: {e}"
    except approvals.Denied as e:
        return f"사용자가 거부했습니다: {e}"

    p.write_text(new, encoding="utf-8")
    bus.say("AGENT", f"`{path}` 부분 수정", kind="tool")
    bus.state(changed=workspace.git_status().get("changed", []))
    return f"ok: {path} 수정됨"


@beta_tool
def run_command(command: str, why: str = "") -> str:
    """작업 폴더에서 셸 명령을 실행한다. 사람의 승인을 받은 뒤에만 실행된다.

    테스트 실행, 빌드, 의존성 설치 같은 데 쓴다.

    Args:
        command: 실행할 명령.
        why: 왜 필요한지 한 문장. 승인 화면에 그대로 표시된다.
    """
    cmd = command.strip()
    low = cmd.lower()
    # 상태를 바꾸지 않는 명령은 자동 모드에서만 건너뛴다.
    # 수동 모드는 "항상 확인"이 약속이므로 예외를 두지 않는다.
    safe = any(low == s or low.startswith(s + " ") for s in SAFE_BASH)
    if not (safe and approvals.mode == "auto"):
        try:
            approvals.request("bash", {"command": cmd},
                              why=why or "명령 실행이 필요합니다")
        except approvals.PlanMode as e:
            return f"계획 모드: {e}"
        except approvals.Denied as e:
            return f"사용자가 거부했습니다: {e}"

    bus.say("AGENT", f"실행 — `{cmd}`", kind="tool")
    env = {k: v for k, v in os.environ.items()
           if not any(h in k.upper() for h in
                      ("KEY", "TOKEN", "SECRET", "ANTHROPIC", "GEMINI"))}
    try:
        r = subprocess.run(cmd, shell=True, cwd=workspace.root(), env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=BASH_TIMEOUT)
        out = (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"[타임아웃 {BASH_TIMEOUT}초]"
    except OSError as e:
        return f"실행 실패: {e}"

    out = secrets_broker.scrub(out)
    if len(out) > 12000:
        out = out[:6000] + "\n… (중략) …\n" + out[-6000:]
    bus.state(changed=workspace.git_status().get("changed", []))
    return f"[종료코드 {r.returncode}]\n{out or '(출력 없음)'}"


READ_TOOLS = [read_file, list_dir, search, find_files]
WRITE_TOOLS = [write_file, edit_file, run_command]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
