"""파일이 잘리지 않게 쓰는가 (DAY 22 · app/safeio.py).

## 이 파일이 지키려는 것

저장이 전부 `write_text()` 한 줄이었다. 그 한 줄은 파일을 **0으로 자른 뒤**
새 내용을 쓴다. 그 사이에 프로세스가 죽으면 빈 파일이 남는다.

걸리는 파일들이 하필 중요한 것들이다 — 지갑 · 프로젝트 메타 · MANUAL
대화 · 고객 키 · 인사 기록. "서버가 죽었더니 잔액이 0이 됐다"는 사고는
여기서 난다.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import safeio                                         # noqa: E402


def test_failure_leaves_the_old_content(tmp_path, monkeypatch):
    """새로 쓰다 죽어도 **옛 내용이 그대로** 남아야 한다."""
    target = tmp_path / "wallet.json"
    safeio.write_json(target, {"balance": 900})

    def boom(*_a, **_k):
        raise OSError("디스크가 찼다")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        safeio.write_json(target, {"balance": 0})

    assert json.loads(target.read_text(encoding="utf-8")) == {"balance": 900}


def test_failure_does_not_leave_rubbish(tmp_path, monkeypatch):
    """임시 파일을 남기면 폴더가 쓰레기로 찬다."""
    target = tmp_path / "wallet.json"
    safeio.write_json(target, {"balance": 900})

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        safeio.write_json(target, {"balance": 0})

    leftovers = [p.name for p in tmp_path.iterdir()
                 if p.name.startswith(".wallet.json")]
    assert leftovers == [], f"임시 파일이 남았다: {leftovers}"


def test_writes_land(tmp_path):
    target = tmp_path / "nested" / "a.json"
    safeio.write_json(target, {"x": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}


def test_staff_records_survive_a_failed_write(tmp_path, monkeypatch):
    """헬퍼만 맞고 부르는 쪽이 옛 방식이면 아무 의미가 없다.

    지갑은 DAY 22 에 SQLite 로 옮겼으므로 여기서는 아직 파일인 것을
    본다 — 인사 기록.
    """
    from app.agents import staff

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    staff.reset()
    staff.rename("owner", "developer", "김코딩")
    before = staff.store_path().read_text(encoding="utf-8")

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    staff.rename("owner", "developer", "덮어쓰기 시도")

    assert staff.store_path().read_text(encoding="utf-8") == before
    staff.reset()
    assert staff.name_of("owner", "developer") == "김코딩"


def test_project_meta_survives_a_failed_write(tmp_path, monkeypatch):
    """메타가 잘리면 산출물은 멀쩡한데 프로젝트가 '없는 프로젝트'가 된다."""
    from app import config
    from app.database import store

    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("메타가 살아남아야 한다")
    before = store.meta(slug)

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        store.save_meta(slug, {"status": "done"})

    assert store.exists(slug)
    assert store.meta(slug)["status"] == before["status"]
