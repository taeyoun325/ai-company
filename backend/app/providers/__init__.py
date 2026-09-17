"""AI 제공자 어댑터 (지시서 §7).

모든 모델 호출은 여기를 거친다. 직원 코드가 anthropic/genai SDK를 직접
부르지 않는 이유는 하나다 — **모델을 바꿀 수 있어야 하기 때문**이다.

DAY 2~4에 base.AIProvider 아래로 아래 클라이언트들을 정리한다:
    anthropic_client  → ClaudeProvider
    gemini_client     → GeminiProvider
    (신규)            → OpenAIProvider · HiggsfieldProvider · MockProvider
"""
