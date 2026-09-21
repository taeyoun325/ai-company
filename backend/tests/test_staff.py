"""인사와 언어 (DAY 21 · agents/staff.py · app/lang.py).

## 이 파일이 지키려는 것

1. **핵심 자리는 비지 않는다.** 특히 검증자. 내보낼 수 있으면 화면은
   멀쩡히 돌면서 아무도 보지 않은 코드가 '통과'로 나간다. 조용히
   나빠지는 쪽이라 더 나쁘다.
2. **이름을 바꿔도 권한은 그대로다.** 개발자를 '수석 아키텍트'라고
   불러도 src/ 밖에는 못 쓴다.
3. **내보낸 직원에게 태스크가 가지 않는다.** 가면 그 태스크는 아무도
   손대지 않은 채 검증까지 흘러가 '미완성'으로 판정되고, 사용자는
   자기가 내보낸 것과 그 실패를 연결짓지 못한다.
4. **요청의 언어가 직원 프롬프트까지 간다.** 영어로 요청한 사람에게
   한국어 주석이 달린 코드를 주면, 그건 번역 문제가 아니라 쓸 수 없는
   산출물이다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import lang, tenant                                    # noqa: E402
from app.agents import employee, roles, staff                   # noqa: E402
from app.usage import credits                                   # noqa: E402

OWNER = "owner-1"
OTHER = "owner-2"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    staff.reset()
    credits.reset()
    yield
    staff.reset()
    credits.reset()


# ── 내보낼 수 있는 자리 ────────────────────────────────────────────
def test_the_verifier_cannot_be_fired():
    """제일 위험한 해고다. 없어도 화면은 돌고 산출물도 나오는데,
    아무도 보지 않은 코드가 '통과'로 나간다."""
    assert staff.can_fire(roles.VERIFIER) is False
    with pytest.raises(ValueError):
        staff.set_active(OWNER, roles.VERIFIER, False)
    assert staff.is_active(OWNER, roles.VERIFIER) is True


def test_planner_and_developer_cannot_be_fired():
    for who in (roles.PLANNER, "developer"):
        with pytest.raises(ValueError):
            staff.set_active(OWNER, who, False)


def test_refusal_says_why():
    """버튼만 막아두면 사용자는 고장인 줄 안다."""
    for who in staff.CORE:
        assert staff.fire_reason(who), f"{who} 를 못 내보내는 이유가 없다"


def test_optional_staff_can_be_fired_and_rehired():
    staff.set_active(OWNER, "writer", False)
    assert staff.is_active(OWNER, "writer") is False
    staff.set_active(OWNER, "writer", True)
    assert staff.is_active(OWNER, "writer") is True


def test_a_hand_edited_file_cannot_empty_a_core_seat():
    """저장 파일은 디스크에 있고, 디스크는 고쳐질 수 있다."""
    staff.rename(OWNER, "analyst", "누구")
    raw = staff.store_path().read_text(encoding="utf-8")
    staff.store_path().write_text(
        raw.replace('"name": "누구"', '"name": "누구", "active": false'),
        encoding="utf-8")
    staff.reset()
    assert staff.is_active(OWNER, "analyst") is True


# ── 이름 ───────────────────────────────────────────────────────────
def test_rename_does_not_touch_permissions():
    before = roles.get("developer").writes
    staff.rename(OWNER, "developer", "수석 아키텍트")
    assert staff.name_of(OWNER, "developer") == "수석 아키텍트"
    assert roles.get("developer").writes == before
    assert roles.get("developer").reads == roles.get("developer").reads


def test_names_are_per_tenant():
    staff.rename(OWNER, "developer", "김코딩")
    assert staff.name_of(OTHER, "developer") == roles.get("developer").name


def test_empty_name_restores_the_default():
    staff.rename(OWNER, "writer", "글쓴이")
    staff.rename(OWNER, "writer", "   ")
    assert staff.name_of(OWNER, "writer") == roles.get("writer").name


def test_absurdly_long_name_is_rejected():
    with pytest.raises(ValueError):
        staff.rename(OWNER, "writer", "가" * (staff.MAX_NAME + 1))


# ── 배정 ───────────────────────────────────────────────────────────
def test_fired_staff_get_no_tasks():
    credits.set_plan(OWNER, "pro")
    staff.set_active(OWNER, "designer", False)
    with tenant.bind(OWNER):
        assert "designer" not in roles.assignable()
        assert "developer" in roles.assignable()


def test_assignable_never_returns_nobody():
    """전원이 빠지는 일은 없어야 하지만, 혹시 그런 상태가 되면 배정할
    사람이 없어 실행이 통째로 멈춘다. 그때는 전원을 돌려준다."""
    credits.set_plan(OWNER, "pro")
    for who in ("writer", "designer"):
        staff.set_active(OWNER, who, False)
    with tenant.bind(OWNER):
        assert roles.assignable(), "배정 가능한 직원이 아무도 없다"


def test_status_carries_the_staff_overlay():
    credits.set_plan(OWNER, "pro")
    staff.rename(OWNER, "analyst", "최검증")
    with tenant.bind(OWNER):
        rows = {r["id"]: r for r in employee.status()}
    assert rows["analyst"]["name"] == "최검증"
    assert rows["analyst"]["can_fire"] is False
    assert rows["analyst"]["fire_reason"]
    assert rows["writer"]["can_fire"] is True


# ── 언어 ───────────────────────────────────────────────────────────
def test_accept_language_is_read_in_preference_order():
    assert lang.from_header("ja,en-US;q=0.9,en;q=0.8") == "ja"
    assert lang.from_header("fr-FR,fr;q=0.9") == "ko", "모르는 언어는 기본값"
    assert lang.from_header(None) == "ko"


def test_prompt_tells_the_employee_which_language_to_write_in():
    """산출물·주석·요약이 전부 이 언어로 나온다. 표로 번역할 수 없는
    글이라 프롬프트에서 정해야 한다."""
    e = roles.get("developer")
    with lang.bind("en"):
        req = employee._request(e, "안녕", None)
        assert "English" in req.system
    with lang.bind("ja"):
        assert "日本語" in employee._request(e, "안녕", None).system


def test_korean_adds_nothing_to_the_prompt():
    """프롬프트가 이미 한국어다. '한국어로 쓰세요'를 덧붙이면 토큰만 쓰고,
    캐싱(§14)도 꼬리가 고정이어야 잘 맞는다."""
    e = roles.get("developer")
    with lang.bind("ko"):
        assert employee._request(e, "안녕", None).system == e.system


def test_refusals_are_translated():
    """영어로 쓰는 사람에게 한국어 거절 사유가 가면, 그 화면만 번역이
    깨진 것처럼 보인다."""
    with lang.bind("en"):
        assert "plan" in lang.t("plan.required").lower()
    with lang.bind("ja"):
        assert "プラン" in lang.t("plan.required")


def test_phase_labels_are_translated():
    """단계 설명은 화면 한가운데(사무실 탁자)에 뜬다. 번역되지 않으면
    눈에 제일 먼저 띈다."""
    with lang.bind("en"):
        assert lang.t("phase.plan") == "The strategist is planning"
    with lang.bind("ja"):
        assert "ストラテジスト" in lang.t("phase.plan")


def test_phase_label_keeps_the_employees_name():
    """이름은 번역하지 않는다 — 사람 이름이고, 고객이 붙인 것일 수도 있다."""
    with lang.bind("en"):
        out = lang.t("phase.manual", who="박도현")
    assert "박도현" in out
