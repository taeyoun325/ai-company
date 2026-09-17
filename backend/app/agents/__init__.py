"""AI 직원 정의 (지시서 §8).

각 직원은 id · name · role · provider · model · system_prompt ·
available_tools · status · usage 를 갖는다.

현재 들어 있는 core.py / subagents.py 는 이전 제품(대화형 개발도구)의
에이전트 루프다. 지우지 않는 이유: 도구 루프와 교차검토 프롬프트가
그대로 재사용되기 때문이다(DAY 4).
"""
