"""파일 롤백 (app/tools/project_fs.py 의 raw_read · restore_files).

## 이 파일이 지키려는 것

반려가 쌓여 태스크를 포기할 때, 그 태스크가 건드린 파일은 **시작 전
상태로** 돌아가야 한다. 원래 없던 파일이면 지워지고, 원래 있던 파일이면
그 내용으로 돌아가야 한다 — 어느 쪽이든 반려된 시도의 흔적이 남으면 안
된다.

전체 오케스트레이터를 통한 통합 검증은 `test_orchestrator.py` 의
`test_giving_up_on_a_task_rolls_its_files_back` 가 한다. 여기서는
`project_fs` 의 두 함수 자체를 직접 본다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config                                          # noqa: E402
from app.database import store                                  # noqa: E402
from app.tools import project_fs as pfs                          # noqa: E402


@pytest.fixture
def slug(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    s = store.new_project("롤백 테스트")
    pfs.use(s)
    try:
        yield s
    finally:
        pfs.release()


def test_raw_read_returns_none_for_a_missing_file(slug):
    assert pfs.raw_read("src/nope.py") is None


def test_raw_read_ignores_permissions(slug):
    """이 함수는 시작 전 상태를 **기록**하는 것이지 누군가에게 보여주는
    것이 아니다 — 그래서 직원 권한 검사가 없어야 한다."""
    pfs.write("tests/only_analyst.py", "x = 1\n", "analyst")
    assert pfs.raw_read("tests/only_analyst.py") == "x = 1\n"


def test_restore_files_deletes_a_file_that_did_not_exist_before(slug):
    pfs.write("src/new.py", "print(1)\n", "developer")
    assert "src/new.py" in store.files_of(slug)

    restored = pfs.restore_files({"src/new.py": None})

    assert restored == ["src/new.py"]
    assert "src/new.py" not in store.files_of(slug)


def test_restore_files_reverts_an_overwritten_file(slug):
    pfs.write("src/calc.py", "def add(a, b):\n    return a + b\n", "developer")
    baseline = {"src/calc.py": pfs.raw_read("src/calc.py")}
    pfs.write("src/calc.py", "def add(a, b):\n    return a - b  # 버그\n",
              "developer")

    restored = pfs.restore_files(baseline)

    assert restored == ["src/calc.py"]
    assert pfs.raw_read("src/calc.py") == baseline["src/calc.py"]


def test_restore_files_is_a_no_op_when_content_already_matches(slug):
    pfs.write("src/calc.py", "x = 1\n", "developer")
    baseline = {"src/calc.py": pfs.raw_read("src/calc.py")}

    assert pfs.restore_files(baseline) == []
