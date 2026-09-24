"""로그를 평범한 말로 옮기기 (DAY 23 · app/narrator.py).

## 이 파일이 지키려는 것

1. **아직 돈이 든다.** MANUAL 이 DAY 18 까지 크레딧을 안 깎던 것과 같은
   구멍을 새로 만들지 않는다.
2. **캐시는 인스턴스를 넘는다.** 프로세스 메모리에 두면 이 요청을 받은
   인스턴스가 지난번과 다를 때 다시 부르고 다시 청구한다.
3. **CEO 가 누를 때만 돈다.** 같은 로그를 두 번 설명해 달라고 하지
   않으면 두 번째 호출은 캐시를 돌려주고 청구하지 않는다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import bus, config, narrator, usage                    # noqa: E402
from app.database import store                                   # noqa: E402
from app.providers import registry                                # noqa: E402
from app.usage import credits                                     # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    registry.reset()
    usage.drop_all()
    credits.reset()
    # 트레이스 파일 핸들은 slug 문자열로 캐시된다(`bus._files`). 같은 초에
    # 같은 요구사항으로 여러 테스트가 slug 를 만들면 문자열이 같아지고,
    # 이전 테스트가 (지금은 monkeypatch 로 바뀐) 옛 LOGS 경로로 열어둔
    # 핸들을 그대로 쓰게 된다 — 이번 테스트가 쓴 줄이 엉뚱한 파일로 간다.
    bus.close_all_traces()
    yield
    bus.close_all_traces()
    usage.drop_all()
    credits.reset()
    registry.reset()


@pytest.fixture
def slug():
    s = store.new_project("계산기를 만들어주세요", owner="ceo")
    store.save_meta(s, {"requirement": "계산기를 만들어주세요"})
    bus.bind(s)
    bus.phase("PLAN", "요구사항을 정리하는 중")
    bus.say("strategist", "인수기준 2개를 정리했습니다.")
    bus.release()
    return s


def test_refuses_when_nothing_happened_yet():
    s = store.new_project("빈 프로젝트", owner="ceo")
    with pytest.raises(narrator.NoProgress):
        narrator.narrate(s, owner="ceo")


def test_narrates_and_charges_credits(slug):
    credits.set_plan("ceo", "pro")
    before = credits.balance("ceo")
    out = narrator.narrate(slug, owner="ceo")
    assert out["text"]
    assert out["cached"] is False
    assert credits.balance("ceo") < before, "돈이 안 깎였다"


def test_repeat_call_is_cached_and_free(slug):
    """같은 로그를 두 번 설명해 달라고 하지 않았다면 두 번째는 공짜다."""
    credits.set_plan("ceo", "pro")
    narrator.narrate(slug, owner="ceo")
    after_first = credits.balance("ceo")
    out2 = narrator.narrate(slug, owner="ceo")
    assert out2["cached"] is True
    assert credits.balance("ceo") == pytest.approx(after_first)


def test_new_log_lines_bust_the_cache(slug):
    """일이 더 진행됐으면 지난 설명을 그대로 돌려주면 안 된다."""
    credits.set_plan("ceo", "pro")
    narrator.narrate(slug, owner="ceo")
    bus.bind(slug)
    bus.phase("IMPLEMENT", "개발자가 코드를 쓰는 중")
    bus.release()
    out = narrator.narrate(slug, owner="ceo")
    assert out["cached"] is False


def test_force_recharges_even_without_new_lines(slug):
    credits.set_plan("ceo", "pro")
    narrator.narrate(slug, owner="ceo")
    after_first = credits.balance("ceo")
    out = narrator.narrate(slug, owner="ceo", force=True)
    assert out["cached"] is False
    assert credits.balance("ceo") < after_first


def test_cache_survives_a_restart(slug):
    """캐시가 프로세스 메모리에만 있으면, 이 요청을 받은 인스턴스가
    지난번과 다를 때(또는 서버가 재시작됐을 때) 또 부르고 또 청구한다."""
    credits.set_plan("ceo", "pro")
    narrator.narrate(slug, owner="ceo")
    # 다른 프로세스라고 치고, 메타를 파일에서 새로 읽는다.
    m = store.meta(slug)
    assert m.get("narration", {}).get("text")


def test_is_refused_when_credits_run_out(slug):
    credits.set_plan("ceo", "starter")
    credits.charge("ceo", credits.credits_to_usd(credits.balance("ceo")))
    with pytest.raises(credits.InsufficientCredits):
        narrator.narrate(slug, owner="ceo")
