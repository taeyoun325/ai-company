"""MANUAL 모드 (지시서 §11).

## 이 파일이 지키려는 것

**두 경로가 같은 규칙을 쓴다.** AUTO 에서 막히는 것이 MANUAL 에서 뚫리면,
그 차이가 곧 구멍이다. CEO 가 직접 시켰다는 사실은 권한의 근거가 아니다.

그리고 예산. MANUAL 은 버튼을 여러 번 누르는 모드이므로, 누를 때마다
누적이 0 으로 돌아가면 상한이 영영 걸리지 않는다.

DAY 19 에 하나 더 붙었다: **MANUAL 도 크레딧을 깎는다.** 그 전까지
MANUAL 은 한 개도 깎지 않았고, 요금제를 붙이는 순간 그건 구멍이 아니라
"AUTO 는 결제, MANUAL 은 공짜"라는 제품이 된다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config, usage                              # noqa: E402
from app.agents import employee, roles                          # noqa: E402
from app.database import store                                   # noqa: E402
from app.orchestrator import manual                              # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    registry.reset()
    # 집계는 slug 문자열을 전역 키로 쓴다. 테스트마다 임시 폴더가 달라도
    # 같은 초에 같은 요구사항이면 slug 가 같아서, 앞 테스트의 비용이
    # 이번 테스트의 예산 상한에 걸린다.
    usage.drop_all()
    manual.forget_cached_history()
    yield
    usage.drop_all()
    manual.forget_cached_history()
    registry.reset()


@pytest.fixture
def slug():
    s = manual.open_project("계산기를 만들어주세요")
    yield s
    manual.clear_history(s)


# ── 기본 흐름 ──────────────────────────────────────────────────────
def test_instruct_writes_files(slug):
    out = manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    assert out["files"] == ["src/calc.py"]
    assert "src/calc.py" in store.files_of(slug)


def test_planner_answers_in_prose_without_inventing_files(slug):
    """파일을 쓸 수 없는 직원에게 files 스키마를 씌우면, 빈 배열을 채우려고
    없는 파일을 지어낸다."""
    out = manual.instruct(slug, roles.PLANNER, "어떻게 나누면 좋을까요?")
    assert out["files"] == []
    assert out["text"].strip()


def test_history_is_kept_per_employee(slug):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    manual.instruct(slug, "writer", "문서를 써주세요")
    assert manual.history(slug, "developer"), "다음 지시에서 이어받을 수 없다"
    assert not any("사칙연산" in m.content
                   for m in manual.history(slug, "writer")), \
        "직원끼리 대화가 섞이면 교차검증 전제가 무너진다"


def test_history_is_capped(slug):
    for _ in range(MAX := manual.MAX_HISTORY):
        manual.instruct(slug, "developer", f"{_}번째 지시입니다")
    assert len(manual.history(slug, "developer")) <= MAX, \
        "이력이 무한히 쌓이면 비용이 대화 길이의 제곱으로 자란다"


def test_clear_history(slug):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    manual.clear_history(slug, "developer")
    assert manual.history(slug, "developer") == []


# ── 권한 경계는 AUTO 와 같다 ───────────────────────────────────────
def test_ceo_cannot_grant_write_permission(slug, monkeypatch):
    """'CEO 가 시켰다'는 권한의 근거가 아니다.

    작가에게 src/ 를 쓰라고 시키고 모델이 따르더라도, 파일은 거부되어야 한다.
    """
    from app.agents.schemas import FileWrite, WorkResult
    monkeypatch.setattr(employee, "ask", lambda *a, **kw: WorkResult(
        message_to_team="썼습니다", summary="s", self_check="c",
        files=[FileWrite(path="src/evil.py", content="x = 1")]))
    out = manual.instruct(slug, "writer", "src/evil.py 에 써주세요")
    assert out["files"] == []
    assert "src/evil.py" not in store.files_of(slug)


def test_denied_write_is_reported_not_silent(slug, monkeypatch):
    from app.agents.schemas import FileWrite, WorkResult
    monkeypatch.setattr(employee, "ask", lambda *a, **kw: WorkResult(
        message_to_team="썼습니다", summary="s", self_check="c",
        files=[FileWrite(path="tests/test_x.py", content="x")]))
    manual.instruct(slug, "developer", "테스트를 고쳐주세요")
    errors = [e for e in bus.history(slug)
              if e.get("kind") == "error" and "거부" in e.get("text", "")]
    assert errors, "조용히 버리면 CEO 는 지시가 먹혔다고 믿는다"


# ── 예산 (§18) ─────────────────────────────────────────────────────
def test_usage_accumulates_across_instructions(slug):
    """지시마다 0 으로 돌아가면, 버튼을 여러 번 누르는 것으로 상한을 우회한다."""
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    first = usage.agents_of(slug)["developer"]["calls"]
    manual.instruct(slug, "developer", "주석을 달아주세요")
    assert usage.agents_of(slug)["developer"]["calls"] > first


def test_budget_is_checked_before_the_call(slug, monkeypatch):
    monkeypatch.setattr(config, "MAX_PROJECT_COST", 0.0)
    monkeypatch.setattr(employee, "worst_case_cost", lambda _id: 1.0)
    with pytest.raises(RuntimeError, match="비용 상한"):
        manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    assert "src/calc.py" not in store.files_of(slug), "상한을 넘긴 뒤에 멈췄다"


# ── 검증 ───────────────────────────────────────────────────────────
def test_verify_runs_the_same_check_as_auto(slug):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    manual.instruct(slug, "analyst", "인수기준대로 테스트를 써주세요")
    out = manual.verify(slug)
    assert out["verdict"]["verdict"] in ("pass", "fail")
    assert "passed" in out["report"]


def test_verify_without_criteria_uses_the_requirement(slug):
    """기준 없이 검증하면 검증자가 기준을 지어낸다."""
    crit = manual._criteria_of(store.meta(slug))
    assert crit and "계산기" in crit[0].text


def test_verifier_prompt_has_no_builder_explanation(slug, monkeypatch):
    manual.instruct(slug, "developer", "사칙연산을 구현해주세요")
    seen = []
    real = employee.ask

    def spy(employee_id, user, schema, history=None):
        if employee_id == roles.VERIFIER:
            seen.append(user)
        return real(employee_id, user, schema, history)

    monkeypatch.setattr(employee, "ask", spy)
    manual.verify(slug)
    assert seen
    assert all("확인하지 못했다" not in t for t in seen)


# ── 잘못된 입력 ────────────────────────────────────────────────────
def test_unknown_project_raises(slug):
    with pytest.raises(KeyError):
        manual.instruct("없는프로젝트", "developer", "안녕")


def test_empty_message_raises(slug):
    with pytest.raises(ValueError):
        manual.instruct(slug, "developer", "   ")


def test_unknown_employee_raises(slug):
    with pytest.raises(KeyError):
        manual.instruct(slug, "없는직원", "안녕")


def test_busy_project_rejects_a_second_instruction(slug, monkeypatch):
    """같은 프로젝트에 둘이 동시에 쓰면 파일이 서로를 덮어쓴다."""
    import threading
    started = threading.Event()
    release = threading.Event()
    real = employee.ask

    def slow(*a, **kw):
        started.set()
        release.wait(10)
        return real(*a, **kw)

    monkeypatch.setattr(employee, "ask", slow)
    t = threading.Thread(target=lambda: manual.instruct(slug, "developer", "구현"),
                         daemon=True)
    t.start()
    assert started.wait(10)
    try:
        with pytest.raises(manual.Busy):
            manual.instruct(slug, "writer", "문서")
    finally:
        release.set()
        t.join(20)


# ── 크레딧 (§15 · DAY 19) ──────────────────────────────────────────
@pytest.fixture
def wallet(tmp_path, monkeypatch):
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    credits.reset()
    yield credits
    credits.reset()


def test_manual_charges_credits_for_what_it_spent(slug, wallet):
    """DAY 18 까지 MANUAL 은 한 개도 깎지 않았다. 프로젝트는 얼마든지
    새로 열 수 있으므로, 상한만으로는 아무것도 막지 못한다."""
    wallet.set_plan("ceo", "pro")
    before = wallet.balance("ceo")
    with manual._Session(slug, "developer", "ceo"):
        usage.record("developer", "claude-opus-5", 1_000_000, 0)   # $5.00
    assert wallet.balance("ceo") == pytest.approx(before - 500.0)


def test_manual_charges_only_the_new_spend(slug, wallet):
    """프로젝트 누적으로 깎으면 지시를 한 번 더 할 때마다 앞의 지시를
    다시 청구하게 된다."""
    wallet.set_plan("ceo", "business")
    with manual._Session(slug, "developer", "ceo"):
        usage.record("developer", "claude-opus-5", 1_000_000, 0)   # $5.00
    mid = wallet.balance("ceo")
    with manual._Session(slug, "developer", "ceo"):
        usage.record("developer", "claude-opus-5", 200_000, 0)     # $1.00
    assert wallet.balance("ceo") == pytest.approx(mid - 100.0)


def test_manual_on_byok_plan_does_not_spend_credits(slug, wallet, tmp_path,
                                                    monkeypatch):
    """고객이 자기 키로 낸 돈을 크레딧으로 또 받으면 이중 청구다."""
    from app import byok
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BYOK_SECRET", "test-kek")
    byok.reset()
    byok.set_key("ceo", "anthropic", "sk-ant-mine-0123456789")
    byok.set_key("ceo", "gemini", "AIza-mine-0123456789")
    wallet.set_plan("ceo", "byok")
    before = wallet.balance("ceo")
    with manual._Session(slug, "developer", "ceo"):
        usage.record("developer", "claude-opus-5", 1_000_000, 0)   # $5.00
    assert wallet.balance("ceo") == before
    assert wallet.status("ceo")["byok_usd"] == pytest.approx(5.0)
    byok.reset()


def test_manual_is_refused_when_byok_keys_are_missing(slug, wallet, tmp_path,
                                                      monkeypatch):
    from app import byok, tenant
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BYOK_SECRET", "test-kek")
    byok.reset()
    wallet.set_plan("ceo", "byok")
    with pytest.raises(tenant.KeysMissing):
        with manual._Session(slug, "developer", "ceo"):
            pass
    assert manual.busy_employee(slug) is None, "거부된 뒤에도 직원이 잡혀 있다"
    byok.reset()


def test_manual_is_refused_when_credits_run_out(slug, wallet):
    wallet.set_plan("ceo", "starter")
    wallet.charge("ceo", wallet.credits_to_usd(wallet.balance("ceo")))
    with pytest.raises(credits.InsufficientCredits):
        with manual._Session(slug, "developer", "ceo"):
            pass


# ── 대화는 파일에 남는다 (§12 · DAY 22) ────────────────────────────
def test_history_survives_a_restart(slug):
    """그 전까지 대화는 프로세스 메모리에만 있었다. 서버를 다시 켜면
    진행 중이던 대화가 통째로 사라졌고, 사용자는 자기가 무슨 지시를
    했는지 다시 떠올려야 했다."""
    manual.instruct(slug, "developer", "더하기를 만들어주세요")
    before = manual.history(slug, "developer")
    assert before, "대화가 기록되지 않았다"

    manual.forget_cached_history()          # 프로세스가 죽었다 살아난 셈
    after = manual.history(slug, "developer")
    assert [m.content for m in after] == [m.content for m in before]


def test_history_file_lives_with_the_project(slug):
    """산출물과 같은 자리에 둔다 — 프로젝트를 지우면 대화도 함께 사라진다."""
    manual.instruct(slug, "developer", "더하기를 만들어주세요")
    assert (store.dir_of(slug) / manual.HISTORY_FILE).exists()


def test_broken_history_file_does_not_break_the_screen(slug):
    """파일 하나가 깨진 것 때문에 MANUAL 화면 전체가 열리지 않으면,
    그건 대화를 잃는 것보다 나쁘다."""
    manual.instruct(slug, "developer", "더하기를 만들어주세요")
    (store.dir_of(slug) / manual.HISTORY_FILE).write_text("{깨진", encoding="utf-8")
    manual.forget_cached_history()
    assert manual.history(slug, "developer") == []


def test_clearing_history_also_clears_the_file(slug):
    manual.instruct(slug, "developer", "더하기를 만들어주세요")
    manual.clear_history(slug, "developer")
    manual.forget_cached_history()
    assert manual.history(slug, "developer") == []


def test_two_employees_keep_separate_conversations(slug):
    """검증자가 개발자의 자기 설명을 읽으면 교차검증이 오염된다(§9)."""
    manual.instruct(slug, "developer", "더하기를 만들어주세요")
    manual.forget_cached_history()
    assert manual.history(slug, "analyst") == []
    assert manual.history(slug, "developer")
