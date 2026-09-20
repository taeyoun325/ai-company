"""SDK 시그니처 계약 — 키 없이 잡을 수 있는 마지막 구간 (지시서 §7, DAY 14).

## 왜 이 파일이 있나

DAY 14 에 **유효하지 않은 키**로 실제 SDK 를 태워보다가 이걸 잡았다:

    TypeError: Messages.create() got an unexpected keyword argument 'temperature'

현재 Claude 모델은 `temperature` 를 받지 않는다. 그 자리를
`output_config.effort` 가 대신한다. 우리는 그걸 모르고 보내고 있었다.

계약 테스트(`test_providers.py`)는 이걸 못 잡는다. **Mock 은 SDK 시그니처를
모르기 때문이다.** Mock 은 "우리가 만든 요청 객체를 우리가 읽는다"를 확인할
뿐, 그 객체가 실제 SDK 에 들어갈 수 있는지는 모른다.

키를 맨 마지막에 넣는 방침이 감추는 것이 정확히 이 종류의 결함이다.
그래서 **키 없이 확인할 수 있는 만큼은 여기서 확인한다**: 각 어댑터가
만드는 페이로드의 키가 그 SDK 함수가 실제로 받는 인자 안에 있는가.

## 이 테스트가 보장하지 않는 것

값의 **모양**까지는 못 본다(`output_config` 안에 무엇이 들어가야 하는지 등).
그건 실제 호출만 안다 — `scripts/first_real_run.py` 의 몫이다.
"""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app.agents import roles                                    # noqa: E402
from app.providers.base import GenerateRequest, Message         # noqa: E402
from app.providers.claude import ClaudeProvider                 # noqa: E402
from app.providers.gemini import GeminiProvider                 # noqa: E402
from app.providers.openai import OpenAIProvider                 # noqa: E402

REQ = GenerateRequest(
    system="지침", messages=[Message("user", "질문")],
    model="claude-opus-5", max_tokens=64, temperature=0.3, effort="high",
)


def _params(fn) -> set[str]:
    sig = inspect.signature(fn)
    names = set(sig.parameters)
    # **kwargs 를 받는 함수는 무엇이든 통과시키므로 검사 의미가 없다.
    if any(p.kind is inspect.Parameter.VAR_KEYWORD
           for p in sig.parameters.values()):
        pytest.skip("이 SDK 함수는 **kwargs 를 받아 시그니처 검사가 무의미하다")
    return names


def test_claude_payload_matches_the_sdk_signature():
    """`temperature` 를 보내다가 첫 실물 호출에서 터졌다. 같은 일을 막는다."""
    import anthropic
    client = anthropic.Anthropic(api_key="x")          # 호출하지 않는다
    allowed = _params(client.messages.create)
    sent = set(ClaudeProvider(model="claude-opus-5")._payload(REQ))
    extra = sent - allowed
    assert not extra, (
        f"anthropic SDK 가 받지 않는 인자를 보냅니다: {sorted(extra)}. "
        f"받는 것: {sorted(allowed)}")


def test_claude_stream_takes_the_same_payload():
    """생성은 되는데 스트리밍만 터지는 경우가 있다. 둘 다 본다."""
    import anthropic
    client = anthropic.Anthropic(api_key="x")
    allowed = _params(client.messages.stream)
    sent = set(ClaudeProvider(model="claude-opus-5")._payload(REQ))
    assert not sent - allowed


def test_claude_does_not_send_sampling_parameters():
    """현재 Claude 모델은 temperature·top_p·top_k 를 400 으로 거부한다.
    effort 가 그 자리다."""
    payload = ClaudeProvider(model="claude-opus-5")._payload(REQ)
    assert "temperature" not in payload
    assert "top_p" not in payload and "top_k" not in payload
    assert payload["output_config"]["effort"] == "high"


def test_gemini_payload_matches_the_sdk_signature():
    from google import genai
    client = genai.Client(api_key="x")
    allowed = _params(client.models.generate_content)
    sent = set(GeminiProvider(model="gemini-2.5-pro")._payload(REQ))
    assert not sent - allowed, f"google-genai 가 받지 않는 인자: {sorted(sent - allowed)}"


def test_openai_payload_matches_the_sdk_signature():
    from openai import OpenAI
    client = OpenAI(api_key="x")
    allowed = _params(client.responses.create)
    sent = set(OpenAIProvider(model="gpt-5")._payload(REQ))
    assert not sent - allowed, f"openai 가 받지 않는 인자: {sorted(sent - allowed)}"


def test_every_employee_effort_is_a_valid_level():
    """오타 하나가 400 이 된다. 직원 표는 사람이 손으로 고치는 곳이다."""
    valid = {"low", "medium", "high", "xhigh", "max"}
    for e in roles.EMPLOYEES.values():
        assert e.effort in valid, f"{e.id} 의 effort 가 이상합니다: {e.effort}"


def test_every_employee_request_survives_signature_check():
    """직원별 설정(토큰 수·effort)이 그대로 SDK 에 들어갈 수 있는가."""
    import anthropic
    from app.agents import employee

    allowed = _params(anthropic.Anthropic(api_key="x").messages.create)
    for e in roles.EMPLOYEES.values():
        if e.provider != "claude":
            continue
        req = employee._request(e, "안녕", None)
        assert not set(ClaudeProvider(model=e.model)._payload(req)) - allowed
