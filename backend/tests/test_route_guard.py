"""모든 API 경로의 문단속 (DAY 27).

라우트마다 손으로 검사를 불러 왔다. DAY 27 에 전 경로를 로그인 없이 불러 보니
작업 로그(`/api/events`·`/api/stream`), 첨부 목록·업로드·미리보기, 원가·마진,
전체 색인 재구축이 열려 있었다 — 첨부 목록에서 id 를 얻어 미리보기를 부르면
**남의 이미지 원본**이 나왔다. 한 곳을 고치는 것으로 끝내지 않고, 경로 목록
전체를 두 사람(로그인 안 한 사람 · 다른 테넌트)으로 두드린다. 새 경로가 생기면
여기서 저절로 걸린다.

본문 검증(422)이 인증보다 먼저 거절하면 "막혔다"로 보인다. 그래서 경로마다
**통과하는 본문**을 스키마에서 만들어 보낸다.
"""
import sys
import time
import typing
from pathlib import Path

import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from fastapi.testclient import TestClient                       # noqa: E402

from app import attachments, config, main                       # noqa: E402
from app.auth import service, store                              # noqa: E402
from app.database import index                                   # noqa: E402
from app.orchestrator import engine                              # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402

PW = "정말로긴비밀번호2026"

# 로그인 전에도 열려 있어야 하는 것. 이유를 함께 적는다 — 이유를 못 적으면 닫는다.
PUBLIC = {
    "/api/deploy": "헬스 체크 (Cloud Run 시작·생존 검사)",
    "/api/preflight": "배포 점검 — 운영자가 curl 로 본다 (docs/deploy.md §5)",
    "/api/plans": "랜딩의 요금제. 로그인 안 했으면 사용량을 재지 않는다",
    "/api/settings": "운영자 키의 유무·모델 목록뿐, 테넌트 데이터 없음",
    "/api/providers": "직원별 Mock 여부뿐, 테넌트 데이터 없음",
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("SSE_MAX_SECONDS", "0.3")
    monkeypatch.setattr(main, "SSE_MAX_SECONDS", 0.3)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(attachments, "DIR", tmp_path / "attachments")
    monkeypatch.setattr(attachments, "_meta", {})
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
    monkeypatch.setattr(main, "_run_owner_cache", {})
    store.close()
    index.close()
    credits.reset()
    service.reset_rate_limits()
    registry.reset()
    yield
    store.close()
    index.close()
    credits.reset()
    registry.reset()


def _signed_up(email: str) -> TestClient:
    c = TestClient(main.app)
    r = c.post("/api/auth/signup", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return c


def _alice_world():
    alice = _signed_up("alice@example.com")
    assert alice.post("/api/credits/plan", json={"plan": "pro"}).status_code == 200
    aid = alice.post("/api/attachments",
                     files={"file": ("secret.png", b"\x89PNG\r\n\x1a\nALICE", "image/png")}
                     ).json()["id"]
    slug = alice.post("/api/runs", json={"requirement": "계산기", "attachments": [aid]}).json()["slug"]
    deadline = time.time() + 60
    while engine.is_running(slug) and time.time() < deadline:
        time.sleep(0.05)
    return alice, slug, aid


# ── 통과하는 요청 만들기 ─────────────────────────────────────────────
def _value(tp):
    origin = typing.get_origin(tp)
    if origin is typing.Union or str(origin) == "types.UnionType":
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return _value(args[0]) if args else None
    if origin in (list, tuple, set):
        return []
    if origin is dict or tp is dict:
        return {}
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return _body_of(tp)
    return {str: "x", int: 1, float: 1.0, bool: True}.get(tp, "x")


def _body_of(model) -> dict:
    return {name: _value(f.annotation) for name, f in model.model_fields.items()
            if f.is_required()}


def _request_for(route, ids: dict):
    url = route.path
    for k, v in ids.items():
        url = url.replace("{" + k + "}", v)
    params = {p.name: "src/calc.py" if p.name == "path" else _value(p.field_info.annotation)
              for p in route.dependant.query_params if p.field_info.is_required()}
    body = None
    for bp in route.dependant.body_params:
        tp = bp.field_info.annotation if hasattr(bp.field_info, "annotation") else None
        if isinstance(tp, type) and issubclass(tp, BaseModel):
            body = _body_of(tp)
    return url, params, body


def _api_routes():
    for r in main.app.routes:
        methods = getattr(r, "methods", None)
        if methods and r.path.startswith("/api") and not r.path.startswith("/api/auth"):
            for m in sorted(methods - {"HEAD", "OPTIONS"}):
                yield m, r


def test_nothing_opens_without_signing_in():
    _alice, slug, aid = _alice_world()
    anon = TestClient(main.app)
    ids = {"slug": slug, "run": slug, "aid": aid, "sid": slug, "employee_id": "pm",
           "approval_id": "x", "provider": "claude"}
    opened = []
    for method, route in _api_routes():
        if route.path in PUBLIC:
            continue
        url, params, body = _request_for(route, ids)
        if route.path == "/api/attachments" and method == "POST":
            r = anon.post(url, files={"file": ("a.txt", b"x", "text/plain")})
        else:
            r = anon.request(method, url, params=params, json=body)
        if r.status_code < 400 or r.status_code == 422:
            opened.append(f"{method} {route.path} → {r.status_code}")
    assert not opened, "로그인 없이 열린다:\n" + "\n".join(opened)


def test_another_tenant_sees_nothing_of_alices():
    _alice, slug, aid = _alice_world()
    bob = _signed_up("bob@example.com")
    ids = {"slug": slug, "run": slug, "aid": aid, "sid": slug, "employee_id": "pm",
           "approval_id": "x", "provider": "claude"}
    leaked = []
    for method, route in _api_routes():
        if not any("{" + k + "}" in route.path for k in ("slug", "run", "aid", "sid")):
            continue
        url, params, body = _request_for(route, ids)
        r = bob.request(method, url, params=params, json=body)
        if r.status_code < 400:
            leaked.append(f"{method} {route.path} → {r.status_code}")
    # 목록·이벤트: 경로에 id 가 없어도 내용에 alice 의 것이 섞이면 안 된다
    for method, url, params in [("GET", "/api/attachments", {}),
                                ("GET", "/api/projects", {}),
                                ("GET", "/api/events", {}),
                                ("GET", "/api/events", {"run": slug}),
                                ("GET", "/api/stream", {}),
                                ("GET", "/api/stream", {"run": slug})]:
        r = bob.request(method, url, params=params)
        if r.status_code < 400 and (aid in r.text or slug in r.text or "ALICE" in r.text):
            leaked.append(f"{method} {url} {params} → alice 의 것이 보인다")
    assert not leaked, "다른 테넌트에게 새어 나간다:\n" + "\n".join(leaked)


def test_owner_still_sees_her_own():
    """막는 것만 보면 다 막아 버려도 통과한다. 주인에게는 보여야 한다."""
    alice, slug, aid = _alice_world()
    assert alice.get(f"/api/attachments/{aid}/preview").status_code == 200
    assert aid in alice.get("/api/attachments").text
    ev = alice.get("/api/events", params={"run": slug}).json()["events"]
    assert ev, "주인이 자기 작업 로그를 못 본다"
    body = alice.get("/api/stream", params={"run": slug}).text
    assert "id: " in body, "주인의 SSE 에 이벤트가 없다"


def test_attachments_survive_a_restart():
    """메타데이터가 메모리에만 있어서 서버가 다시 뜨면 파일을 못 찾았다."""
    alice, _slug, aid = _alice_world()
    attachments._meta.clear()                       # 다시 뜬 프로세스
    assert alice.get(f"/api/attachments/{aid}/preview").status_code == 200


def test_operator_screens_need_an_operator(monkeypatch):
    alice, _slug, _aid = _alice_world()
    assert alice.get("/api/margin").status_code == 403
    assert alice.post("/api/projects/reindex").status_code == 403
    monkeypatch.setenv("OPERATOR_EMAILS", "Alice@Example.com")
    assert alice.get("/api/margin").status_code == 200
    assert alice.post("/api/projects/reindex").status_code == 200
