"""AI COMPANY 백엔드.

지시서 §6의 구조를 따른다. 모듈이 놓인 자리가 곧 역할이다:

    providers/     AI 제공자 어댑터 (§7). 모델 교체 지점
    agents/        AI 직원 정의 (§8)
    orchestrator/  업무 분배·검증·재작업 (§9)
    tools/         에이전트가 쓰는 도구
    database/      영속화 (§12)
    usage/         토큰·비용·크레딧 (§14 §15)
    models/        API 요청·응답 스키마
    api/           FastAPI 라우터
"""
