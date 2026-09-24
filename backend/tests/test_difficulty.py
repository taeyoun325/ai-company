"""난이도에 따른 모델 선택 (app/orchestrator/difficulty.py).

## 이 파일이 지키려는 것

1. **기본 모델보다 비싼 쪽으로는 절대 가지 않는다.** 호출 전 최악 비용
   검사(`employee.worst_case_cost`)가 기본 모델 단가로 이미 계산돼
   있다 — 그보다 비싼 모델을 고르면 상한이 상한이 아니게 된다.
2. **반려로 다시 쓰는 태스크는 할인하지 않는다.** 이미 한 번 틀렸다.
3. **큰 태스크는 할인하지 않는다.** 파일·인수기준·의존성이 많을수록
   실수의 여지가 크다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config                                          # noqa: E402
from app.agents import roles                                    # noqa: E402
from app.agents.schemas import Task                              # noqa: E402
from app.orchestrator import difficulty                          # noqa: E402


def _task(*, files=("src/a.py",), covers=("ac1",), deps=()) -> Task:
    return Task(id="t1", title="작은 일", assignee="developer",
                deps=list(deps), files=list(files), covers=list(covers),
                done_when="끝났다")


def test_small_first_attempt_downgrades_to_a_cheaper_model():
    e = roles.get("developer")               # claude, 기본은 opus(가장 비쌈)
    task = _task(files=["src/a.py"], covers=["ac1"], deps=[])
    picked = difficulty.pick_model(e, task, is_retry=False)
    assert picked is not None
    assert config.PRICES[picked] < config.PRICES[e.model]


def test_never_picks_a_model_pricier_than_the_default():
    """모든 직원 · 모든 태스크 크기 조합에서 성립해야 하는 불변식이다."""
    for employee_id in roles.ids():
        e = roles.get(employee_id)
        for n_files in range(0, 5):
            task = _task(files=[f"src/{i}.py" for i in range(n_files)])
            picked = difficulty.pick_model(e, task, is_retry=False)
            if picked is not None:
                assert config.PRICES[picked] <= config.PRICES[e.model]


def test_retry_does_not_downgrade():
    e = roles.get("developer")
    task = _task(files=["src/a.py"], covers=["ac1"], deps=[])
    assert difficulty.pick_model(e, task, is_retry=True) is None


def test_large_task_does_not_downgrade():
    e = roles.get("developer")
    task = _task(files=["src/a.py", "src/b.py", "src/c.py"],
                covers=["ac1", "ac2"], deps=["t0"])
    assert difficulty.pick_model(e, task, is_retry=False) is None


def test_an_employee_already_on_the_cheapest_model_is_not_downgraded_further():
    roles.set_model("designer", "gemini-2.5-flash")   # 이 제공자의 가장 싼 모델
    try:
        e = roles.get("designer")
        task = _task(files=["src/a.py"], covers=["ac1"], deps=[])
        assert difficulty.pick_model(e, task, is_retry=False) is None
    finally:
        roles.clear_models()
