"""생성된 코드를 가두는 샌드박스 (DAY 27).

Cloud Run 에서 잰 사실: 네트워크만 끊긴 자식 프로세스도 서버와 같은
사용자라서 계정 DB·다른 테넌트의 프로젝트·서버의 환경변수에 닿았다.
"""
import shutil
import sys

import pytest

from app import deploy
from app.orchestrator import isolation, runner


@pytest.fixture
def saas_signed(monkeypatch):
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    monkeypatch.setenv("SANDBOXED", "1")


def test_saas_refuses_to_run_without_a_filesystem_sandbox(saas_signed, monkeypatch):
    """서명(SANDBOXED=1)이 있어도 가둘 수 없으면 돌리지 않는다.

    네트워크만 끊고 돌리던 옛 동작으로 조용히 내려가면, 요구사항 한 줄로
    남의 계정을 가져가는 길이 열린다."""
    monkeypatch.setattr(isolation, "probe_sandbox", lambda: (False, "bwrap 없음"))
    reason = deploy.allow_code_execution()
    assert reason is not None and "bwrap 없음" in reason


def test_blocked_run_reports_it_did_not_run(saas_signed, monkeypatch, tmp_path):
    monkeypatch.setattr(isolation, "probe_sandbox", lambda: (False, "bwrap 없음"))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n")
    r = runner.run(tmp_path)
    assert r["blocked"] and not r["ok"] and r["fs_isolated"] is False
    assert runner.run_entry(tmp_path, "src/main.py")["blocked"]


def test_sandbox_shows_only_the_project(monkeypatch, tmp_path):
    """새 루트에는 시스템(읽기 전용)과 **자기 프로젝트 하나**만 들어간다."""
    monkeypatch.setattr(isolation, "probe_sandbox", lambda: (True, "ok"))
    monkeypatch.delenv(isolation.ENV_FLAG, raising=False)
    cmd, rep = isolation.sandbox(["python", "-V"], tmp_path)
    assert rep == {"network": True, "filesystem": True, "detail": "ok"}
    i = cmd.index("bwrap")
    args = cmd[i:cmd.index("--", i)]
    assert "--unshare-all" in args and "--die-with-parent" in args
    binds = [args[k + 1] for k, a in enumerate(args) if a in ("--bind", "--ro-bind")]
    wd = str(tmp_path.resolve()) if sys.platform != "win32" else str(tmp_path)
    assert any(b.rstrip("\\/") == wd.rstrip("\\/") or b == str(tmp_path) for b in binds)
    for secret in ("/app", "/home", "/mnt", "/root", "/"):
        assert secret not in binds, f"{secret} 가 샌드박스에 보인다"
    assert cmd[-2:] == ["python", "-V"]


def test_sandbox_falls_back_to_network_only_off_linux(monkeypatch, tmp_path):
    """로컬 개발 머신(윈도우·맥)의 옛 동작은 그대로다."""
    monkeypatch.setattr(isolation, "probe_sandbox", lambda: (False, "리눅스 아님"))
    _cmd, rep = isolation.sandbox(["echo"], tmp_path)
    assert rep["filesystem"] is False


@pytest.mark.skipif(sys.platform != "linux" or shutil.which("bwrap") is None,
                    reason="bubblewrap 은 리눅스에서만 잴 수 있다")
def test_real_sandbox_hides_the_server(tmp_path):     # pragma: no cover - linux
    isolation.probe_sandbox.cache_clear()
    ok, why = isolation.probe_sandbox()
    if not ok:
        pytest.skip(why)
    (tmp_path / "x.txt").write_text("mine")
    code = ("import os,socket;"
            "print(open('x.txt').read());"
            "print(os.path.exists('/app'), os.path.exists('/home/company'));"
            "s=socket.socket();s.settimeout(2);"
            "print(s.connect_ex(('169.254.169.254',80)))")
    import subprocess
    cmd, rep = isolation.sandbox([sys.executable, "-I", "-c", code], tmp_path)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.split()
    assert out[0] == "mine" and out[1:3] == ["False", "False"] and out[3] != "0"


# ── 트레이스 보관 (DAY 27) ─────────────────────────────────────────
def test_past_run_log_survives_losing_the_local_disk(tmp_path, monkeypatch):
    """Cloud Run 은 쉬면 로컬 디스크를 버린다. 지난 실행의 작업 로그가
    빈 화면이 되면 안 된다."""
    from app import bus, config
    logs, archive = tmp_path / "logs", tmp_path / "archive"
    monkeypatch.setattr(config, "LOGS", logs)
    monkeypatch.setenv("TRACE_ARCHIVE_DIR", str(archive))
    monkeypatch.setattr(bus, "_archived", {})
    logs.mkdir()
    (logs / "r1.jsonl").write_text('{"id": 1, "run": "r1", "type": "message"}\n',
                                   encoding="utf-8")
    assert bus.archive_traces() == 1
    assert bus.archive_traces() == 0, "바뀌지 않은 파일을 다시 올리면 안 된다"
    (logs / "r1.jsonl").unlink()                   # 인스턴스가 바뀌었다
    assert [e["id"] for e in bus.read_trace("r1")] == [1]


def test_without_archive_setting_nothing_changes(tmp_path, monkeypatch):
    from app import bus, config
    monkeypatch.setattr(config, "LOGS", tmp_path)
    monkeypatch.delenv("TRACE_ARCHIVE_DIR", raising=False)
    assert bus.archive_traces() == 0
    assert bus.read_trace("nope") == []
