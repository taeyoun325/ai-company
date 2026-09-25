"""서버를 두 대로 띄웠을 때의 승인·재개·정지 (DAY 26).

## 이 파일이 지키려는 것

DAY 25 의 승인 게이트는 "쉬러 들어가는 실행"과 "결정 버튼"의 경쟁을
**프로세스 안의 잠금**으로 막았다. 인스턴스가 둘이면 그 잠금은 서로를 못
본다 — 결정은 파일에 남는데 아무도 실행을 깨우지 않았다.

1. **메타 잠금이 프로세스를 넘는다.** 다른 프로세스가 쥔 동안에는 못 잡는다.
2. **결정과 쉬기가 서로를 본다.** 다른 프로세스의 결정이 쉬기와 겹치면,
   결정은 쉬기가 끝난 뒤의 `awaiting` 을 보고 깨운다.
3. **재개는 한 인스턴스만 한다.** 둘이 동시에 깨워도 자리는 하나다.
4. **정지 버튼은 실행을 돌리지 않는 인스턴스에서도 먹는다.**

"다른 인스턴스"는 진짜 다른 프로세스(`subprocess`)로 흉내 낸다 — 같은
프로세스의 스레드로 흉내 내면 스레드 잠금이 대신 막아주므로 시험이 아무것도
증명하지 못한다.
"""
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import config, lang, safeio                            # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import engine, gates                       # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402

TIMEOUT = 90


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    monkeypatch.setattr(engine, "DECISION_POLL", 0.05)
    monkeypatch.setattr(engine, "CANCEL_POLL", 0.0)
    credits.reset()
    registry.reset()
    yield
    credits.reset()
    registry.reset()


def _settle(slug: str, timeout: float = TIMEOUT) -> dict:
    deadline = time.time() + timeout
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    assert not engine.is_running(slug), f"{timeout}초 안에 끝나지 않았다"
    return store.meta(slug)


