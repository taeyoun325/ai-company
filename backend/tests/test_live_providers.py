"""진짜 키로 진짜 서버에 — 돈이 드는 통합 시험 (DAY 25).

## 왜 따로 있나

`test_providers.py` 의 계약 시험은 키가 있으면 **저절로** 걸린다. 그래서 싸게
둔다(max_tokens 64, 인사 한 줄). 여기는 그보다 비싸다 — 직원 설정 그대로
(effort · 모델), 우리 스키마로 JSON 을 받아 파싱까지, 그리고 원하면 프로젝트
하나를 통째로. 키가 있다는 이유만으로 `pytest` 를 칠 때마다 돈이 나가면 안
되므로 **켜야만** 돈다:

    LIVE_PROVIDER_TESTS=1     직원별 호출 · 구조화 응답 · 캐시 (몇 센트)
    LIVE_PROVIDER_TESTS=full  위 + AUTO 프로젝트 한 건 (상한 $0.50)

키는 평소처럼 넣는다(환경변수 또는 설정 화면 — 브로커가 가져간다).

## 가짜 서버 시험(test_wire_providers.py)과의 차이

그쪽은 **우리 코드와 SDK** 를 확인한다. 이쪽은 **진짜 서버의 규칙** 을
확인한다 — 우리가 보내는 모델 이름을 받는가, 모르는 필드를 400 으로
거절하지 않는가, 모델이 우리 JSON 계약을 실제로 지키는가, 캐시가 실제로
걸리는가. 가짜 서버는 이것들을 흉내 낼 수 없다.
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config, secrets_broker, usage                  # noqa: E402
from app.agents import employee, roles                          # noqa: E402
from app.agents.schemas import Routing                           # noqa: E402
from app.providers import registry                               # noqa: E402

MODE = os.getenv("LIVE_PROVIDER_TESTS", "").strip().lower()
KEY_OF = {"claude": "anthropic", "gemini": "gemini", "openai": "openai"}

pytestmark = pytest.mark.skipif(
    MODE not in ("1", "full"),
    reason="돈이 드는 시험 — LIVE_PROVIDER_TESTS=1 (또는 full) 일 때만 돈다")


def _needs_key(provider: str):
    if not secrets_broker.has(KEY_OF[provider]):
        pytest.skip(f"{KEY_OF[provider]} 키 없음")


@pytest.fixture(autouse=True)
def _real(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "real")
    registry.reset()
    usage.bind("live")
    yield
    usage.drop("live")
    registry.reset()


@pytest.mark.parametrize("who", list(roles.EMPLOYEES))
def test_each_employee_answers_with_its_real_settings(who):
    """직원 설정 그대로(모델 · effort · temperature) 진짜 서버가 받아주는가."""
    e = roles.get(who)
    _needs_key(e.provider)
    text = employee.ask_text(who, "연결 확인입니다. '확인'이라고만 답하세요.")
    assert text.strip()
    row = usage.agents_of("live")[who]
    assert row["calls"] >= 1 and row["cost"] > 0, "실물 호출인데 원가가 0 이다 — 단가표를 보라"
    assert row["latency_ms"] > 0


@pytest.mark.parametrize("who", ["strategist", "analyst", "writer"])
def test_structured_json_contract_holds_against_real_models(who):
    """모델이 우리 JSON 계약(스키마)을 실제로 지키는가 — Mock 은 늘 지킨다."""
    e = roles.get(who)
    _needs_key(e.provider)
    r = employee.ask(who, "README 한 장을 누가 쓰면 좋을지 골라주세요. "
                          "후보: developer, writer, designer", Routing)
    assert r.employee in ("developer", "writer", "designer")
    assert r.why.strip()


def test_prompt_cache_actually_hits_on_claude():
    """cache_control 을 붙였다는 사실과 캐시가 걸렸다는 사실은 다르다(§14)."""
    _needs_key("claude")
    for _ in range(2):
        employee.ask_text("developer", "연결 확인입니다. '확인'이라고만 답하세요.")
        time.sleep(1)
    row = usage.agents_of("live")["developer"]
    # 시스템 프롬프트가 최소 캐시 길이보다 짧으면 조용히 안 걸린다 — 그 사실을
    # 알아야 한다. 실패하면 캐시가 원가 계산에 반영되지 않는 것이다.
    assert row["cached"] > 0 or row["cache_written"] > 0, (
        "두 번 불렀는데 캐시를 읽지도 쓰지도 않았다 — 프리픽스가 최소 길이 미만일 수 있다")


@pytest.mark.skipif(MODE != "full", reason="프로젝트 한 건 — LIVE_PROVIDER_TESTS=full")
def test_one_full_auto_project_with_a_hard_cost_cap(monkeypatch, tmp_path):
    """진짜 직원들로 작은 프로젝트 하나. 상한 $0.50 — 넘으면 멈추는 것도 합격이다
    (상한이 실제로 지켜진다는 뜻이다). 결과는 사람 눈으로 보도록 경로를 남긴다."""
    from app.database import store
    from app.orchestrator import engine
    from app.usage import credits
    for k in ("anthropic", "gemini"):
        if not secrets_broker.has(k):
            pytest.skip(f"{k} 키 없음 — 교차검증에는 둘 다 필요하다")
    monkeypatch.setattr(config, "MAX_PROJECT_COST", 0.50)
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "w.json")
    credits.reset()
    slug = engine.start("두 수를 더하는 add(a, b) 함수와 그 사용법 한 줄")
    deadline = time.time() + 15 * 60
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(1)
    m = store.meta(slug)
    print(f"\n실물 프로젝트: {store.dir_of(slug)} · 상태 {m['status']} · ${m.get('cost')}")
    assert m["status"] in ("done", "stopped")
    assert float(m.get("cost") or 0) <= 0.50 + 0.05
    assert m["mock"] is False
    if m["status"] == "stopped":
        assert "상한" in (m.get("stopped_reason") or "") or "cap" in \
            (m.get("stopped_reason") or "").lower(), m.get("stopped_reason")
