"""여러 세션 조정 도구 (DAY 25 · scripts/claims.py).

## 이 파일이 지키려는 것

1. **다른 세션이 고치는 파일은 막는다** — 훅이 종료코드 2 로 거절하고, 누가
   잡고 있는지 말한다.
2. **같은 세션은 막지 않는다.** 세션이 끝나면 표시가 풀린다.
3. **작업 선언(경로 단위)이 그 아래 파일을 덮는다** — 파일이 달라도 같은 기능을
   겹쳐 만드는 일을 막는 것은 이쪽이다(DAY 24 의 guard.py).
4. **도구가 망가져도 편집을 막지 않는다.** 깨진 입력·깨진 파일 → 통과.

훅은 Claude Code 가 부르는 모양 그대로 — 표준입력 JSON, 종료코드 — 로
**별도 프로세스**를 띄워 시험한다. 함수만 부르면 훅 배선이 깨진 것을 못 본다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "claims.py"


@pytest.fixture
def env(tmp_path):
    e = dict(os.environ)
    e["AI_CLAIMS_FILE"] = str(tmp_path / "claims.json")
    e.pop("CLAIMS_OVERRIDE", None)
    return e


def run(env, *args, stdin: dict | str | None = None):
    data = stdin if isinstance(stdin, str) else json.dumps(stdin or {})
    p = subprocess.run([sys.executable, str(SCRIPT), *args], input=data,
                       capture_output=True, text=True, encoding="utf-8",
                       env=env, cwd=ROOT, timeout=30)
    return p.returncode, p.stdout, p.stderr


def edit(session: str, rel: str, tool: str = "Edit") -> dict:
    return {"session_id": session, "tool_name": tool, "cwd": str(ROOT),
            "tool_input": {"file_path": str(ROOT / rel)}}


def test_another_session_editing_the_same_file_is_blocked(env):
    code, _, _ = run(env, "hook", "pre-tool-use",
                     stdin=edit("A", "backend/app/office.py"))
    assert code == 0
    code, _, err = run(env, "hook", "pre-tool-use",
                       stdin=edit("B", "backend/app/office.py"))
    assert code == 2, "다른 세션의 같은 파일 편집이 통과했다"
    assert "backend/app/office.py" in err and "세션 A" in err


def test_the_same_session_is_never_blocked(env):
    for _ in range(3):
        code, _, _ = run(env, "hook", "pre-tool-use",
                         stdin=edit("A", "backend/app/office.py", "Write"))
        assert code == 0


def test_different_files_do_not_collide(env):
    run(env, "hook", "pre-tool-use", stdin=edit("A", "backend/app/office.py"))
    code, _, _ = run(env, "hook", "pre-tool-use",
                     stdin=edit("B", "backend/app/secretary.py"))
    assert code == 0


def test_session_end_releases_its_claims(env):
    run(env, "hook", "pre-tool-use", stdin=edit("A", "backend/app/office.py"))
    run(env, "hook", "session-end", stdin={"session_id": "A", "cwd": str(ROOT)})
    code, _, _ = run(env, "hook", "pre-tool-use",
                     stdin=edit("B", "backend/app/office.py"))
    assert code == 0


def test_a_declared_feature_covers_every_file_under_it(env):
    code, out, _ = run(env, "claim", "비용 상한", "--paths", "backend/app/usage",
                       "--session", "A")
    assert code == 0 and "비용 상한" in out
    code, _, err = run(env, "hook", "pre-tool-use",
                       stdin=edit("B", "backend/app/usage/credits.py", "Write"))
    assert code == 2 and "비용 상한" in err


def test_overlapping_declarations_are_refused(env):
    run(env, "claim", "비용 상한", "--paths", "backend/app/usage", "--session", "A")
    code, _, err = run(env, "claim", "지갑 개편", "--paths",
                       "backend/app/usage/wallet_store.py", "--session", "B")
    assert code == 1 and "비용 상한" in err


def test_session_start_tells_about_other_sessions_only(env):
    run(env, "claim", "사무실 개편", "--paths", "frontend/src/app", "--session", "A")
    _, out_b, _ = run(env, "hook", "session-start",
                      stdin={"session_id": "B", "cwd": str(ROOT)})
    assert "사무실 개편" in out_b
    _, out_a, _ = run(env, "hook", "session-start",
                      stdin={"session_id": "A", "cwd": str(ROOT)})
    assert out_a.strip() == ""


def test_override_lets_it_through_with_a_warning(env):
    run(env, "hook", "pre-tool-use", stdin=edit("A", "backend/app/office.py"))
    env["CLAIMS_OVERRIDE"] = "1"
    code, _, err = run(env, "hook", "pre-tool-use",
                       stdin=edit("B", "backend/app/office.py"))
    assert code == 0 and "CLAIMS_OVERRIDE" in err


def test_expired_claims_do_not_block(env):
    env["CLAIMS_AUTO_TTL_MIN"] = "0"
    run(env, "hook", "pre-tool-use", stdin=edit("A", "backend/app/office.py"))
    code, _, _ = run(env, "hook", "pre-tool-use",
                     stdin=edit("B", "backend/app/office.py"))
    assert code == 0


def test_files_outside_the_repo_are_ignored(env, tmp_path):
    outside = {"session_id": "A", "tool_name": "Write", "cwd": str(ROOT),
               "tool_input": {"file_path": str(tmp_path / "x.txt")}}
    run(env, "hook", "pre-tool-use", stdin=outside)
    outside["session_id"] = "B"
    code, _, _ = run(env, "hook", "pre-tool-use", stdin=outside)
    assert code == 0


@pytest.mark.parametrize("bad", ["not json", "", '{"tool_input": 5}'])
def test_broken_input_never_blocks(env, bad):
    code, _, _ = run(env, "hook", "pre-tool-use", stdin=bad)
    assert code == 0


def test_a_corrupt_store_never_blocks(env):
    Path(env["AI_CLAIMS_FILE"]).write_text("{{{ not json", encoding="utf-8")
    code, _, _ = run(env, "hook", "pre-tool-use",
                     stdin=edit("A", "backend/app/office.py"))
    assert code == 0


def test_project_settings_wire_the_hooks():
    """훅 배선이 설정에서 빠지면 이 도구는 아무것도 안 한다."""
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = s["hooks"]
    pre = [h["command"] for m in hooks["PreToolUse"] for h in m["hooks"]
           if "Edit" in m.get("matcher", "")]
    assert any("claims.py" in c and "pre-tool-use" in c for c in pre)
    shell_pre = [h["command"] for m in hooks["PreToolUse"] for h in m["hooks"]
                 if "Bash" in m.get("matcher", "") and "PowerShell" in m["matcher"]]
    assert any("pre-tool-use" in c for c in shell_pre), "셸 명령 전 훅이 빠졌다"
    shell_post = [h["command"] for m in hooks.get("PostToolUse", []) for h in m["hooks"]
                  if "Bash" in m.get("matcher", "") and "PowerShell" in m["matcher"]]
    assert any("post-tool-use" in c for c in shell_post), "셸 명령 후 훅이 빠졌다"
    assert any("session-start" in h["command"]
               for m in hooks["SessionStart"] for h in m["hooks"])
    assert any("session-end" in h["command"]
               for m in hooks["SessionEnd"] for h in m["hooks"])


# ── 셸 명령 · 커밋 (DAY 26) ─────────────────────────────────────────
# DAY 25 의 훅은 Edit·Write 만 봤다. 셸로 고친 파일은 그냥 지나갔고, 그날
# 이 도구를 만들면서 실제로 파이썬 스크립트로 파일을 고쳤다.
def _git(repo: Path, *args: str, env: dict | None = None):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=30)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "core.autocrlf", "false")
    for name in ("a.txt", "b.txt"):
        (r / name).write_text(name + "\n", encoding="utf-8")
    # git 훅은 **그 저장소의** scripts/claims.py 를 부른다.
    (r / "scripts").mkdir()
    (r / "scripts" / "claims.py").write_bytes(SCRIPT.read_bytes())
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "init")
    return r


def shell(session: str, repo: Path, command: str, tool: str = "Bash") -> dict:
    return {"session_id": session, "tool_name": tool, "cwd": str(repo),
            "tool_input": {"command": command}}


def edit_in(session: str, repo: Path, name: str) -> dict:
    return {"session_id": session, "tool_name": "Edit", "cwd": str(repo),
            "tool_input": {"file_path": str(repo / name)}}


def run_in(env, cwd: Path, *args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                       text=True, encoding="utf-8", env=env, cwd=cwd, timeout=30)
    return p.returncode, p.stdout, p.stderr


@pytest.mark.parametrize("command,tool", [
    ("echo x > a.txt", "Bash"),
    ("echo x >> ./a.txt", "Bash"),
    ("sed -i 's/a/b/' a.txt", "Bash"),
    ("rm -f a.txt", "Bash"),
    ("mv a.txt c.txt", "Bash"),
    ("cp b.txt a.txt", "Bash"),
    ("cd . && tee a.txt < b.txt", "Bash"),
    ("git checkout -- a.txt", "Bash"),
    ("Set-Content -Path a.txt -Value x", "PowerShell"),
    ("Remove-Item a.txt", "PowerShell"),
])
def test_shell_writes_to_another_sessions_file_are_blocked(env, repo, command, tool):
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    code, _, err = run(env, "hook", "pre-tool-use",
                       stdin=shell("B", repo, command, tool))
    assert code == 2, f"셸 쓰기가 통과했다: {command}"
    assert "a.txt" in err and "세션 A" in err


@pytest.mark.parametrize("command", [
    "cat a.txt",
    "grep a a.txt > out.txt",
    "cp a.txt out.txt",
    "git diff a.txt",
    "echo x > b.txt",
])
def test_reading_or_writing_elsewhere_is_allowed(env, repo, command):
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    code, _, err = run(env, "hook", "pre-tool-use", stdin=shell("B", repo, command))
    assert code == 0, err


def test_post_hook_catches_a_write_the_command_did_not_show(env, repo):
    """스크립트 안의 쓰기는 명령에 안 보인다 — 전후로 파일을 비교해서 잡는다."""
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    code, _, _ = run(env, "hook", "pre-tool-use",
                     stdin=shell("B", repo, "python fix.py"))
    assert code == 0
    (repo / "a.txt").write_text("B 가 스크립트로 덮었다\n", encoding="utf-8")
    code, _, err = run(env, "hook", "post-tool-use",
                       stdin=shell("B", repo, "python fix.py"))
    assert code == 2 and "a.txt" in err and "세션 A" in err


def test_files_changed_by_the_shell_get_this_sessions_name_tag(env, repo):
    """셸로 고친 파일도 이름표가 붙어야 다른 세션의 Edit 를 막는다."""
    run(env, "hook", "pre-tool-use", stdin=shell("B", repo, "python gen.py"))
    (repo / "b.txt").write_text("changed\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    code, _, _ = run(env, "hook", "post-tool-use",
                     stdin=shell("B", repo, "python gen.py"))
    assert code == 0
    for name in ("b.txt", "new.txt"):
        code, _, err = run(env, "hook", "pre-tool-use",
                           stdin=edit_in("A", repo, name))
        assert code == 2 and "세션 B" in err, name


def test_owner_editing_during_the_command_is_not_reported(env, repo):
    """그 사이 주인 세션이 Edit 로 고친 것은 주인의 일이다."""
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    run(env, "hook", "pre-tool-use", stdin=shell("B", repo, "sleep 1"))
    import time as _t
    _t.sleep(0.05)
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    (repo / "a.txt").write_text("A 의 편집\n", encoding="utf-8")
    code, _, err = run(env, "hook", "post-tool-use",
                       stdin=shell("B", repo, "sleep 1"))
    assert code == 0, err


@pytest.mark.parametrize("command,stage", [
    ("git commit -m wip", True),
    ("git -c core.editor=true commit -m wip", True),
    ("git commit -am wip", False),
])
def test_committing_another_sessions_file_is_blocked(env, repo, command, stage):
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    (repo / "a.txt").write_text("A 가 고치는 중\n", encoding="utf-8")
    if stage:
        _git(repo, "add", "a.txt")
    code, _, err = run(env, "hook", "pre-tool-use", stdin=shell("B", repo, command))
    assert code == 2 and "커밋" in err and "a.txt" in err


def test_precommit_command_blocks_only_other_sessions(env, repo):
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    env["CLAUDE_CODE_SESSION_ID"] = "B"
    code, _, err = run_in(env, repo, "precommit")
    assert code == 3 and "a.txt" in err
    env["CLAUDE_CODE_SESSION_ID"] = "A"
    assert run_in(env, repo, "precommit")[0] == 0
    env["CLAUDE_CODE_SESSION_ID"] = "B"
    env["CLAIMS_OVERRIDE"] = "1"
    assert run_in(env, repo, "precommit")[0] == 0


def test_git_hook_blocks_a_real_commit(env, repo):
    """훅 배선까지 — 사람이 터미널에서 하는 커밋도 여기를 지난다."""
    env["AI_CLAIMS_GIT_HOOK"] = "1"
    code, out, _ = run_in(env, repo, "install-git-hook")
    assert code == 0 and out.strip() == "installed"
    assert run_in(env, repo, "install-git-hook")[1].strip() == "current"
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    p = _git(repo, "commit", "-m", "B 의 커밋", env={**env, "CLAUDE_CODE_SESSION_ID": "B"})
    assert p.returncode != 0, "다른 세션의 파일이 커밋됐다"
    assert "a.txt" in p.stderr
    p = _git(repo, "commit", "-m", "A 의 커밋", env={**env, "CLAUDE_CODE_SESSION_ID": "A"})
    assert p.returncode == 0, p.stderr


def test_git_hook_never_overwrites_someone_elses_hook(env, repo):
    env["AI_CLAIMS_GIT_HOOK"] = "1"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    code, out, _ = run_in(env, repo, "install-git-hook")
    assert out.strip() == "foreign" and code == 1
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"


def test_git_hook_passes_when_the_tool_itself_breaks(env, repo):
    """막는 쪽으로 틀리지 않는다 — 표가 깨져도 커밋은 된다."""
    env["AI_CLAIMS_GIT_HOOK"] = "1"
    run_in(env, repo, "install-git-hook")
    Path(env["AI_CLAIMS_FILE"]).write_text("{{{ broken", encoding="utf-8")
    (repo / "b.txt").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    p = _git(repo, "commit", "-m", "ok", env={**env, "CLAUDE_CODE_SESSION_ID": "B"})
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("bad", ["not json", "", '{"tool_name": "Bash", "tool_input": 5}',
                                 '{"tool_name": "Bash", "session_id": "B"}'])
def test_broken_shell_input_never_blocks(env, bad):
    assert run(env, "hook", "pre-tool-use", stdin=bad)[0] == 0
    assert run(env, "hook", "post-tool-use", stdin=bad)[0] == 0


def test_project_dir_fast_path_finds_the_same_repo(env, repo):
    """훅은 git 을 띄우지 않고 `CLAUDE_PROJECT_DIR` 로 저장소를 안다 — 같은 답이어야 한다."""
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    run(env, "hook", "pre-tool-use", stdin=edit_in("A", repo, "a.txt"))
    code, _, err = run(env, "hook", "pre-tool-use",
                       stdin=shell("B", repo, "echo x > a.txt"))
    assert code == 2 and "a.txt" in err


def test_fast_path_does_not_swallow_a_nested_repo(repo, monkeypatch):
    """프로젝트 폴더 안의 **다른 저장소**에서 도는 명령은 그 저장소 기준이다 —
    빠른 길(`CLAUDE_PROJECT_DIR`)이 바깥 저장소로 착각하면 안 된다."""
    inner = repo / "vendor" / "lib"
    inner.mkdir(parents=True)
    _git(inner, "init", "-q")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import claims
        claims._dirs.clear()
        assert claims.repo_root(repo / "scripts") == repo.resolve()
        assert claims.repo_root(inner) == inner.resolve()
        assert claims.git_common(inner) == (inner / ".git").resolve()
    finally:
        sys.path.remove(str(SCRIPT.parent))
