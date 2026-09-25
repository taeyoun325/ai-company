"""실제 SDK 를 실제 HTTP 로 — 키 없이 (DAY 25).

## 왜 이 파일이 있나

테스트가 전부 Mock 기반이었다. Mock 은 `AIProvider` 를 통째로 대신하므로
SDK 가 만드는 요청, SDK 가 읽는 응답, SDK 의 예외·재시도·시간 제한은 한
줄도 돌지 않았다. 계약 테스트(`test_providers.py`)는 키가 없어 skip,
시그니처 테스트(`test_sdk_contract.py`)는 인자 **이름**만 본다.

여기서는 세 회사의 프로토콜을 흉내 내는 로컬 서버(`fakes/provider_server.py`)
에 **실제 SDK** 를 붙인다. 처음 붙여본 날 두 가지가 나왔다:

1. **개발자가 첫 호출에서 즉시 죽었을 것이다.** anthropic SDK 는 스트리밍이
   아닌 호출에서 `max_tokens` 가 크면 요청을 보내기도 전에 `ValueError` 를
   던진다. 개발자의 `max_tokens` 는 32000 — 네트워크에 닿기 전이라 "가짜 키로
   401 까지" 시험(DAY 14)으로는 안 보였다.
2. **429 하나에 18번 두드렸을 것이다.** anthropic·openai SDK 가 기본으로 2번
   더 재시도하고, 그 바깥에서 우리가 `MAX_RETRY`(5)번 더 한다: 3×6.

## 이 파일이 보장하지 않는 것

서버는 흉내다. 진짜 서버가 모르는 필드를 거절하는지, 모델 이름을
받는지, 토큰을 어떻게 세는지는 모른다 — 그건 `test_live_providers.py`
(키가 있을 때만 돈다)와 `scripts/first_real_run.py` 의 몫이다.
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))              # tests/

from fakes.provider_server import BAD_KEY, FakeProviders               # noqa: E402

from app import bus, config, secrets_broker, usage                     # noqa: E402
from app.agents import employee, roles                                  # noqa: E402
from app.database import store                                          # noqa: E402
from app.orchestrator import engine                                     # noqa: E402
from app.providers import (anthropic_client, base, gemini_client,       # noqa: E402
                           openai_client, registry)
from app.providers.base import (AuthError, FallbackProvider,           # noqa: E402
                                GenerateRequest, RateLimited,
                                RefusedError, TransientError)
from app.providers.claude import ClaudeProvider                         # noqa: E402
from app.providers.gemini import GeminiProvider                         # noqa: E402
from app.providers.openai import OpenAIProvider                         # noqa: E402
from app.usage import credits                                           # noqa: E402

PROVIDERS = {
    "anthropic": (ClaudeProvider, "developer"),
    "openai": (OpenAIProvider, "writer"),
    "gemini": (GeminiProvider, "analyst"),
}
KEY = "fake-key-0123456789"


def _reset_clients():
    anthropic_client.reset_client()
    openai_client.reset_client()
    gemini_client.reset_client()
    registry.reset()


@pytest.fixture
def fp(monkeypatch, tmp_path):
    """가짜 서버를 띄우고, 세 SDK 가 거기로 가게 하고, 키를 꽂는다."""
    monkeypatch.setattr(base, "_sleep", lambda s: None)      # 백오프는 재지 않는다
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    saved = {n: secrets_broker._store.get(n) for n in secrets_broker.KEYS}
    with FakeProviders() as server:
        for k, v in server.env().items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("PROVIDER_MODE", "real")
        for name in secrets_broker.KEYS:
            secrets_broker.set_key(name, KEY)
        _reset_clients()
        usage.bind("wire")
        bus.bind("wire")
        try:
            yield server
        finally:
            bus.release()
            usage.drop("wire")
            for name, val in saved.items():
                secrets_broker.set_key(name, val or "")
            _reset_clients()


def _req(employee_id: str, text: str = "안녕") -> GenerateRequest:
    return employee._request(roles.get(employee_id), text, None)


# ── 각 회사: 실제 SDK 로 한 번 ────────────────────────────────────
@pytest.mark.parametrize("name", list(PROVIDERS))
def test_generate_through_the_real_sdk(fp, name):
    cls, who = PROVIDERS[name]
    r = cls(model=roles.get(who).model).generate(_req(who))
    assert r.text.startswith("[MOCK]"), r.text[:80]
    assert r.usage.input_tokens > 0 and r.usage.output_tokens > 0
    assert len(fp.hits(name)) == 1


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_stream_through_the_real_sdk(fp, name):
    cls, who = PROVIDERS[name]
    p = cls(model=roles.get(who).model)
    joined = "".join(p.stream(_req(who)))
    assert joined == p.generate(_req(who)).text


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_stream_is_billed_from_the_wire(fp, name):
    """스트리밍도 **제공자가 알려준 사용량**으로 청구한다 (DAY 26) — 실제 SDK 의
    최종 메시지(Anthropic)·최종 응답(OpenAI)·마지막 조각(Gemini)에서 읽는다."""
    cls, who = PROVIDERS[name]
    p = cls(model=roles.get(who).model)
    "".join(p.stream(_req(who)))
    streamed = dict(usage.agents_of("wire")[who])
    p.generate(_req(who))
    both = usage.agents_of("wire")[who]
    assert streamed["calls"] == 1 and streamed["cost"] > 0
    # 같은 요청이면 스트리밍과 한 번에 받기가 같은 토큰을 센다.
    assert both["output"] == 2 * streamed["output"]
    ends = [e for e in bus.history("wire")
            if e["type"] == "call" and e["stage"] == "end" and e.get("stream")]
    assert ends and ends[-1]["estimated"] is False, "사용량을 어림으로 채웠다"


@pytest.mark.parametrize("who", list(roles.EMPLOYEES))
def test_every_employee_request_goes_through_its_real_sdk(fp, who):
    """직원 설정 **그대로**(max_tokens·effort·temperature) SDK 에 넣는다.

    개발자의 32000 토큰이 여기서 걸렸다 — 스트리밍이 아닌 `create` 는
    요청을 보내기도 전에 거절한다.
    """
    e = roles.get(who)
    cls = {"claude": ClaudeProvider, "openai": OpenAIProvider,
           "gemini": GeminiProvider}[e.provider]
    r = cls(model=e.model).generate(_req(who))
    assert r.text


def test_anthropic_sdk_still_refuses_large_non_streaming_calls(fp):
    """우리가 스트리밍으로 받는 **이유**가 아직 유효한지 지켜본다. SDK 가
    이 제한을 없애면 이 시험이 알려준다 — 그때 다시 판단하면 된다."""
    import anthropic
    c = anthropic.Anthropic(api_key=KEY, base_url=fp.root, max_retries=0)
    with pytest.raises(ValueError, match="Streaming is required"):
        c.messages.create(model=roles.get("developer").model,
                          max_tokens=roles.get("developer").max_tokens,
                          messages=[{"role": "user", "content": "x"}])
    assert not fp.hits("anthropic"), "네트워크에 닿기 **전에** 터진다"


# ── 우리가 보낸 모양 ────────────────────────────────────────────────
def test_anthropic_wire_payload(fp):
    ClaudeProvider(model="claude-opus-5").generate(_req("developer"))
    body = fp.hits("anthropic")[0]["body"]
    assert "temperature" not in body, "현재 Claude 모델은 temperature 를 400 으로 거절한다"
    assert body["output_config"] == {"effort": roles.get("developer").effort}
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["stream"] is True
    assert body["max_tokens"] == roles.get("developer").max_tokens
    assert fp.hits("anthropic")[0]["key"] == KEY


def test_openai_wire_payload(fp):
    OpenAIProvider(model="gpt-5").generate(_req("writer"))
    body = fp.hits("openai")[0]["body"]
    assert body["instructions"].startswith(roles.get("writer").system[:20])
    assert body["input"][-1] == {"role": "user", "content": "안녕"}
    assert body["max_output_tokens"] == roles.get("writer").max_tokens


def test_gemini_wire_payload(fp):
    GeminiProvider(model="gemini-2.5-pro").generate(_req("analyst"))
    hit = fp.hits("gemini")[0]
    body = hit["body"]
    assert hit["key"] == KEY
    assert "systemInstruction" in body
    assert body["generationConfig"]["maxOutputTokens"] == roles.get("analyst").max_tokens
    assert body["contents"][-1]["role"] == "user"


# ── 사용량 · 캐시 ───────────────────────────────────────────────────
def test_usage_and_cost_are_recorded_from_the_wire(fp):
    p = ClaudeProvider(model="claude-opus-5")
    p.generate(_req("developer"))
    p.generate(_req("developer"))
    row = usage.agents_of("wire")["developer"]
    assert row["calls"] == 2 and row["cost"] > 0
    assert row["cache_written"] > 0, "첫 호출은 캐시를 쓴다"
    assert row["cached"] > 0, "같은 system 의 두 번째 호출은 캐시를 읽어야 한다"
    assert usage.cache_working("wire") is True


def test_openai_cached_tokens_are_not_counted_twice(fp):
    p = OpenAIProvider(model="gpt-5")
    p.generate(_req("writer"))
    r = p.generate(_req("writer"))
    raw_in = fp.hits("openai")[1]
    assert r.usage.cached_tokens > 0
    # input_tokens 에 캐시분이 포함돼 오므로 어댑터가 빼야 한다.
    assert r.usage.input_tokens + r.usage.cached_tokens <= \
        len(raw_in["body"]["instructions"]) + 10_000


# ── 오류 · 재시도 ───────────────────────────────────────────────────
@pytest.mark.parametrize("name", list(PROVIDERS))
def test_rate_limit_retries_happen_in_one_place_only(fp, name, monkeypatch):
    """SDK 의 기본 재시도(2회)가 우리 재시도와 곱해지면 429 하나에 18번 간다."""
    monkeypatch.setattr(config, "MAX_RETRY", 2)
    cls, who = PROVIDERS[name]
    fp.fail(name, 429, times=2, headers={"retry-after": "0"})
    r = cls(model=roles.get(who).model).generate(_req(who))
    assert r.attempts == 3
    assert len(fp.hits(name)) == 3, \
        f"429 두 번에 요청이 {len(fp.hits(name))}번 나갔다 — SDK 가 따로 재시도한다"


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_retry_after_header_is_honoured(fp, name, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(base, "_sleep", lambda s: slept.append(s))
    cls, who = PROVIDERS[name]
    fp.fail(name, 429, times=1, headers={"retry-after": "7"})
    cls(model=roles.get(who).model).generate(_req(who))
    assert slept == [7.0]


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_bad_key_is_an_auth_error_and_is_not_retried(fp, name):
    cls, who = PROVIDERS[name]
    secrets_broker.set_key({"anthropic": "anthropic", "openai": "openai",
                            "gemini": "gemini"}[name], BAD_KEY)
    _reset_clients()
    with pytest.raises(AuthError):
        cls(model=roles.get(who).model).generate(_req(who))
    assert len(fp.hits(name)) == 1


@pytest.mark.parametrize("name,status", [("anthropic", 529), ("anthropic", 500),
                                         ("openai", 500), ("gemini", 503)])
def test_server_errors_are_transient_and_retried(fp, name, status, monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRY", 1)
    cls, who = PROVIDERS[name]
    fp.fail(name, status, times=5)
    with pytest.raises(TransientError):
        cls(model=roles.get(who).model).generate(_req(who))
    assert len(fp.hits(name)) == 2


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_refusals_become_refused_error(fp, name):
    cls, who = PROVIDERS[name]
    fp.refuse.add(name)
    with pytest.raises(RefusedError):
        cls(model=roles.get(who).model).generate(_req(who))


def test_fallback_chain_crosses_companies_over_the_wire(fp, monkeypatch):
    """Claude 가 계속 5xx 면 OpenAI 로 넘어간다(§18). 실제 SDK 두 개를 지난다."""
    monkeypatch.setattr(config, "MAX_RETRY", 0)
    fp.fail("anthropic", 500, times=10)
    p = registry.get("claude")
    assert isinstance(p, FallbackProvider)
    r = p.generate(_req("developer"))
    assert r.provider == "openai"
    assert fp.hits("anthropic") and fp.hits("openai")


def test_slow_provider_shows_up_in_latency(fp):
    fp.delay = 0.2
    ClaudeProvider(model="claude-opus-5").generate(_req("developer"))
    assert usage.agents_of("wire")["developer"]["latency_ms"] >= 200


# ── 회사 전체: AUTO 한 번을 실제 SDK 위에서 ─────────────────────────
def test_full_auto_run_over_the_wire(fp, monkeypatch):
    """Mock 제공자 없이 — 세 회사의 실제 SDK 가 HTTP 로 — 프로젝트 하나를 끝낸다.

    답은 직원 대본이 만든다(모델의 실력은 흉내 낼 수 없다). 그 대신 요청을
    만들고, 보내고, 받고, 읽고, 세는 전 구간이 실물과 같은 코드로 돈다.
    """
    bus.release()
    monkeypatch.setattr(credits, "WALLET_FILE", Path(config.PROJECTS).parent / "w.json")
    credits.reset()
    assert not registry.status()["all_mock"]
    slug = engine.start("간단한 계산기를 만들어주세요")
    deadline = time.time() + 120
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    m = store.meta(slug)
    assert m["status"] == "done", m.get("stopped_reason")
    assert m["mock"] is False
    assert {"anthropic", "openai", "gemini"} <= {r["provider"] for r in fp.requests}
    for who in ("strategist", "developer", "analyst", "writer", "designer"):
        assert m["usage"][who]["calls"] >= 1, who
        assert m["usage"][who]["cost"] > 0, who
    assert "src/calc.py" in store.files_of(slug)
    calls = [e for e in bus.history(slug) if e["type"] == "call" and e["stage"] == "end"]
    assert calls and all(e["ok"] for e in calls)
    credits.reset()
    bus.bind("wire")


def test_manual_instruction_over_the_wire(fp, monkeypatch):
    from app.orchestrator import manual
    bus.release()
    monkeypatch.setattr(credits, "WALLET_FILE", Path(config.PROJECTS).parent / "w.json")
    credits.reset()
    slug = manual.open_project("계산기")
    out = manual.instruct(slug, "developer", "계산기 함수를 만들어 주세요")
    assert "src/calc.py" in out["files"]
    assert fp.hits("anthropic")
    credits.reset()
    bus.bind("wire")


def test_env_base_url_is_read_at_call_time(fp):
    """시험이 서버를 띄운 **뒤에** 주소를 넣는다 — 기동 시에만 읽으면 못 쓴다."""
    assert config.base_url("anthropic") == fp.root
    assert config.base_url("openai") == fp.root + "/v1"
    assert os.environ["GEMINI_BASE_URL"] == fp.root