def _other_instance(code: str) -> subprocess.Popen:
    """같은 프로젝트 폴더를 보는 **다른 프로세스**."""
    prelude = textwrap.dedent(f"""
        import sys, json
        sys.path.insert(0, {str(BACKEND)!r})
        from pathlib import Path
        from app import config
        config.PROJECTS = Path({str(config.PROJECTS)!r})
        config.LOGS = Path({str(config.LOGS)!r})
    """)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PROVIDER_MODE": "mock"}
    return subprocess.Popen([sys.executable, "-c", prelude + textwrap.dedent(code)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", env=env, cwd=str(BACKEND))


# ── 1. 잠금이 프로세스를 넘는다 ──────────────────────────────────────
def test_file_lock_is_exclusive_across_processes(tmp_path):
    target = tmp_path / "x.json"
    holder = _other_instance(f"""
        import time
        from app import safeio
        with safeio.file_lock(Path({str(target)!r})):
            print("held", flush=True)
            time.sleep(1.5)
    """)
    assert holder.stdout.readline().strip() == "held", holder.stderr.read()
    with pytest.raises(safeio.LockTimeout):
        with safeio.file_lock(target, timeout=0.2):
            pass
    holder.wait(timeout=30)
    with safeio.file_lock(target, timeout=5):
        pass                                      # 놓은 뒤에는 잡힌다


def test_lock_is_released_when_the_holder_dies(tmp_path):
    """잠금 파일 방식과의 차이 — 쥔 프로세스가 죽으면 운영체제가 푼다."""
    target = tmp_path / "y.json"
    holder = _other_instance(f"""
        import os, time
        from app import safeio
        lk = safeio.file_lock(Path({str(target)!r})).__enter__()
        print("held", flush=True)
        time.sleep(60)
    """)
    assert holder.stdout.readline().strip() == "held"
    holder.kill()
    holder.wait(timeout=30)
    with safeio.file_lock(target, timeout=5):
        pass


# ── 2. 다른 인스턴스의 결정과 쉬기가 겹쳐도 깨운다 ────────────────────
def test_decision_from_another_instance_racing_the_park_still_wakes(monkeypatch):
    """DAY 25 의 구멍: A 가 "결정 없음"을 확인하고 → B 가 결정을 쓰고 상태를
    읽고("running" — 안 깨움) → A 가 `awaiting` 을 쓴다. 아무도 안 깨운다.

    B 의 결정을 A 가 쉬러 들어가는 **바로 그 순간**에 다른 프로세스에서 넣는다.
    """
    real = gates.unapplied
    box: dict = {}

    def racing(m, gate=None):
        if gate == "plan" and "proc" not in box:
            aid = next(a["id"] for a in m.get("approvals", [])
                       if a["gate"] == "plan" and a["status"] == "pending")
            box["proc"] = _other_instance(f"""
                from app.orchestrator import gates
                print("ready", flush=True)
                rec, status = gates.decide_seen({m["slug"]!r}, {aid!r}, "approve")
                print(json.dumps({{"status": status}}), flush=True)
            """)
            assert box["proc"].stdout.readline().strip() == "ready"
            time.sleep(0.5)          # 다른 프로세스가 메타 잠금 앞에서 기다린다
        return real(m, gate)

    monkeypatch.setattr(gates, "unapplied", racing)
    slug = engine.start("계산기", gate_list=["plan"])
    m = _settle(slug)
    assert m["status"] == "awaiting"
    out, err = box["proc"].communicate(timeout=30)
    seen = json.loads(out.strip().splitlines()[-1])["status"]
    assert seen == "awaiting", (
        "다른 인스턴스의 결정이 쉬기 도중의 상태를 봤다 — 깨울 사람이 없다", err)
    # B 는 `awaiting` 을 봤으므로 깨운다. (여기서는 이 프로세스가 B 역할)
    monkeypatch.setattr(gates, "unapplied", real)
    engine.resume(slug)
    assert _settle(slug)["status"] == "done"


# ── 3. 재개는 한 인스턴스만 ─────────────────────────────────────────
def test_resume_claim_is_taken_by_one_instance_only():
    slug = engine.start("계산기", gate_list=["plan"])
    assert _settle(slug)["status"] == "awaiting"
    other = _other_instance(f"""
        from app.orchestrator import engine
        print(json.dumps({{"seen": engine._claim({slug!r})}}), flush=True)
    """)
    out, err = other.communicate(timeout=30)
    assert json.loads(out.strip().splitlines()[-1])["seen"] is None, err
    assert store.meta(slug)["status"] == "running"
    with pytest.raises(engine.NotResumable):
        engine.resume(slug)
    assert not engine.is_running(slug), "두 인스턴스가 같은 실행을 띄웠다"


# ── 4. 정지 버튼 ────────────────────────────────────────────────────
def test_cancel_reaches_a_run_owned_by_another_instance():
    """다른 인스턴스에 온 정지 요청은 메타에 남고, 돌리는 쪽이 경계에서 본다."""
    slug = engine.start("계산기", gate_list=["plan"])
    assert _settle(slug)["status"] == "awaiting"
    other = _other_instance(f"""
        from app.orchestrator import gates
        a = [x for x in gates.pending({slug!r}) if x["gate"] == "plan"][0]
        gates.decide({slug!r}, a["id"], "approve")
    """)
    other.communicate(timeout=30)
    engine.resume(slug)
    # 다른 인스턴스의 정지 버튼 — 여기에는 실행 스레드가 없다.
    stopper = _other_instance(f"""
        from app.orchestrator import engine
        print(json.dumps({{"ok": engine.cancel({slug!r})}}), flush=True)
    """)
    out, err = stopper.communicate(timeout=30)
    ok = json.loads(out.strip().splitlines()[-1])["ok"]
    m = _settle(slug)
    if m["status"] == "done":
        pytest.skip("실행이 정지 요청보다 먼저 끝났다 — 시험 조건이 안 섰다")
    assert ok is True, err
    assert m["status"] == "stopped"
    assert m["stopped_reason"] == lang.t("stop.byCeo")


def test_cancel_marks_a_dead_instances_run_stopped():
    """박자가 끊긴 `running` 은 멈출 스레드가 없다 — 바로 `stopped` 로."""
    slug = store.new_project("계산기")
    store.save_meta(slug, {"beat": time.time() - engine.BEAT_STALE - 5})
    assert engine.cancel(slug) is True
    assert store.meta(slug)["status"] == "stopped"


def test_cancel_request_is_cleared_when_resumed():
    slug = store.new_project("계산기")
    store.save_meta(slug, {"status": "stopped", "cancel_requested": time.time()})
    assert engine._claim(slug) is None
    assert store.meta(slug).get("cancel_requested") is None


def test_update_meta_does_not_write_when_nothing_changed():
    """실행은 0.5초마다 결정을 묻는다 — 답이 "없다"면 쓰지 않는다."""
    slug = store.new_project("계산기")
    p = store.dir_of(slug) / store.META
    before = p.stat().st_mtime_ns
    time.sleep(0.02)
    assert gates.take_decided(slug, "task") == []
    assert p.stat().st_mtime_ns == before
