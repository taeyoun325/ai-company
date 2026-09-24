"""태스크 난이도에 따라 모델을 고른다.

## 왜 필요한가

직원마다 모델이 하나로 고정돼 있었다(`roles.py`). 파일 하나짜리 자잘한
태스크도, 다섯 파일을 건드리는 큰 태스크도 항상 같은(대개 가장 비싼)
모델로 불렀다. 작은 태스크에는 과한 값이다.

## 왜 기본 모델보다 비싼 쪽으로는 가지 않나

호출 *전에* 최악 비용을 검사하는 `employee.worst_case_cost()` 는
직원의 **기본** 모델(`e.model`) 단가로 계산한다. 여기서 기본보다 비싼
모델을 고르면, 이미 통과한 검사보다 실제로 더 나갈 수 있다 — 상한이
상한이 아니게 된다. 그래서 이 모듈은 **같거나 싼** 모델로만 내려간다.
반려로 다시 쓰는 것이면 아예 내려가지 않는다(기본 모델 그대로) — 이미
한 번 틀린 태스크에 싼 모델을 또 주면 같은 실수를 반복할 확률이 높다.

## 왜 IMPLEMENT 태스크에만 적용하나

PLAN·WRITE_TESTS·REVIEW·FINALIZE 는 실행 전체에 한 번씩만 도는 단일
호출이라 절감 여지가 작고, 잘못 골랐을 때 되돌릴 여지도 작다.
IMPLEMENT 는 태스크 수만큼 반복되므로 절감이 누적되고, 작은 태스크를
가려낼 신호(파일 수·의존성 수)도 여기에만 있다.
"""
from __future__ import annotations

from app import config
from app.agents.roles import Employee
from app.agents.schemas import Task

# 태스크가 이 개수 이하면 "작다"고 본다: 건드릴 파일 + 충족시킬 인수기준
# + 선행 의존성을 합친 값이다. 셋 다 태스크의 **크기**를 말한다 — 파일이
# 많을수록, 걸린 조건이 많을수록, 앞 단계에 얽힐수록 실수의 여지가 크다.
SMALL_TASK_SIZE = 2


def _size(task: Task) -> int:
    return len(task.files) + len(task.covers) + len(task.deps)


def _price(model: str) -> tuple[float, float]:
    return config.PRICES.get(model, (float("inf"), float("inf")))


def pick_model(e: Employee, task: Task, *, is_retry: bool) -> str | None:
    """이 태스크에 맞는 모델 id. 기본 모델을 쓸 거면 `None`.

    `None` 은 "고르지 않았다"가 아니라 "기본 모델이 이미 맞다"는 뜻이다 —
    호출부는 `model or e.model` 로 받으므로 `None` 이 곧 기본값이다.
    """
    if is_retry or _size(task) > SMALL_TASK_SIZE:
        return None
    default_price = _price(e.model)
    cheaper = [m["id"] for m in config.models_of(e.provider)
               if _price(m["id"]) < default_price]
    if not cheaper:
        return None
    # 출력 단가가 원가의 대부분을 차지한다 — 그 기준으로 가장 싼 것 하나.
    return min(cheaper, key=lambda m: _price(m)[1])
