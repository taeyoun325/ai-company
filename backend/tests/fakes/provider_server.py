"""세 회사의 **프로토콜**을 흉내 내는 로컬 HTTP 서버 (DAY 25).

## 왜 필요한가

테스트가 전부 Mock 위에 있었다. Mock 은 `AIProvider` 를 **대신**하므로,
그 아래 — SDK 가 만드는 HTTP 요청, SDK 가 응답을 읽는 방식, SDK 가 오류를
예외로 바꾸는 방식, SDK 자체의 재시도·시간 제한 — 는 한 줄도 돌지 않는다.
"진짜로 붙었을 때 무엇이 깨지는가"는 전부 그 구간에 있다.

키가 없다는 것은 **남의 서버**가 없다는 뜻이지, 프로토콜을 말하는 서버가
없다는 뜻이 아니다(SMTP 도 같은 방법으로 붙여봤다 — `test_mail_smtp.py`).
이 서버를 띄우고 `ANTHROPIC_BASE_URL` · `OPENAI_BASE_URL` · `GEMINI_BASE_URL`
을 여기로 돌리면, **실제 SDK 가 실제 HTTP 로** 우리 어댑터를 지난다.

## 흉내 내는 것

| | 경로 | 인증 헤더 |
|---|---|---|
| Anthropic Messages | `POST /v1/messages` (JSON · SSE) | `x-api-key` |
| OpenAI Responses | `POST /v1/responses` (JSON · SSE) | `Authorization: Bearer` |
| Gemini | `POST /v1beta/models/{m}:generateContent` · `:streamGenerateContent?alt=sse` | `x-goog-api-key` |

응답 모양은 각 회사의 공개 API 문서에 적힌 필드를 따른다. 오류도 각자의
모양(`{"type":"error","error":{...}}` · `{"error":{...}}`)과 상태 코드로 낸다.

## 흉내 내지 못하는 것 (정직하게)

- **모델의 실력.** 답은 `brain` 이 만든다(기본: 직원 대본 `mock_script`).
- **진짜 서버만의 규칙.** 모르는 필드를 400 으로 거절하는지, 모델 이름을
  받는지, 토큰을 어떻게 세는지. 여기서는 요청을 **기록**해 두고, 시험이
  우리가 보낸 모양을 검사한다.
- **TLS · 실제 네트워크 지연 · 실제 요율 제한 정책.**

그래서 이 서버를 통과한다고 실물이 보장되지는 않는다. 다만 SDK 시그니처,
응답 파싱, 사용량 해석, 스트리밍, 오류 번역, 재시도 겹침 — Mock 이 볼 수
없던 구간은 **키 없이** 전부 돈다.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

BAD_KEY = "bad-key"

Brain = Callable[[str, dict], str]   # (provider, 번역된 요청) -> 답 글


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


def default_brain(provider: str, req: dict) -> str:
    """직원 대본으로 답한다 — AUTO 전 구간이 실제 SDK 위에서 돌 수 있게."""
    from app.agents import mock_script
    from app.providers.base import GenerateRequest, Message
    gr = GenerateRequest(
        system=req["system"],
        messages=[Message(m["role"], m["content"]) for m in req["messages"]],
        model=req["model"], max_tokens=req["max_tokens"])
    return mock_script.responder(gr)


class Fault:
    def __init__(self, status: int, times: int = 1,
                 headers: dict | None = None, kind: str | None = None):
        self.status = status
        self.times = times
        self.headers = headers or {}
        self.kind = kind


class FakeProviders:
    """`with FakeProviders() as fp:` — 서버를 띄우고 주소를 알려준다."""

    def __init__(self, brain: Brain | None = None, delay: float = 0.0):
        self.brain = brain or default_brain
        self.delay = delay
        self.requests: list[dict] = []
        self.faults: dict[str, deque[Fault]] = defaultdict(deque)
        # 같은 system 을 두 번째 보면 캐시가 걸린 것으로 답한다.
        self._seen_prefix: set[str] = set()
        self.refuse: set[str] = set()
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ── 수명 ──────────────────────────────────────────────────────
    def __enter__(self) -> "FakeProviders":
        fake = self

        class Handler(_Handler):
            owner = fake

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True, name="fake-providers")
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    @property
    def root(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def env(self) -> dict[str, str]:
        """각 SDK 가 기대하는 모양의 주소. OpenAI 만 `/v1` 까지 붙인다."""
        return {"ANTHROPIC_BASE_URL": self.root,
                "OPENAI_BASE_URL": f"{self.root}/v1",
                "GEMINI_BASE_URL": self.root}

    # ── 시험이 조종하는 것 ────────────────────────────────────────
    def fail(self, provider: str, status: int, times: int = 1,
             headers: dict | None = None, kind: str | None = None) -> None:
        self.faults[provider].append(Fault(status, times, headers, kind))

    def hits(self, provider: str) -> list[dict]:
        return [r for r in self.requests if r["provider"] == provider]

    # ── 내부 ──────────────────────────────────────────────────────
    def _take_fault(self, provider: str) -> Fault | None:
        with self._lock:
            q = self.faults.get(provider)
            if not q:
                return None
            f = q[0]
            f.times -= 1
            if f.times <= 0:
                q.popleft()
            return f

    def _cached(self, system: str) -> int:
        with self._lock:
            if system in self._seen_prefix:
                return _tokens(system)
            self._seen_prefix.add(system)
            return 0


# ── 요청 번역 ───────────────────────────────────────────────────────
def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for block in content or []:
        if isinstance(block, dict):
            out.append(block.get("text") or "")
    return "".join(out)


def _from_anthropic(body: dict) -> dict:
    system = body.get("system")
    return {"model": body.get("model"), "max_tokens": body.get("max_tokens", 0),
            "system": _text_of(system) if not isinstance(system, str) else system,
            "messages": [{"role": m["role"], "content": _text_of(m["content"])}
                         for m in body.get("messages", [])],
            "stream": bool(body.get("stream"))}


def _from_openai(body: dict) -> dict:
    items = body.get("input")
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    return {"model": body.get("model"),
            "max_tokens": body.get("max_output_tokens", 0),
            "system": body.get("instructions") or "",
            "messages": [{"role": m.get("role", "user"),
                          "content": _text_of(m.get("content"))}
                         for m in items or []],
            "stream": bool(body.get("stream"))}


def _from_gemini(body: dict, model: str) -> dict:
    si = body.get("systemInstruction") or body.get("system_instruction") or {}
    system = _text_of(si.get("parts")) if isinstance(si, dict) else str(si)
    cfg = body.get("generationConfig") or {}
    return {"model": model, "max_tokens": cfg.get("maxOutputTokens", 0),
            "system": system,
            "messages": [{"role": "assistant" if c.get("role") == "model" else "user",
                          "content": _text_of(c.get("parts"))}
                         for c in body.get("contents", [])]}


# ── 응답 ────────────────────────────────────────────────────────────
_ANTHROPIC_ERR = {400: "invalid_request_error", 401: "authentication_error",
                  403: "permission_error", 429: "rate_limit_error",
                  500: "api_error", 529: "overloaded_error"}
_GEMINI_STATUS = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED",
                  403: "PERMISSION_DENIED", 429: "RESOURCE_EXHAUSTED",
                  500: "INTERNAL", 503: "UNAVAILABLE"}


class _Handler(BaseHTTPRequestHandler):
    owner: FakeProviders
    protocol_version = "HTTP/1.0"      # 스트림은 연결을 닫아서 끝낸다

    def log_message(self, *a):          # 테스트 출력을 더럽히지 않는다
        pass

    # ── 공통 ──────────────────────────────────────────────────────
    def _json(self, status: int, body: dict, headers: dict | None = None) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.send_header("request-id", "req_" + uuid.uuid4().hex[:8])
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _sse_start(self) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()

    def _sse(self, event: str | None, data: dict) -> None:
        chunk = (f"event: {event}\n" if event else "") + \
            f"data: {json.dumps(data)}\n\n"
        self.wfile.write(chunk.encode("utf-8"))
        self.wfile.flush()

    def _record(self, provider: str, body: dict, key: str | None) -> None:
        with self.owner._lock:
            self.owner.requests.append({
                "provider": provider, "path": self.path, "body": body,
                "key": key, "headers": dict(self.headers), "at": time.time()})

    def do_POST(self):                  # noqa: N802 — http.server 의 이름
        length = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        if self.owner.delay:
            time.sleep(self.owner.delay)
        path = self.path.split("?", 1)[0]
        if path.endswith("/v1/messages"):
            return self._anthropic(body)
        if path.endswith("/v1/responses"):
            return self._openai(body)
        m = re.search(r"/models/([^/:]+):(generateContent|streamGenerateContent)$", path)
        if m:
            return self._gemini(body, m.group(1), m.group(2) == "streamGenerateContent")
        self._json(404, {"error": {"message": f"no route {path}"}})

    # ── Anthropic ─────────────────────────────────────────────────
    def _anthropic(self, body: dict) -> None:
        key = self.headers.get("x-api-key")
        self._record("anthropic", body, key)
        err = self._auth_or_fault("anthropic", key)
        if err:
            status, headers, kind = err
            return self._json(status, {"type": "error", "error": {
                "type": kind or _ANTHROPIC_ERR.get(status, "api_error"),
                "message": f"fake {status}"}}, headers)
        req = _from_anthropic(body)
        if "anthropic" in self.owner.refuse:
            text, stop = "", "refusal"
        else:
            text, stop = self.owner.brain("anthropic", req), "end_turn"
        cached = self.owner._cached(req["system"])
        usage = {"input_tokens": _tokens(json.dumps(req["messages"])),
                 "output_tokens": _tokens(text) if text else 0,
                 "cache_creation_input_tokens": 0 if cached else _tokens(req["system"]),
                 "cache_read_input_tokens": cached}
        msg_id = "msg_" + uuid.uuid4().hex[:12]
        if not req["stream"]:
            return self._json(200, {
                "id": msg_id, "type": "message", "role": "assistant",
                "model": req["model"],
                "content": [{"type": "text", "text": text}] if text else [],
                "stop_reason": stop, "stop_sequence": None, "usage": usage})
        self._sse_start()
        self._sse("message_start", {"type": "message_start", "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "model": req["model"], "content": [], "stop_reason": None,
            "stop_sequence": None, "usage": {**usage, "output_tokens": 1}}})
        if text:
            self._sse("content_block_start", {"type": "content_block_start",
                                              "index": 0, "content_block":
                                              {"type": "text", "text": ""}})
            self._sse("ping", {"type": "ping"})
            for i in range(0, len(text), 40):
                self._sse("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": text[i:i + 40]}})
            self._sse("content_block_stop", {"type": "content_block_stop",
                                             "index": 0})
        self._sse("message_delta", {"type": "message_delta",
                                    "delta": {"stop_reason": stop,
                                              "stop_sequence": None},
                                    "usage": {"output_tokens": usage["output_tokens"]}})
        self._sse("message_stop", {"type": "message_stop"})

    # ── OpenAI ────────────────────────────────────────────────────
    def _openai(self, body: dict) -> None:
        auth = self.headers.get("authorization") or ""
        key = auth[7:] if auth.lower().startswith("bearer ") else None
        self._record("openai", body, key)
        err = self._auth_or_fault("openai", key)
        if err:
            status, headers, kind = err
            code = {401: "invalid_api_key", 429: "rate_limit_exceeded"}.get(
                status, "server_error")
            return self._json(status, {"error": {"message": f"fake {status}",
                                                 "type": kind or code,
                                                 "param": None, "code": code}},
                              headers)
        req = _from_openai(body)
        refused = "openai" in self.owner.refuse
        text = "" if refused else self.owner.brain("openai", req)
        cached = self.owner._cached(req["system"])
        in_tok = _tokens(req["system"] + json.dumps(req["messages"]))
        usage = {"input_tokens": in_tok,
                 "input_tokens_details": {"cached_tokens": min(cached, in_tok)},
                 "output_tokens": _tokens(text) if text else 0,
                 "output_tokens_details": {"reasoning_tokens": 0},
                 "total_tokens": in_tok + (_tokens(text) if text else 0)}
        rid, mid = "resp_" + uuid.uuid4().hex[:12], "msg_" + uuid.uuid4().hex[:12]
        part = ({"type": "refusal", "refusal": "no"} if refused
                else {"type": "output_text", "text": text, "annotations": []})
        item = {"type": "message", "id": mid, "status": "completed",
                "role": "assistant", "content": [part]}

        def response(status: str, output: list, with_usage: bool) -> dict:
            return {"id": rid, "object": "response", "created_at": int(time.time()),
                    "status": status, "error": None, "incomplete_details": None,
                    "instructions": req["system"],
                    "max_output_tokens": body.get("max_output_tokens"),
                    "model": req["model"], "output": output,
                    "parallel_tool_calls": True,
                    "temperature": body.get("temperature"), "tool_choice": "auto",
                    "tools": [], "top_p": 1.0, "text": {"format": {"type": "text"}},
                    "truncation": "disabled", "metadata": {},
                    "usage": usage if with_usage else None}

        if not req["stream"]:
            return self._json(200, response("completed", [item], True))
        self._sse_start()
        seq = iter(range(10_000))

        def ev(kind: str, **payload) -> None:
            self._sse(kind, {"type": kind, "sequence_number": next(seq), **payload})

        ev("response.created", response=response("in_progress", [], False))
        ev("response.in_progress", response=response("in_progress", [], False))
        ev("response.output_item.added", output_index=0,
           item={**item, "status": "in_progress", "content": []})
        ev("response.content_part.added", item_id=mid, output_index=0,
           content_index=0, part={**part, "text": ""} if not refused else part)
        if not refused:
            for i in range(0, len(text), 40):
                ev("response.output_text.delta", item_id=mid, output_index=0,
                   content_index=0, delta=text[i:i + 40], logprobs=[])
            ev("response.output_text.done", item_id=mid, output_index=0,
               content_index=0, text=text, logprobs=[])
        ev("response.content_part.done", item_id=mid, output_index=0,
           content_index=0, part=part)
        ev("response.output_item.done", output_index=0, item=item)
        ev("response.completed", response=response("completed", [item], True))

    # ── Gemini ────────────────────────────────────────────────────
    def _gemini(self, body: dict, model: str, stream: bool) -> None:
        key = self.headers.get("x-goog-api-key")
        self._record("gemini", {**body, "_model": model, "_stream": stream}, key)
        err = self._auth_or_fault("gemini", key)
        if err:
            status, headers, _ = err
            return self._json(status, {"error": {
                "code": status, "message": f"fake {status}",
                "status": _GEMINI_STATUS.get(status, "UNKNOWN")}}, headers)
        req = _from_gemini(body, model)
        refused = "gemini" in self.owner.refuse
        text = "" if refused else self.owner.brain("gemini", req)
        prompt = _tokens(req["system"] + json.dumps(req["messages"]))
        usage = {"promptTokenCount": prompt,
                 "candidatesTokenCount": _tokens(text) if text else 0,
                 "totalTokenCount": prompt + (_tokens(text) if text else 0)}
        finish = "SAFETY" if refused else "STOP"

        def chunk(piece: str, last: bool) -> dict:
            cand = {"index": 0, "content": {"role": "model",
                                            "parts": [{"text": piece}] if piece else []}}
            if last:
                cand["finishReason"] = finish
            out = {"candidates": [cand], "modelVersion": model,
                   "responseId": uuid.uuid4().hex[:12]}
            if last:
                out["usageMetadata"] = usage
            return out

        if not stream:
            return self._json(200, chunk(text, True))
        self._sse_start()
        pieces = [text[i:i + 40] for i in range(0, len(text), 40)] or [""]
        for i, p in enumerate(pieces):
            self._sse(None, chunk(p, i == len(pieces) - 1))

    # ── 인증 · 장애 ───────────────────────────────────────────────
    def _auth_or_fault(self, provider: str, key: str | None):
        if not key or key == BAD_KEY:
            return 401, {}, None
        f = self.owner._take_fault(provider)
        if f is None:
            return None
        return f.status, f.headers, f.kind
