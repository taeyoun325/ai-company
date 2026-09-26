"""배포로 끊긴 실행을 잇는다 (DAY 27).

Cloud Run 인계는 몇 초면 끝난다. 끊긴 실행의 박자는 아직 싱싱해서, 박자로만
판단하던 기동 정리가 그것을 건너뛰었다 — 다음 재시작까지 '진행 중' 좀비.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config                                          # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import engine                              # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.delenv("SOLE_WRITER", raising=False)
    calls = []
    monkeypatch.setattr(engine, "resume", lambda slug, owner="local": calls.append((slug, owner)))
    return calls


def _interrupted(done=1, rounds=2) -> str:
    slug = store.new_project("계산기", owner="alice")
    store.save_meta(slug, {"status": "running", "beat": time.time(),
                           "checkpoint": {"done": ["t1"][:done], "rounds": rounds,
                                          "stage": "tasks"}})
    return slug


def test_fresh_beat_is_left_alone_without_the_sole_writer_guarantee():
    """compose·로컬: 둘이 떠 있을 수 있으니 박자가 싱싱하면 건드리지 않는다."""
    slug = _interrupted()
    assert engine.sweep_stale_runs() == []
    assert store.meta(slug)["status"] == "running"
    assert engine.resume_interrupted([slug]) == []


def test_sole_writer_stops_and_resumes_a_run_cut_by_a_deploy(monkeypatch, _isolated):
    monkeypatch.setenv("SOLE_WRITER", "1")
    slug = _interrupted()
    assert engine.sweep_stale_runs() == [slug]
    assert engine.resume_interrupted([slug]) == [slug]
    assert _isolated == [(slug, "alice")], "주인 그대로 이어 돈다"


def test_a_run_that_keeps_dying_at_the_same_point_is_not_resumed_forever(monkeypatch, _isolated):
    """실행이 인스턴스를 죽이는 경우 이어 돌리면 기동 → 죽음이 끝없이 돈다."""
    monkeypatch.setenv("SOLE_WRITER", "1")
    slug = _interrupted()
    for _ in range(engine.AUTO_RESUME_MAX):
        store.save_meta(slug, {"status": "running"})
        engine.sweep_stale_runs()
        assert engine.resume_interrupted([slug]) == [slug]
    store.save_meta(slug, {"status": "running"})
    engine.sweep_stale_runs()
    assert engine.resume_interrupted([slug]) == []
    m = store.meta(slug)
    assert m["status"] == "stopped" and "자동" in m["stopped_reason"]


def test_progress_resets_the_count(monkeypatch, _isolated):
    """배포 여러 번에 걸친 긴 실행은 진척이 있는 한 계속 이어진다."""
    monkeypatch.setenv("SOLE_WRITER", "1")
    slug = _interrupted(rounds=1)
    for r in range(1, 6):
        store.save_meta(slug, {"status": "running",
                               "checkpoint": {"done": [], "rounds": r, "stage": "tasks"}})
        engine.sweep_stale_runs()
        assert engine.resume_interrupted([slug]) == [slug]
    assert len(_isolated) == 5
