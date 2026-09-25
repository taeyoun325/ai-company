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
    assert any("session-start" in h["command"]
               for m in hooks["SessionStart"] for h in m["hooks"])
    assert any("session-end" in h["command"]
               for m in hooks["SessionEnd"] for h in m["hooks"])
