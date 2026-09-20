"""오케스트레이터 (지시서 §9 · §10).

AI 직원 수가 아니라 **여기가 제품의 핵심이다**. 누가 다음에 말할지를
LLM 이 아니라 파이썬 상태머신이 정한다.

    engine.py    상태머신 · 하드스톱 · AUTO 라우팅
    prompts.py   직원에게 건네는 요청문
    runner.py    격리된 pytest 실행 (생성된 코드를 돌리는 유일한 지점)
    score.py     완성도 계산
"""
from app.orchestrator.engine import (cancel, is_running, route,  # noqa: F401
                                     running_slugs, start)
