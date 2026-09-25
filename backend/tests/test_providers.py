"""제공자 계약 테스트 (지시서 §7 · §18).

## 이 파일이 지키려는 것

방침상 API 키는 맨 마지막에 들어온다. 그때까지 모든 코드가 Mock 위에서만
돈다. 그러면 마지막 날 키를 꽂는 순간 무엇이 깨질지 아무도 모른다.

그래서 **같은 계약을 Mock 과 실제 제공자에 똑같이 건다.** 키가 없으면
실제 쪽은 skip 되지만, skip 은 출력에 남아서 "아직 검증 안 됨"을 계속
드러낸다. 키가 생기는 날 skip 이 풀리면서 계약 위반이 즉시 드러난다.

Mock 만 통과하는 테스트는 마지막 날 아무것도 보장하지 못한다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app import config, secrets_broker, usage                  # noqa: E402
from app.providers import base, registry                       # noqa: E402
from app.providers.base import (AuthError, FallbackProvider,    # noqa: E402
                                GenerateRequest, ProviderError,
                                ProviderUnavailable, RateLimited,
                                TransientError)
from app.providers.claude import ClaudeProvider, translate      # noqa: E402
from app.providers.gemini import GeminiProvider                 # noqa: E402
from app.providers.gemini import translate as translate_gemini  # noqa: E402
from app.providers.openai import OpenAIProvider                 # noqa: E402
from app.providers.openai import translate as translate_openai  # noqa: E402
from app.providers.mock import Failure, MockProvider, estimate_tokens  # noqa: E402

SYSTEM = "당신은 테스트용 조수입니다. 짧게 답하세요."
ASK = "한 줄로 인사해 주세요."


@pytest.fixture(autouse=True)
def _bind_run():
    """사용량 집계는 실행(run)에 묶여야 기록된다. 안 묶으면 조용히 버려진다."""
    usage.bind("test-providers")
    yield
    usage.drop("test-providers")


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """재시도 테스트가 실제로 잠들면 한 번에 30초씩 잡아먹는다."""
    monkeypatch.setattr(base, "_sleep", lambda s: None)


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.reset()
    yield
    registry.reset()


# ── 계약: Mock 과 실제에 똑같이 건다 ───────────────────────────────
# (계약을 걸 제공자, 키 이름, 생성자)
_REAL = [
    ("claude", "anthropic", ClaudeProvider),
    ("gemini", "gemini", GeminiProvider),
    ("openai", "openai", OpenAIProvider),
]


def _cases():
    yield pytest.param(lambda: MockProvider(), id="mock")

    for label, key, factory in _REAL:
        if secrets_broker.has(key):
            yield pytest.param(factory, id=label)
        else:
            yield pytest.param(
                None, id=label,
                marks=pytest.mark.skip(
                    reason=f"{label} 키 없음 — 키를 넣는 순간 이 계약이 자동으로 걸린다"))


@pytest.fixture(params=list(_cases()))
def provider(request):
    return request.param()


def _req(**kw) -> GenerateRequest:
    return GenerateRequest.ask(SYSTEM, ASK, max_tokens=64, agent="TEST", **kw)


def test_generate_returns_text(provider):
    r = provider.generate(_req())
    assert r.text.strip(), "빈 응답을 성공으로 돌려주면 위에서 성공으로 오해한다"
    assert r.provider == provider.name
    assert r.model, "어떤 모델이 답했는지 모르면 비용을 어디 달지 알 수 없다"
    assert r.attempts >= 1


def test_generate_records_usage(provider):
    before = usage.totals()["calls"]
    r = provider.generate(_req())
    after = usage.totals()
    assert after["calls"] == before + 1, "호출이 사용량에 잡히지 않는다 (§14)"
    assert r.usage.input_tokens > 0 and r.usage.output_tokens > 0


def test_stream_yields_chunks(provider):
    chunks = list(provider.stream(_req()))
    assert chunks, "스트림이 아무것도 내지 않았다"
    assert "".join(chunks).strip(), "조각을 이었더니 빈 글이다"


def test_available_is_truthful(provider):
    assert isinstance(provider.available(), bool)


def test_agenerate_matches_generate(provider):
    """async 표면은 동기 호출을 스레드로 넘긴 것뿐이어야 한다."""
    import asyncio
    r = asyncio.run(provider.agenerate(_req()))
    assert r.text.strip()
    assert r.provider == provider.name


# ── Mock 고유의 불변식 ──────────────────────────────────────────────
def test_mock_is_deterministic():
    """같은 요청에 같은 답. 아니면 테스트도 화면 비교도 흔들린다."""
    p = MockProvider()
    assert p.generate(_req()).text == p.generate(_req()).text


def test_mock_stream_equals_generate_exactly():
    """조각을 이은 글과 한 번에 받은 글이 달라지면, 화면에 보인 것과
    저장된 것이 달라진다. 가장 고약한 종류의 버그다."""
    p = MockProvider()
    whole = p.generate(_req()).text
    streamed = "".join(p.stream(_req()))
    assert streamed == whole


def test_mock_response_is_labelled():
    """Mock 이 만든 글은 Mock 이라고 적혀 있어야 한다.

    안 적히면 시연 중에 누구도 이게 진짜 AI 인지 아닌지 구분하지 못한다.
    """
    text = MockProvider().generate(_req()).text
    assert "MOCK" in text.upper()


def test_estimate_tokens_is_positive():
    assert estimate_tokens("") >= 1
    assert estimate_tokens("가" * 400) > estimate_tokens("가")


# ── 재시도·백오프 (§18) ────────────────────────────────────────────
def test_retryable_error_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRY", 5)
    p = MockProvider(failure=Failure(RateLimited, times=2))
    r = p.generate(_req())
    assert r.attempts == 3, "두 번 실패했으면 세 번째에 성공해야 한다"


def test_retry_stops_at_max_retry(monkeypatch):
    """상한 없이 재시도하면 지갑이 탄다. 상한에 닿으면 올려보낸다."""
    monkeypatch.setattr(config, "MAX_RETRY", 3)
    p = MockProvider(failure=Failure(TransientError, times=99))
    with pytest.raises(TransientError):
        p.generate(_req())
    assert len(p.calls) == 4, "첫 시도 1 + 재시도 3 = 4번이어야 한다"


def test_non_retryable_error_is_not_retried(monkeypatch):
    """인증 오류에 5번 재시도하는 것은 5번 틀리는 것이다."""
    monkeypatch.setattr(config, "MAX_RETRY", 5)
    p = MockProvider(failure=Failure(AuthError, times=99))
    with pytest.raises(AuthError):
        p.generate(_req())
    assert len(p.calls) == 1


def test_failed_call_is_not_billed(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRY", 1)
    before = usage.totals()["calls"]
    p = MockProvider(failure=Failure(TransientError, times=99))
    with pytest.raises(TransientError):
        p.generate(_req())
    assert usage.totals()["calls"] == before, "실패한 호출이 사용량에 잡혔다"


def test_backoff_grows_and_is_capped():
    delays = [base.backoff_delay(i) for i in range(12)]
    assert delays[0] < delays[5], "백오프가 커지지 않는다"
    assert all(d <= base.MAX_DELAY for d in delays), "상한을 넘는 대기"


def test_backoff_honours_retry_after():
    assert base.backoff_delay(0, retry_after=3.0) == 3.0


class _BreaksMidStream(MockProvider):
    """첫 조각을 낸 **뒤에** 연결이 끊기는 제공자."""

    def _stream(self, req):
        self.calls.append(req)
        yield "첫 조각 "
        raise TransientError("연결 끊김", provider=self.name)


def test_stream_retries_before_the_first_chunk(monkeypatch):
    """아무것도 보여주기 전의 실패는 다시 해도 겹칠 것이 없다 (DAY 26)."""
    monkeypatch.setattr(config, "MAX_RETRY", 3)
    p = MockProvider(failure=Failure(TransientError, times=1))
    assert "".join(p.stream(_req())) == MockProvider().generate(_req()).text
    assert len(p.calls) == 2


def test_stream_is_not_retried_after_the_first_chunk(monkeypatch):
    """조각을 이미 내보낸 뒤 재시도하면 사용자는 같은 문장을 두 번 본다."""
    monkeypatch.setattr(config, "MAX_RETRY", 3)
    p = _BreaksMidStream()
    got: list[str] = []
    with pytest.raises(TransientError):
        for chunk in p.stream(_req()):
            got.append(chunk)
    assert got == ["첫 조각 "]
    assert len(p.calls) == 1


def test_non_retryable_stream_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRY", 3)
    p = MockProvider(failure=Failure(AuthError, times=99))
    with pytest.raises(AuthError):
        list(p.stream(_req()))
    assert len(p.calls) == 1


# ── 스트리밍도 청구된다 (DAY 26) ────────────────────────────────────
def test_stream_is_billed_exactly_like_generate():
    """DAY 25 까지 `stream()` 은 사용량을 한 줄도 안 남겼다 — 청구되지 않았다."""
    usage.bind("stream-a")
    MockProvider().generate(_req())
    by_generate = usage.agents_of("stream-a")["TEST"]
    usage.bind("stream-b")
    "".join(MockProvider().stream(_req()))
    by_stream = usage.agents_of("stream-b")["TEST"]
    for k in ("calls", "input", "output", "cost"):
        assert by_stream[k] == by_generate[k], k
    assert by_stream["calls"] == 1 and by_stream["latency_ms"] >= 0
    usage.drop("stream-a")
    usage.drop("stream-b")


def test_stream_abandoned_midway_is_still_billed():
    """소비자가 도중에 그만 읽어도 제공자는 만든 만큼 청구한다.
    0 으로 두면 끊는 것이 곧 공짜로 쓰는 법이 된다."""
    before = usage.totals()["calls"]
    it = MockProvider().stream(_req())
    next(it)
    it.close()
    after = usage.totals()
    assert after["calls"] == before + 1
    assert after["output"] >= 1


def test_stream_broken_after_chunks_is_billed_by_estimate(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRY", 0)
    before = usage.totals()["calls"]
    with pytest.raises(TransientError):
        list(_BreaksMidStream().stream(_req()))
    assert usage.totals()["calls"] == before + 1


def test_stream_failing_before_any_chunk_is_not_billed(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRY", 0)
    before = usage.totals()
    with pytest.raises(TransientError):
        list(MockProvider(failure=Failure(TransientError, times=9)).stream(_req()))
    after = usage.totals()
    assert after["calls"] == before["calls"]
    assert after["failures"] == before["failures"] + 1


def test_astream_bills_the_run_that_started_it():
    """`astream` 은 조각마다 스레드 풀의 아무 스레드에서 돈다. 그 스레드에는
    실행이 묶여 있지 않으므로, 부른 쪽의 실행을 기억하지 않으면 그 호출의
    원가가 어느 실행에도 안 잡힌다."""
    import asyncio

    async def consume():
        return "".join([c async for c in MockProvider().astream(_req())])

    usage.bind("astream-run")
    text = asyncio.run(consume())
    assert text
    assert usage.agents_of("astream-run")["TEST"]["calls"] == 1
    usage.drop("astream-run")


def test_stream_emits_call_events_into_its_run():
    from app import bus
    bus.bind("stream-events")
    try:
        "".join(MockProvider().stream(_req()))
        calls = [e for e in bus.history("stream-events") if e["type"] == "call"]
    finally:
        bus.release()
        bus.reset("stream-events")
    assert [e["stage"] for e in calls] == ["start", "end"]
    assert calls[-1]["stream"] is True and calls[-1]["ok"] is True
    assert calls[-1]["estimated"] is False, "Mock 은 사용량을 알려준다 — 어림이 아니다"


# ── 대체 제공자 (§18) ──────────────────────────────────────────────
def test_fallback_moves_to_next_provider():
    dead = MockProvider(name="dead", failure=Failure(TransientError, times=99))
    alive = MockProvider(name="alive")
    r = FallbackProvider(dead, alive).generate(_req())
    assert r.provider == "alive"


def test_fallback_skips_unavailable_provider():
    """키 없는 제공자에 요청을 던져 예외를 받고 넘어가는 건 낭비다."""
    class NoKey(MockProvider):
        def available(self) -> bool:
            return False

    no_key = NoKey(name="nokey")
    alive = MockProvider(name="alive")
    r = FallbackProvider(no_key, alive).generate(_req())
    assert r.provider == "alive"
    assert not no_key.calls, "쓸 수 없는 제공자를 호출했다"


def test_fallback_stream_moves_on_before_the_first_chunk():
    dead = MockProvider(name="dead", failure=Failure(AuthError, times=99))
    alive = MockProvider(name="alive")
    text = "".join(FallbackProvider(dead, alive).stream(_req()))
    assert text == alive.generate(_req()).text


def test_fallback_stream_does_not_switch_voices_midway():
    """조각을 낸 뒤에 다른 모델이 이어 쓰면 한 답에 두 목소리가 섞인다."""
    alive = MockProvider(name="alive")
    with pytest.raises(TransientError):
        list(FallbackProvider(_BreaksMidStream(name="flaky"), alive).stream(_req()))
    assert alive.calls == []


def test_fallback_raises_when_all_dead():
    a = MockProvider(name="a", failure=Failure(TransientError, times=99))
    b = MockProvider(name="b", failure=Failure(TransientError, times=99))
    with pytest.raises(ProviderError):
        FallbackProvider(a, b).generate(_req())


# ── 레지스트리: 교체는 설정 한 줄 ──────────────────────────────────
def test_auto_mode_falls_back_to_mock_without_key(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "auto")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: False)
    registry.reset()
    assert registry.is_mock("claude")
    assert registry.get("claude").generate(_req()).provider.startswith("mock")


def test_real_mode_refuses_to_use_mock(monkeypatch):
    """배포에서 키 설정이 빠졌을 때 조용히 Mock 으로 돌아가면,
    가짜 결과물이 진짜처럼 사용자에게 간다. 그건 버그가 아니라 사고다."""
    monkeypatch.setenv("PROVIDER_MODE", "real")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: False)
    registry.reset()
    with pytest.raises(ProviderUnavailable):
        registry.get("claude")


def test_mock_mode_forces_mock_even_with_key(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: True)
    registry.reset()
    assert registry.is_mock("claude")
    assert registry.get("claude").generate(_req()).provider.startswith("mock")


def test_fallback_chain_never_contains_mock(monkeypatch):
    """실패가 성공처럼 보이면 안 된다. Mock 은 대체 사슬에 들어가지 않는다."""
    monkeypatch.setenv("PROVIDER_MODE", "auto")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: True)
    registry.reset()
    p = registry.get("claude")
    chain = getattr(p, "chain", [p])
    assert not any("mock" in c.name for c in chain)


def test_status_reports_mock_state(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "auto")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: False)
    registry.reset()
    st = registry.status()
    assert st["mode"] == "auto"
    assert st["all_mock"] is True
    assert st["providers"][0]["mock"] is True


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "real")
    registry.reset()
    with pytest.raises(ProviderUnavailable):
        registry.get("존재하지않는제공자")


# ── 예외 번역 ──────────────────────────────────────────────────────
class _Fake(Exception):
    def __init__(self, name, status=None):
        super().__init__("가짜")
        type(self).__name__ = name
        self.status_code = status


@pytest.mark.parametrize("name,expected", [
    ("RateLimitError", RateLimited),
    ("AuthenticationError", AuthError),
    ("PermissionDeniedError", AuthError),
    ("APIConnectionError", TransientError),
    ("APITimeoutError", TransientError),
    ("InternalServerError", TransientError),
    ("OverloadedError", TransientError),
])
def test_translate_known_errors(name, expected):
    assert isinstance(translate(_Fake(name)), expected)


def test_translate_unknown_error_is_not_retryable():
    """모르는 오류를 재시도 가능으로 두면, 영영 성공하지 않을 요청에
    MAX_RETRY 번 돈을 쓴다. 판단이 안 서면 멈추는 쪽이 싸다."""
    assert translate(_Fake("어떤이상한오류")).retryable is False


def test_translate_uses_status_code_when_name_unknown():
    assert isinstance(translate(_Fake("낯선이름", status=503)), TransientError)
    assert isinstance(translate(_Fake("낯선이름", status=429)), RateLimited)


def test_translate_scrubs_secrets(monkeypatch):
    """오류 메시지에 키가 섞여 나가면 로그에 그대로 남는다."""
    monkeypatch.setitem(secrets_broker._store, "anthropic", "sk-ant-verysecret12345")
    err = translate(Exception("실패: sk-ant-verysecret12345"))
    assert "verysecret" not in str(err)
    assert "[REDACTED]" in str(err)


# ── 키가 없는 실제 제공자 ──────────────────────────────────────────
def test_claude_without_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: False)
    with pytest.raises(ProviderUnavailable):
        ClaudeProvider().generate(_req())


# ── Gemini · OpenAI: 키 없이도 확인할 수 있는 것 ───────────────────
#
# 페이로드 변환과 사용량 해석은 **키가 있어야 볼 수 있는 것이 아니다.**
# 역할 이름을 잘못 옮기거나 캐시 토큰을 두 번 세는 버그는 키를 꽂는 날이
# 아니라 지금 잡아야 한다 — 키를 맨 마지막에 넣는 방침이 감춰버리는
# 바로 그런 종류의 결함이다.

class _Blob:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_gemini_translates_assistant_role_to_model():
    """Anthropic 의 'assistant' 는 Google 에서 'model' 이다.

    이 한 줄을 빠뜨리면 멀티턴에서 역할이 뒤집혀, 모델이 자기 말을
    사용자 말로 읽는다. 증상은 '갑자기 이상한 답'이고 원인은 안 보인다.
    """
    req = GenerateRequest(system="S", messages=[
        base.Message("user", "안녕"), base.Message("assistant", "네"),
        base.Message("user", "더"),
    ])
    roles = [c["role"] for c in GeminiProvider()._payload(req)["contents"]]
    assert roles == ["user", "model", "user"]


def test_gemini_system_goes_to_system_instruction():
    req = GenerateRequest.ask("지침", "질문")
    cfg = GeminiProvider()._payload(req)["config"]
    assert cfg["system_instruction"] == "지침"


def test_gemini_does_not_double_count_cached_tokens():
    """genai 의 prompt_token_count 에는 캐시분이 이미 들어 있다.

    그대로 두면 usage 가 input+cached 를 더해 과금하므로 캐시분이 두 번
    잡히고, §17 원가(판매가의 50% 이하)가 실제보다 나쁘게 나온다.
    """
    u = GeminiProvider._usage_of(_Blob(prompt_token_count=1000,
                                       candidates_token_count=200,
                                       cached_content_token_count=400))
    assert (u.input_tokens, u.cached_tokens) == (600, 400)


def test_openai_does_not_double_count_cached_tokens():
    u = OpenAIProvider._usage_of(_Blob(
        input_tokens=1000, output_tokens=200,
        input_tokens_details=_Blob(cached_tokens=300)))
    assert (u.input_tokens, u.cached_tokens) == (700, 300)


def test_openai_payload_keeps_system_separate():
    req = GenerateRequest.ask("지침", "질문")
    pay = OpenAIProvider()._payload(req)
    assert pay["instructions"] == "지침"
    assert pay["input"] == [{"role": "user", "content": "질문"}]


@pytest.mark.parametrize("xlate", [translate_gemini, translate_openai])
def test_new_providers_translate_unknown_as_not_retryable(xlate):
    assert xlate(_Fake("낯선오류")).retryable is False


@pytest.mark.parametrize("xlate", [translate_gemini, translate_openai])
def test_new_providers_translate_by_status_code(xlate):
    assert isinstance(xlate(_Fake("낯선이름", status=503)), TransientError)
    assert isinstance(xlate(_Fake("낯선이름", status=429)), RateLimited)
    assert isinstance(xlate(_Fake("낯선이름", status=401)), AuthError)


@pytest.mark.parametrize("xlate", [translate_gemini, translate_openai])
def test_new_providers_scrub_secrets(xlate, monkeypatch):
    monkeypatch.setitem(secrets_broker._store, "openai", "sk-proj-verysecret12345")
    err = xlate(Exception("실패: sk-proj-verysecret12345"))
    assert "verysecret" not in str(err)


@pytest.mark.parametrize("factory", [GeminiProvider, OpenAIProvider])
def test_new_providers_without_key_are_unavailable(factory, monkeypatch):
    monkeypatch.setattr(factory, "available", lambda self: False)
    with pytest.raises(ProviderUnavailable):
        factory().generate(_req())


# ── 대체 사슬은 회사를 건넌다 (§18) ────────────────────────────────
def test_fallback_chain_crosses_companies():
    """같은 회사 안에서 넘기는 것은 대체가 아니라 같은 문을 두 번 두드리는 것이다."""
    for name, chain in registry._FALLBACKS.items():
        assert name not in chain, f"{name} 이 자기 자신으로 대체된다"


def test_reviewer_never_falls_back_to_the_implementer():
    """검증자(gemini)가 Claude 로 넘어가면 교차검증 전제가 조용히 사라진다.

    구현도 Claude, 검증도 Claude 면 같은 맹점을 함께 놓친다. 그건
    '느리게라도 돌아감'이 아니라 '검증한 척'이다. 차라리 멈춘다.
    """
    assert "claude" not in registry._FALLBACKS["gemini"]


def test_cross_check_flag_requires_two_companies(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "auto")
    monkeypatch.setattr(ClaudeProvider, "available", lambda self: True)
    monkeypatch.setattr(GeminiProvider, "available", lambda self: False)
    registry.reset()
    assert registry.status()["cross_check"] is False

    monkeypatch.setattr(GeminiProvider, "available", lambda self: True)
    registry.reset()
    assert registry.status()["cross_check"] is True


def test_catalog_default_is_in_its_own_model_list():
    """기본 모델이 목록에 없으면 설정 화면이 '선택된 것 없음'으로 뜬다."""
    for name in ("claude", "gemini", "openai"):
        ids = [m["id"] for m in config.models_of(name)]
        assert config.default_model(name) in ids, f"{name} 기본 모델이 목록 밖이다"


def test_every_catalog_model_has_a_price():
    """단가 없는 모델을 고르게 두면 그 실행의 비용이 조용히 0 으로 잡힌다.

    0 은 '공짜'가 아니라 '모른다'이고, 예산 상한(§18)이 그 모델에는
    걸리지 않게 된다.
    """
    missing = [m["id"] for name in ("claude", "gemini", "openai")
               for m in config.models_of(name) if m["id"] not in config.PRICES]
    assert not missing, f"단가표에 없는 모델: {missing}"
