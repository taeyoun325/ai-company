"""프로젝트 저장과 색인 (지시서 §12 · §5).

## 이 파일이 지키려는 것

**파일이 진실이고 색인은 사본이다.** 이 규칙은 말로만 두면 지켜지지
않는다. 색인을 지워도, 깨뜨려도, 산출물이 남아 있고 목록이 되살아나는지
실제로 확인한다.

DB 를 진실로 두면 둘이 어긋나는 날 어느 쪽이 맞는지 알 수 없다.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config                                          # noqa: E402
from app.database import index, store                            # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    index.close()
    yield
    index.close()


def _make(requirement="계산기를 만들어주세요", **patch) -> str:
    slug = store.new_project(requirement, owner=patch.pop("owner", "local"))
    if patch:
        store.save_meta(slug, patch)
    return slug


# ── 저장 ───────────────────────────────────────────────────────────
def test_new_project_creates_all_areas():
    slug = _make()
    for area in store.AREAS:
        assert (store.dir_of(slug) / area).is_dir(), f"{area}/ 가 없다"


def test_meta_round_trips():
    slug = _make(status="done", score=87)
    m = store.meta(slug)
    assert m["status"] == "done" and m["score"] == 87


def test_files_of_excludes_tool_droppings():
    """__pycache__ 나 .meta.json 을 산출물로 보여주면, CEO 는 우리가
    만든 부산물을 납품물로 읽는다."""
    slug = _make()
    (store.dir_of(slug) / "src" / "calc.py").write_text("x = 1", encoding="utf-8")
    (store.dir_of(slug) / "src" / "__pycache__").mkdir()
    (store.dir_of(slug) / "src" / "__pycache__" / "x.pyc").write_bytes(b"x")
    (store.dir_of(slug) / "pytest.ini").write_text("[pytest]", encoding="utf-8")
    assert store.files_of(slug) == ["src/calc.py"]


def test_read_file_rejects_escape():
    slug = _make()
    with pytest.raises(ValueError):
        store.read_file(slug, "../../secret.txt")


def test_delete_project_refuses_to_escape():
    """slug 는 사용자 입력에서 올 수 있다. `../..` 하나면 저장소 밖을 지운다."""
    assert store.delete_project("../..") is False
    assert store.delete_project("없는프로젝트") is False


def test_delete_project_removes_files_and_index():
    slug = _make()
    assert index.get(slug) is not None
    assert store.delete_project(slug) is True
    assert not store.dir_of(slug).exists()
    assert index.get(slug) is None, "색인에 없는 유령 항목이 남았다"


# ── 파일 이력 ──────────────────────────────────────────────────────
def test_version_history_and_diff():
    slug = _make()
    p = store.dir_of(slug) / "src" / "calc.py"
    p.write_text("old\n", encoding="utf-8")
    store.snapshot_version(slug, "src/calc.py", "old\n", note="덮어쓰기 직전")
    p.write_text("new\n", encoding="utf-8")

    versions = store.versions(slug, "src/calc.py")
    assert [v["version"] for v in versions] == [1, 0], "마지막은 항상 현재 파일이다"
    rows = store.diff(slug, "src/calc.py", 1, 0)
    assert any(r["kind"] == "add" and "new" in r["text"] for r in rows)
    assert any(r["kind"] == "del" and "old" in r["text"] for r in rows)


def test_unknown_version_raises():
    slug = _make()
    with pytest.raises(ValueError):
        store.version_text(slug, "src/calc.py", 99)


# ── 색인 ───────────────────────────────────────────────────────────
def test_save_meta_updates_the_index():
    slug = _make(status="done", score=91)
    row = index.get(slug)
    assert row is not None and row["status"] == "done" and row["score"] == 91


def test_search_filters_by_status():
    _make("첫 번째", status="done")
    _make("두 번째", status="stopped")
    done = index.search(status="done")
    assert done["total"] == 1
    assert done["projects"][0]["status"] == "done"


def test_search_filters_by_owner():
    _make("내 것", owner="me")
    _make("남의 것", owner="other")
    assert index.search(owner="me")["total"] == 1


def test_search_by_text():
    _make("계산기를 만들어주세요")
    _make("블로그를 만들어주세요")
    assert index.search(q="계산기")["total"] == 1


def test_search_paginates_and_reports_total():
    """한 페이지를 받아보고 마지막인지 판단하면, 마지막 페이지에서
    한 번 더 요청하게 된다."""
    for i in range(5):
        _make(f"프로젝트 {i}")
    page = index.search(limit=2, offset=0)
    assert len(page["projects"]) == 2
    assert page["total"] == 5


def test_sort_key_is_whitelisted():
    """정렬 키를 문자열 그대로 SQL 에 넣으면 그게 곧 주입 통로다.
    자리표시자로는 컬럼명을 넘길 수 없어서 화이트리스트가 유일한 방어다."""
    _make()
    r = index.search(sort="'; DROP TABLE projects; --")
    assert r["total"] == 1, "색인이 살아 있어야 한다"
    assert index.search()["total"] == 1


def test_search_by_text_is_parameterised():
    _make("계산기")
    r = index.search(q="%' OR '1'='1")
    assert r["total"] == 0, "검색어가 SQL 로 해석됐다"


def test_stats_sums_cost_and_counts():
    _make("A", status="done", cost=0.50, credits=50, score=90)
    _make("B", status="stopped", cost=0.25, credits=25, score=40)
    s = index.stats()
    assert s["projects"] == 2
    assert s["cost"] == pytest.approx(0.75)
    assert s["done"] == 1 and s["stopped"] == 1


def test_mock_projects_are_counted_separately():
    """Mock 으로 만든 산출물이 실제 결과와 같은 통계에 섞이면,
    '우리는 N개를 만들었다'가 거짓말이 된다."""
    _make("진짜", mock=False)
    _make("가짜", mock=True)
    assert index.stats()["mock"] == 1


# ── 파일이 진실이다 ────────────────────────────────────────────────
def test_rebuild_recovers_the_index_from_disk():
    slugs = [_make(f"프로젝트 {i}") for i in range(3)]
    with index.conn() as c:
        c.execute("DELETE FROM projects")
    assert index.search()["total"] == 0

    assert index.rebuild() == 3
    assert index.search()["total"] == 3
    assert all(index.get(s) for s in slugs)


def test_ensure_ready_rebuilds_when_index_is_empty():
    """DB 파일만 지워졌을 때 목록이 비어 보이면, 사용자는 산출물을
    잃어버렸다고 생각한다."""
    _make()
    index.close()
    index.path().unlink(missing_ok=True)
    out = index.ensure_ready()
    assert out["rebuilt"] == 1


def test_search_falls_back_to_disk_when_the_index_is_broken(monkeypatch):
    """색인이 깨졌으면 디스크가 진실이다. 빈 화면 대신 파일에서 읽는다."""
    _make("소중한 프로젝트")

    def boom(*a, **kw):
        raise sqlite3.DatabaseError("색인 손상")

    monkeypatch.setattr(index, "conn", boom)
    r = index.search()
    assert r["source"] == "disk"
    assert r["total"] == 1


def test_stats_falls_back_to_disk_too(monkeypatch):
    _make("A", cost=0.5)

    def boom(*a, **kw):
        raise sqlite3.DatabaseError("색인 손상")

    monkeypatch.setattr(index, "conn", boom)
    assert index.stats()["projects"] == 1


def test_index_failure_does_not_lose_the_project(monkeypatch):
    """색인 쓰기가 실행을 멈추면, 검색 편의 때문에 산출물을 잃는다."""
    monkeypatch.setattr(index, "upsert", lambda m: (_ for _ in ()).throw(
        sqlite3.DatabaseError("색인 손상")))
    slug = store.new_project("그래도 남아야 한다")
    assert store.meta(slug)["requirement"] == "그래도 남아야 한다"


# ── 색인은 사본, 파일이 진실 (§12 · DAY 22) ────────────────────────
def test_list_hides_projects_whose_files_are_gone(tmp_path, monkeypatch):
    """색인에는 있는데 파일이 없는 행을 그대로 내보내면, 목록에는 있는데
    누르면 '없는 프로젝트'가 되는 항목이 남는다. 사용자는 자기가 지운
    것과 그 항목을 연결짓지 못한다."""
    from app.database import index

    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    index.close()

    slug = store.new_project("색인 정리 시험")
    index.upsert(store.meta(slug))
    assert any(p["slug"] == slug for p in index.search()["projects"])

    # 파일만 지운다 — 색인 행은 그대로 남는다
    import shutil
    shutil.rmtree(config.PROJECTS / slug)

    rows = index.search()
    assert all(p["slug"] != slug for p in rows["projects"]), "죽은 행이 보인다"
    # 사본을 진실에 맞춘다 — 다음 조회에서 또 걸러낼 필요가 없어야 한다
    assert all(p["slug"] != slug for p in index.search()["projects"])


def test_partially_emptied_index_is_refilled_from_disk(tmp_path, monkeypatch):
    """비었을 때만 채우면 부분적으로 빈 색인은 아무도 채우지 않는다.
    디스크에 있는데 색인에 없는 프로젝트는 목록에서 사라진 것과 같다."""
    from app.database import index

    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    index.close()

    kept = store.new_project("남는 것")
    lost = store.new_project("색인에서만 사라진 것")
    index.upsert(store.meta(kept))
    index.upsert(store.meta(lost))

    # 색인에서만 지운다 — 파일은 그대로다
    with index.conn() as c:
        c.execute("DELETE FROM projects WHERE slug = ?", (lost,))

    index.ensure_ready()
    slugs = {p["slug"] for p in index.search()["projects"]}
    assert lost in slugs, "디스크에 있는데 목록에서 사라졌다"
    assert kept in slugs


def test_two_projects_in_the_same_second_do_not_collide(tmp_path, monkeypatch):
    """slug 는 `시각-요구사항` 이라 1초 안에 같은 문장으로 두 번 시작하면
    같은 이름이 된다. 둘째가 첫째의 폴더에 겹쳐 쓰면, 사용자는 프로젝트
    하나를 잃었다는 사실조차 모른다."""
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    a = store.new_project("계산기를 만들어주세요")
    b = store.new_project("계산기를 만들어주세요")
    assert a != b
    assert store.exists(a) and store.exists(b)


# ── 파일이 여기까지 온 경위 (DAY 22 · docs/market.md 2순위) ────────
def test_a_revision_records_who_and_why(tmp_path, monkeypatch):
    """자유 문장 하나로는 '이 파일이 왜 세 번 고쳐졌나'를 사람이 읽어내야
    하고, 기계는 아무것도 못 한다 — 정렬도 필터도 안 된다."""
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("경위가 남아야 한다")

    store.snapshot_version(slug, "src/calc.py", "첫 판",
                           meta={"author": "developer", "round": 3,
                                 "reason": "div 가 0 을 안 막는다"})
    rows = store.versions(slug, "src/calc.py")
    first = rows[0]
    assert first["author"] == "developer"
    assert first["round"] == 3
    assert "0" in first["reason"]
    assert first["at"] > 0


def test_old_revisions_have_empty_fields_not_invented_ones(tmp_path, monkeypatch):
    """옛 판본에는 이 정보가 없다. 없는 것을 그럴듯하게 채우면 이력이
    거짓말이 된다."""
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("옛 판본")
    store.snapshot_version(slug, "src/old.py", "예전 내용", note="그때 방식")

    row = store.versions(slug, "src/old.py")[0]
    assert row["author"] == ""
    assert row["round"] == 0
    assert row["note"] == "그때 방식"


def test_writing_through_the_tools_keeps_the_trail(tmp_path, monkeypatch):
    """헬퍼만 맞고 직원이 쓰는 경로가 옛 방식이면 아무 의미가 없다."""
    from app.tools import project_fs as pfs

    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("도구를 지나가는 길")
    pfs.use(slug)
    try:
        pfs.write("src/calc.py", "def add(a, b): return a + b", "developer")
        pfs.write("src/calc.py", "def add(a, b): return a - b", "developer",
                  round=2, reason="덧셈이 뺄셈으로 되어 있다")
    finally:
        pfs.release()

    rows = store.versions(slug, "src/calc.py")
    assert rows[0]["author"] == "developer"
    assert rows[0]["round"] == 2
    assert "뺄셈" in rows[0]["reason"]
