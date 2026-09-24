"""재개 시 사용량 이어받기 (app/usage/__init__.py 의 seed()).

## 이 파일이 지키려는 것

`bind()` 는 0부터 다시 센다 — 재개(§18)에 그대로 쓰면 멈추기 전까지
쌓인 비용·호출 수가 사라진다. `seed()` 는 저장된 값에서 이어서 센다.
서버가 재시작돼 메모리가 비어 있어도 성립해야 한다(디스크 값만으로
복원).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import usage                                           # noqa: E402


def test_seed_starts_from_the_saved_values():
    usage.drop_all()
    usage.seed("proj-1", {"developer": {"input": 100, "output": 50,
                                         "cached": 0, "cache_written": 0,
                                         "cost": 0.02, "credits": 2.0,
                                         "calls": 2}})
    assert usage.agents_of("proj-1")["developer"]["calls"] == 2
    assert usage.total_cost("proj-1") == 0.02


def test_seed_then_record_accumulates_on_top_of_the_saved_value():
    usage.drop_all()
    usage.seed("proj-2", {"developer": {"input": 100, "output": 50,
                                         "cached": 0, "cache_written": 0,
                                         "cost": 0.02, "credits": 2.0,
                                         "calls": 2}})
    usage.record("developer", "mock", input_tokens=10, output_tokens=5)
    assert usage.agents_of("proj-2")["developer"]["calls"] == 3, \
        "재개 후 첫 호출이 저장된 값을 덮어쓰고 1부터 다시 셌다"


def test_seed_with_no_prior_data_behaves_like_a_fresh_bind():
    usage.drop_all()
    usage.seed("proj-3", {})
    assert usage.total_cost("proj-3") == 0.0
    assert usage.agents_of("proj-3")["developer"]["calls"] == 0


def test_seed_fills_in_employees_missing_from_the_saved_data():
    """저장된 값에 없는 직원(그 실행에서 한 번도 안 불린 직원)은 0으로."""
    usage.drop_all()
    usage.seed("proj-4", {"developer": {"calls": 1, "cost": 0.01}})
    assert usage.agents_of("proj-4")["analyst"]["calls"] == 0
