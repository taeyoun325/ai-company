"""AI COMPANY 백엔드 — FastAPI 앱.

진행 상황은 SSE(`/api/stream`)로 흘러나간다.

  python backend/run.py                키 없이 Mock 으로 실행
  python backend/run.py --dir <경로>    이전 제품의 작업 폴더를 열고 실행

라우트가 늘어나면 `app/api/` 로 쪼갠다.
"""
import json
import queue
import sys
import time

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agents import core as agent_core
from app import approvals
from app import attachments
from app import bus
from app import byok
from app import config
from app import deploy
from app import lang
from app import narrator
from app.api import auth as auth_api
from app.api import local_tools
from app.auth import deps as auth
from app import preflight
from app.providers import gemini_client as gemini
from app.providers import registry
from app import scheduler
from app import screen
from app import secrets_broker
from app.agents import employee as employees
from app.agents import roles
from app.agents import staff
from app.agents import subagents
from app.database import index as project_index
from app.database import store
from app import orchestrator
from app.orchestrator import manual
from app import tenant
from app import timeline
from app import usage
from app.usage import credits
from app import workspace

secrets_broker.init()   # 기동 즉시 환경변수에서 키를 꺼내 지운다

# 색인이 비어 있는데 디스크에 프로젝트가 있으면 다시 만든다 (§12).
# 산출물은 멀쩡한데 목록만 비어 있으면 사용자는 잃어버렸다고 생각한다.
_INDEX_READY = project_index.ensure_ready()

# 프로세스가 죽으면 '진행 중'을 끝낼 사람이 없다. 기동 시 한 번 치운다 —
# 안 치우면 목록에 좀비가 쌓이고, 화면은 오지 않는 로그를 기다린다.
_SWEPT = orchestrator.sweep_stale_runs()

app = FastAPI(title="AI Agent Company")


@app.middleware("http")
async def _language(request: Request, call_next):
    """이 요청의 언어를 정한다 (DAY 21 · app/lang.py).

    라우트마다 헤더를 읽지 않는 이유는 늘 같다 — 하나를 빠뜨리면 그
    화면만 한국어로 돌아가고, 사용자는 번역이 깨졌다고 생각한다.

    ## `?lang=` 이 헤더보다 먼저다 (DAY 22)

    **EventSource 는 헤더를 보낼 수 없다.** 그래서 실시간 로그(SSE)만
    `Accept-Language` 없이 들어오고, 그 요청에서 만들어지는 것들(직원
    로스터의 직함 등)이 기본값인 한국어로 나갔다 — 영어 화면의 모든
    말풍선에 "(전략가)" 가 붙어 있었다. 화면이 주소에 언어를 적어 보내고,
    여기서 그것을 먼저 본다.
    """
    lang.set(lang.from_query(request.query_params.get("lang"))
             or lang.from_header(request.headers.get("accept-language")))
    return await call_next(request)
app.include_router(auth_api.router)
# 이전 제품(로컬 개발도구)의 라우트. DEPLOY_MODE=saas 에서는 전부 403.
app.include_router(local_tools.router)


# ── 요청 모델 ───────────────────────────────────────────────────────
class SendReq(BaseModel):
    message: str
    attachments: list[str] = []


class OpenReq(BaseModel):
    path: str


class ModeReq(BaseModel):
    mode: str


class KeysReq(BaseModel):
    anthropic: str | None = None
    gemini: str | None = None
    openai: str | None = None
    remember: bool = False


class StaffReq(BaseModel):
    """이름과 채용 여부. 권한은 여기 없다 — 자리의 것이라 바꿀 수 없다."""
    name: str | None = None
    active: bool | None = None


class ByokReq(BaseModel):
    """고객 자신의 키. 운영자 키(`KeysReq`)와 **모델부터 다르다** —
    같은 모델을 재사용하면 언젠가 같은 저장소로 흘러간다."""
    anthropic: str | None = None
    gemini: str | None = None
    openai: str | None = None


class ModelReq(BaseModel):
    qa_model: str


class ProviderModelReq(BaseModel):
    provider: str
    model: str


class ModelReq2(BaseModel):
    model: str


class PlanReq(BaseModel):
    plan: str


class TopUpReq(BaseModel):
    credits: float


class RunReq(BaseModel):
    requirement: str
    attachments: list[str] = []


class InstructReq(BaseModel):
    employee: str
    message: str


class DecisionReq(BaseModel):
    decision: str


class EditReq(BaseModel):
    path: str
    content: str


class ScheduleReq(BaseModel):
    requirement: str
    at: str
    days: list[int] = []
    enabled: bool = True


class SchedulePatch(BaseModel):
    requirement: str | None = None
    at: str | None = None
    days: list[int] | None = None
    enabled: bool | None = None


@app.get("/")
def index():
    """백엔드 루트. **화면이 아니다.**

    DAY 17 전에는 이전 제품의 단일 파일 UI(38KB)를 여기서 서빙했다.
    지금 화면은 Next.js 쪽이고, 백엔드 루트에 또 하나의 UI 가 떠 있으면
    "어느 쪽이 진짜인가"를 매번 헷갈린다. 그 파일은 legacy/web/ 으로
    옮겼다 — 지우지 않은 이유는 설계 기록이기 때문이다.
    """
    return {"service": "ai-company-backend",
            "ui": "프론트엔드(기본 :3000)로 접속하세요",
            "deploy": deploy.mode(),
            "docs": "/docs"}


# ── 상태 ────────────────────────────────────────────────────────────
@app.get("/api/state")
def state(request: Request, run: str | None = None):
    """`run` 을 주면 그 실행의 직원별 사용량이 함께 온다.

    안 주면 0 으로 나온다 — 사용량은 실행별 스레드 로컬이고, 이 요청은
    다른 스레드에서 처리되기 때문이다(§14).
    """
    run = _my_run(request, run)
    return {
        "workspace": workspace.summary(),
        "permission": approvals.mode_info(),
        # 지시서 §8 의 직원 5명. subagents 는 이전 제품의 보조 에이전트이고
        # 다른 것이다 — 화면이 둘을 섞으면 누가 일하는지 알 수 없게 된다.
        "employees": employees.status(run),
        "agents": subagents.roster(),
        "models": config.MODEL_OF,
        "keys_ready": secrets_broker.ready(),
        # 화면이 "지금 Mock 으로 돌고 있다"를 표시할 수 있어야 한다.
        # 안 그러면 사용자는 Mock 이 지어낸 글을 AI 의 작업 결과로 믿는다.
        "providers": registry.status(),
        "credits": credits.status(auth.owner_of(request)),
        "user": auth.require_user(request).public(),
        # 무엇이 막혀 있는지 화면이 말할 수 있어야 한다. 감추면 사용자는
        # 기능이 고장 났다고 생각한다.
        "deploy": deploy.status(),
        "busy": agent_core.busy(),
        "turns": len(agent_core.history),
        "screen": screen.status(),
    }


def _my_run(request: Request, run: str | None) -> str | None:
    """`run` 이 내 프로젝트인가. 아니면 None 으로 떨어뜨린다.

    이 파라미터는 실행별 사용량을 불러오는 데 쓴다(§14). 검사하지 않으면
    남의 slug 를 넣어 **그 프로젝트의 직원별 토큰·비용을 볼 수 있다.**
    소유권 검사를 목록에만 걸고 이런 부수적인 파라미터에 빼먹는 것이
    테넌트 분리가 뚫리는 가장 흔한 방식이다.

    404 로 막지 않고 조용히 None 으로 떨어뜨리는 이유: 이건 화면을
    그리는 보조 정보라, 남의 slug 하나 때문에 상태 조회 전체가 실패하면
    화면이 통째로 빈다. 정보는 안 주되 화면은 뜬다.
    """
    if not run:
        return None
    m = store.meta(run)
    return run if m and auth.owns(request, m.get("owner")) else None


def _require_local_tools() -> None:
    """로컬 환경을 건드리는 기능의 공통 관문 (§18 · app/deploy.py).

    이 검사를 라우트마다 손으로 넣지 않고 한 함수로 모은 이유: 라우트가
    늘어날 때 하나를 빠뜨리면, 그 하나가 통째로 구멍이 된다.
    """
    if (reason := deploy.allow_local_tools()) is not None:
        raise HTTPException(403, reason)


# ── 설정: API 키와 모델 ─────────────────────────────────────────────
def _operator_only() -> None:
    """운영자 키·기본 모델을 만지는 경로의 공통 관문 (DAY 19 · app/deploy.py).

    DAY 18 까지 이 라우트들은 아무 가드도 없었다. 로컬 도구에서는 맞는
    설계였지만, SaaS 에서는 **로그인한 아무 테넌트나 운영자 키를
    덮어쓰거나 지울 수 있다**는 뜻이었다. 요금제를 붙이는 순간 이건
    구멍 정도가 아니라 서비스 정지 버튼이다.
    """
    if (reason := deploy.allow_operator_settings()) is not None:
        raise HTTPException(403, reason)


@app.get("/api/settings")
def get_settings():
    # SaaS 에서는 운영자 키의 마스크조차 내보내지 않는다. 고객이 볼 이유가
    # 없고, 앞 6자리는 어떤 계정의 키인지 좁히는 단서가 된다.
    keys = ({n: {"label": lbl, "set": secrets_broker.has(n), "masked": None}
             for n, (_e, lbl) in secrets_broker.KEYS.items()}
            if deploy.is_saas() else secrets_broker.status())
    return {"keys": keys, "models": config.MODEL_OF,
            "operator_settings": deploy.allow_operator_settings() is None,
            "catalog": {n: {"default": config.default_model(n),
                            "models": config.models_of(n)}
                        for n in registry.names()},
            "stored": secrets_broker.STORE_PATH.exists(),
            "missing": secrets_broker.missing(),
            "ready": secrets_broker.ready()}


@app.post("/api/settings/keys")
def set_keys(req: KeysReq):
    _operator_only()
    changed = []
    for name in secrets_broker.KEYS:
        val = getattr(req, name)
        if val is None:
            continue
        secrets_broker.set_key(name, val)
        changed.append(name)
    if req.remember:
        secrets_broker.persist()
    if "anthropic" in changed:
        try:
            from app.providers import anthropic_client as llm
            llm.reset_client()
        except ImportError:
            pass
    if "gemini" in changed:
        gemini.reset_client()
    if "openai" in changed:
        try:
            from app.providers import openai_client
            openai_client.reset_client()
        except ImportError:
            pass
    if changed:
        # 키가 생겼으면 다음 호출부터는 Mock 이 아니라 실제로 가야 한다.
        registry.reset()
    return {"ok": True, "keys": secrets_broker.status(),
            "providers": registry.status(),
            "ready": secrets_broker.ready(),
            "stored": secrets_broker.STORE_PATH.exists()}


@app.post("/api/settings/forget")
def forget_keys():
    _operator_only()
    secrets_broker.forget_stored()
    return {"ok": True, "stored": False}


@app.post("/api/settings/verify/{provider}")
def verify_key(provider: str):
    _operator_only()
    try:
        if provider == "anthropic":
            from app.providers import anthropic_client as llm
            models = [m.id for m in llm.client().models.list()]
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:40]}
        if provider == "gemini":
            models = gemini.list_models()
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:60]}
        if provider == "openai":
            from app.providers import openai_client
            models = openai_client.list_models()
            return {"ok": True, "detail": f"모델 {len(models)}개 조회됨",
                    "models": models[:60]}
        raise HTTPException(400, lang.t("err.unknownProvider", name=""))
    except HTTPException:
        raise
    except ImportError as e:
        pkg = {"anthropic": "anthropic", "gemini": "google-genai",
               "openai": "openai"}.get(provider, provider)
        return {"ok": False,
                "detail": f"{pkg} 패키지가 설치되지 않았습니다. "
                          f"pip install -r requirements.txt 를 실행하세요. ({e})"}
    except Exception as e:
        return {"ok": False, "detail": secrets_broker.scrub(f"{type(e).__name__}: {e}")}


@app.post("/api/settings/qa-model")
def set_qa_model(req: ModelReq):
    _operator_only()
    config.QA_MODEL = req.qa_model
    config.MODEL_OF["QA"] = req.qa_model
    config.PRICES.setdefault(req.qa_model, config.PRICES.get("gemini-2.5-pro", (0.0, 0.0)))
    return {"ok": True, "models": config.MODEL_OF}


@app.post("/api/settings/model")
def set_provider_model(req: ProviderModelReq):
    """제공자의 기본 모델을 바꾼다 (§7 모델 설정).

    카탈로그 밖의 모델도 허용한다 — 모델 ID 는 시점에 따라 바뀌고,
    `models.json` 이 낡았다는 이유로 새 모델을 못 쓰게 막으면 파일을
    코드 밖에 둔 의미가 없다. 다만 **단가를 모르는 모델**은 거부한다:
    단가가 없으면 비용이 0 으로 잡히고, 0 은 공짜가 아니라 모른다는 뜻이며,
    예산 상한(§18)이 그 모델에는 걸리지 않게 된다.
    """
    _operator_only()
    if req.provider not in registry.names():
        raise HTTPException(400, lang.t("err.unknownProvider", name=req.provider))
    if req.model not in config.PRICES:
        raise HTTPException(400, lang.t("err.modelNotPriced", model=req.model))
    config.CATALOG.setdefault(req.provider, {"models": []})["default"] = req.model
    registry.reset()
    return {"ok": True, "provider": req.provider, "model": req.model,
            "providers": registry.status()}


# ── AI 제공자 (지시서 §7) ───────────────────────────────────────────
@app.get("/api/providers")
def providers():
    """어떤 직원이 실제 모델로 일하고, 어떤 직원이 Mock 인지.

    `mock: true` 인데 화면이 그걸 안 보여주면 시연에서 아무도 진짜와
    가짜를 구분하지 못한다.
    """
    return registry.status()


# ── 실행 (지시서 §9 · §10 AUTO) ─────────────────────────────────────
@app.post("/api/runs")
def start_run(req: RunReq, request: Request):
    """AUTO 모드. 오케스트레이터가 직원을 골라 끝까지 돌린다.

    키가 없어도 막지 않는다 — Mock 으로 전 구간을 만드는 것이 현재 방침이고,
    Mock 으로 돌고 있다는 사실은 `mock: true` 로 화면까지 전달된다.
    """
    requirement = req.requirement.strip()
    if not requirement:
        raise HTTPException(400, lang.t("err.emptyRequirement"))
    owner = auth.owner_of(request)
    try:
        slug = orchestrator.start(requirement, req.attachments, owner=owner)
    except tenant.NoPlan as e:
        # 이건 진짜로 결제 문제다 — 무료 요금제가 없으므로, 고르기 전에는
        # 아무것도 시작할 수 없다.
        raise HTTPException(402, str(e))
    except tenant.KeysMissing as e:
        # 402(결제 필요)로 보내지 않는다. 돈 문제가 아니라 **설정** 문제이고,
        # 사용자가 할 일이 다르다 — 충전이 아니라 키 등록이다.
        raise HTTPException(409, str(e))
    except credits.InsufficientCredits as e:
        # 429(한도 초과)와 구분한다. 사용자의 대응이 다르다 —
        # 하나는 기다리면 되고, 하나는 충전해야 한다.
        raise HTTPException(402, str(e))
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    # **이 테넌트의 자세로** 판단한다. 밖에서 부르면 운영자 기준으로
    # 답하게 되고, 무료(Mock) 사용자에게 "실제 모델이 일합니다"라고
    # 말하거나 그 반대가 된다.
    with tenant.bind(owner):
        is_mock = registry.status()["all_mock"]
    return {"slug": slug, "running": True, "mock": is_mock}


@app.get("/api/runs")
def list_runs(request: Request):
    """**내** 실행만. 진행 중 목록도 걸러야 한다 — 남의 slug 가 보이면
    그 자체로 남의 프로젝트가 존재한다는 정보다."""
    owner = auth.owner_of(request)
    mine = {p["slug"] for p in store.list_projects(owner)}
    return {"running": [s for s in orchestrator.running_slugs() if s in mine],
            "projects": store.list_projects(owner)}


@app.get("/api/runs/{slug}")
def get_run(slug: str, request: Request):
    m = store.meta(slug)
    if not m:
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, m.get("owner"))
    m["running"] = orchestrator.is_running(slug)
    m["updated_at"] = store.touched_at(slug)
    m["events"] = bus.history(slug)
    return m


@app.post("/api/runs/{slug}/cancel")
def cancel_run(slug: str, request: Request):
    """정지 버튼 (§18).

    스레드를 강제로 죽이지 않는다 — 파일을 반쯤 쓴 상태로 끊기면 산출물이
    깨진다. 다음 단계 경계에서 스스로 멈춘다.
    """
    auth.require_owner(request, store.meta(slug).get("owner"))
    if not orchestrator.cancel(slug):
        raise HTTPException(404, lang.t("err.notRunning"))
    return {"ok": True}


@app.post("/api/route")
def route_work(req: RunReq):
    """이 일을 누구에게 맡길지만 물어본다 (§10). 화면이 미리 보여줄 수 있어야 한다."""
    if not req.requirement.strip():
        raise HTTPException(400, lang.t("err.emptyRequirement"))
    try:
        r = orchestrator.route(req.requirement.strip())
    except Exception as e:                       # noqa: BLE001
        raise HTTPException(502, secrets_broker.scrub(f"{type(e).__name__}: {e}"))
    return r.model_dump()


@app.get("/api/preflight")
def get_preflight(strict: bool = False):
    """출항 전 점검 (DAY 14).

    `strict=true` 는 "지금 배포한다"는 뜻이다 — 경고 몇 개가 실패로
    승격된다. 실제 모델을 부르지는 않는다. 점검이 돈을 쓰면 아무도
    자주 돌리지 않는다.
    """
    return preflight.report(strict)


@app.get("/api/deploy")
def deploy_status():
    """이 서버가 어떤 자세로 도는가 (local / saas, 샌드박스 여부)."""
    return deploy.status()


# ── 크레딧 · 요금제 · 원가 (지시서 §15 §16 §17) ─────────────────────
@app.get("/api/credits")
def get_credits(request: Request):
    """잔액과 요금제. 단가가 검증됐는지도 함께 내려보낸다 —
    검증 안 된 단가로 계산한 잔액은 근거가 아니라 추측이다."""
    return credits.status(auth.owner_of(request))


@app.get("/api/plans")
def get_plans(request: Request):
    """요금제와 **크레딧이 실제로 뭘 사주는지**.

    바깥 제품들에 대해 가장 많이 나오는 불평이 "크레딧이 뭘 사주는지
    모르겠다"이다(docs/market.md). 우리는 호출 단위로 원가를 집계하고
    있으므로, 끝난 프로젝트들의 실제 비용을 함께 보낸다.

    셀 만큼 돌지 않았으면 `measured: false` 로 답한다 — 화면은 그때
    추정값을 쓰고 **추정이라고 말한다.** 여기서 없는 데이터를 그럴듯한
    숫자로 채우면 그게 제일 나쁜 거짓말이다.
    """
    # 이 라우트는 **로그인 전에도** 보인다(랜딩의 요금제). 여기서 세션을
    # 요구하면 처음 온 사람에게 가격이 안 보인다.
    #
    # 로그인한 사람에게는 **자기 프로젝트**로 잰 값을 준다. 로그인하지
    # 않았고 서버 배포라면 재지 않는다 — 남의 사용량을 모아 보여주는
    # 것이라, 값이 아무리 뭉뚱그려져 있어도 우리가 줄 이유가 없다.
    user = auth.current_user(request)
    owner = user.id if user else None
    measurable = owner is not None or not deploy.is_saas()
    return {"plans": credits.plans(), "topups": credits.topups(),
            "credit_usd": config.CREDIT_USD,
            "per_project": (project_index.project_costs(owner) if measurable
                            else project_index.project_costs("__none__"))}


@app.post("/api/credits/plan")
def change_plan(req: PlanReq, request: Request):
    owner = auth.owner_of(request)
    try:
        credits.set_plan(owner, req.plan)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return credits.status(owner)


@app.post("/api/credits/topup")
def topup(req: TopUpReq, request: Request):
    """결제는 이 제품의 범위 밖이다. 여기서는 잔액이 실제로 늘고
    실제로 막히는가만 성립시킨다."""
    owner = auth.owner_of(request)
    try:
        credits.top_up(owner, req.credits)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return credits.status(owner)


# ── 고객 자신의 키 (BYOK · DAY 19) ──────────────────────────────────
@app.get("/api/byok")
def get_byok(request: Request):
    """내 키 현황. **원문은 어떤 경로로도 나가지 않는다** — 마스크만.

    운영자 키(`/api/settings`)와 라우트를 나눈 이유: 한 라우트에서 둘을
    같이 다루면 언젠가 한쪽 코드가 다른 쪽 저장소를 건드린다. 그때 사고는
    "내 키가 남에게 갔다"가 된다.
    """
    owner = auth.owner_of(request)
    return {**byok.status(owner), **tenant.describe(owner)}


@app.post("/api/byok")
def set_byok(req: ByokReq, request: Request):
    owner = auth.owner_of(request)
    for provider in byok.PROVIDERS:
        val = getattr(req, provider)
        if val is None:
            continue                    # 안 보낸 것과 빈 값은 다르다
        byok.set_key(owner, provider, val)
    return {"ok": True, **byok.status(owner), **tenant.describe(owner)}


@app.delete("/api/byok")
def clear_byok(request: Request, provider: str | None = None):
    owner = auth.owner_of(request)
    if provider is not None and provider not in byok.PROVIDERS:
        raise HTTPException(400, lang.t("err.unknownProvider", name=provider))
    byok.clear(owner, provider)
    return {"ok": True, **byok.status(owner), **tenant.describe(owner)}


@app.post("/api/byok/verify/{provider}")
def verify_byok(provider: str, request: Request):
    """내 키로 실제 조회를 한 번 해본다. 등록 직후에 알아야 할 것은
    "저장됐다"가 아니라 **"이 키로 모델이 불리는가"** 다.

    조회는 모델 호출이 아니라 목록 API 라 요금이 (거의) 들지 않는다.
    """
    owner = auth.owner_of(request)
    if provider not in byok.PROVIDERS:
        raise HTTPException(400, lang.t("err.unknownProvider", name=provider))
    if not byok.has(owner, provider):
        raise HTTPException(400, lang.t("err.noKey"))
    # 자세를 강제로 byok 로 세운다 — 요금제를 바꾸기 *전에* 키부터
    # 확인하고 싶은 것이 정상적인 순서다.
    posture = tenant.Posture(owner=owner, plan="byok", source="byok",
                             keys=byok.keys_of(owner))
    try:
        with tenant.bind(owner, posture):
            if provider == "anthropic":
                from app.providers import anthropic_client as llm
                n = len(list(llm.client().models.list()))
            elif provider == "gemini":
                n = len(gemini.list_models())
            else:
                from app.providers import openai_client
                n = len(openai_client.list_models())
        return {"ok": True, "detail": f"모델 {n}개 조회됨"}
    except Exception as e:                                     # noqa: BLE001
        return {"ok": False,
                "detail": secrets_broker.scrub(f"{type(e).__name__}: {e}")}


@app.get("/api/margin")
def margin():
    """§17 원가 관리 — 원가가 판매가의 50% 이하인가를 **실제 숫자로** 검사한다.

    구호가 아니라 계산이다. 요금제가 주는 크레딧을 전부 쓴 경우가
    우리 최대 원가이므로, 그 값과 구독료를 비교한다.
    """
    return credits.margin_report()


# ── MANUAL 모드 (지시서 §11) ────────────────────────────────────────
@app.post("/api/manual")
def open_manual(req: RunReq, request: Request):
    """계획 단계 없이 바로 지시할 수 있는 빈 프로젝트를 연다."""
    if not req.requirement.strip():
        raise HTTPException(400, lang.t("err.emptyRequirement"))
    slug = manual.open_project(req.requirement.strip(),
                               owner=auth.owner_of(request))
    return {"slug": slug, "mode": "manual"}


@app.post("/api/manual/{slug}/instruct")
def manual_instruct(slug: str, req: InstructReq, request: Request):
    """CEO 가 직원을 지목해 직접 지시한다.

    권한 경계는 AUTO 와 **같다**. "CEO 가 시켰다"는 작가가 src/ 에 쓸
    근거가 아니다 — 두 경로가 다른 규칙을 가지면 그 차이가 곧 구멍이 된다.
    """
    if not roles.exists(req.employee):
        raise HTTPException(404, lang.t("err.noEmployee", id=req.employee))
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    if orchestrator.is_running(slug):
        raise HTTPException(409, lang.t("err.autoRunning"))
    try:
        return manual.instruct(slug, req.employee, req.message,
                               owner=auth.owner_of(request))
    except tenant.NoPlan as e:
        raise HTTPException(402, str(e))
    except tenant.KeysMissing as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except manual.Busy as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:          # 예산 상한 등
        raise HTTPException(402, str(e))
    except employees.EmployeeFailed as e:
        raise HTTPException(502, secrets_broker.scrub(str(e)))


@app.post("/api/manual/{slug}/verify")
def manual_verify(slug: str, request: Request):
    """CEO 가 누를 때만 도는 검증. 검증 기준은 AUTO 와 같다."""
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    if orchestrator.is_running(slug):
        raise HTTPException(409, lang.t("err.autoRunning"))
    try:
        return manual.verify(slug, owner=auth.owner_of(request))
    except tenant.NoPlan as e:
        raise HTTPException(402, str(e))
    except tenant.KeysMissing as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except manual.Busy as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        raise HTTPException(402, str(e))
    except employees.EmployeeFailed as e:
        raise HTTPException(502, secrets_broker.scrub(str(e)))


@app.get("/api/manual/{slug}")
def manual_state(slug: str, request: Request):
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    return {
        "slug": slug,
        "busy": manual.busy_employee(slug),
        "employees": employees.status(slug),
        "files": store.files_of(slug),
        "history": {e: [{"role": m.role, "content": m.content}
                        for m in manual.history(slug, e)]
                    for e in roles.ids()},
    }


@app.delete("/api/manual/{slug}/history")
def manual_clear_history(slug: str, request: Request,
                         employee: str | None = None):
    if store.exists(slug):
        auth.require_owner(request, store.meta(slug).get("owner"))
    manual.clear_history(slug, employee)
    return {"ok": True}


# ── 프로젝트 (지시서 §12) ───────────────────────────────────────────
@app.get("/api/projects")
def list_projects(request: Request, status: str | None = None,
                  q: str | None = None, sort: str = "created",
                  desc: bool = True, limit: int = 50, offset: int = 0):
    """색인으로 검색·정렬·페이지. 색인이 깨졌으면 디스크에서 읽는다 (§12).

    응답의 `source` 가 그 사실을 말한다 — 조용히 느려지는 것보다
    왜 느린지 보이는 편이 낫다.
    """
    # owner 를 쿼리로 받지 않는다. 받으면 값을 바꿔 남의 목록을 본다.
    return project_index.search(owner=auth.owner_of(request), status=status,
                                q=q, sort=sort, desc=desc,
                                limit=limit, offset=offset)


@app.get("/api/projects/stats")
def project_stats(request: Request):
    """대시보드 요약 — 프로젝트 수 · 누적 비용 · 평균 완성도 (§12)."""
    return project_index.stats(auth.owner_of(request))


@app.post("/api/projects/reindex")
def reindex():
    """디스크를 훑어 색인을 다시 만든다.

    **파일이 진실**이라는 규칙이 실제로 성립하려면 이 길이 있어야 한다.
    다른 곳에서 복사해 온 projects/ 폴더를 붙였을 때도 쓴다.
    """
    return {"indexed": project_index.rebuild()}


@app.get("/api/projects/{slug}/files")
def project_files(slug: str, request: Request):
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    return {"files": store.files_of(slug)}


@app.get("/api/projects/{slug}/file")
def project_file(slug: str, path: str, request: Request):
    # 목록만 거르고 파일 접근을 빼먹으면, "목록에는 안 보이는데 주소를
    # 알면 열리는" 상태가 된다. 막은 것처럼 보여서 더 위험하다.
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    try:
        return {"path": path, "content": store.read_file(slug, path),
                "versions": store.versions(slug, path)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/projects/{slug}/diff")
def project_diff(slug: str, path: str, a: int, request: Request, b: int = 0):
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    try:
        return {"path": path, "a": a, "b": b, "diff": store.diff(slug, path, a, b)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/projects/{slug}")
def delete_project(slug: str, request: Request):
    if store.exists(slug):
        auth.require_owner(request, store.meta(slug).get("owner"))
    if orchestrator.is_running(slug):
        raise HTTPException(409, lang.t("err.runningDelete"))
    if not store.delete_project(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    return {"ok": True}


# ── AI 직원 (지시서 §8) ─────────────────────────────────────────────
@app.get("/api/employees")
def list_employees(request: Request, run: str | None = None):
    """직원 5명의 정의 · 권한 · 현재 모델 · Mock 여부 · 사용량 · 인사."""
    owner = auth.owner_of(request)
    with tenant.bind(owner):
        return {"employees": employees.status(_my_run(request, run)),
                "assignable": roles.assignable(),
                "planner": roles.PLANNER, "verifier": roles.VERIFIER}


@app.patch("/api/employees/{employee_id}")
def update_employee(employee_id: str, req: StaffReq, request: Request):
    """이름을 바꾸거나, 채용하거나, 내보낸다 (DAY 21 · agents/staff.py).

    권한은 바꿀 수 없다. 이름은 고객의 것이지만 **자리의 권한은 제품의
    것**이다 — 개발자를 '수석 아키텍트'라고 불러도 src/ 밖에는 못 쓴다.
    """
    if not roles.exists(employee_id):
        raise HTTPException(404, lang.t("err.noEmployee", id=employee_id))
    owner = auth.owner_of(request)
    try:
        if req.name is not None:
            staff.rename(owner, employee_id, req.name)
        if req.active is not None:
            staff.set_active(owner, employee_id, req.active)
    except ValueError as e:
        # 400 이 아니라 409 다. 형식이 틀린 것이 아니라 **지금 상태에서
        # 할 수 없는 일**이다 — 교차검증을 맡은 자리는 비울 수 없다.
        raise HTTPException(409, str(e))
    with tenant.bind(owner):
        return {"ok": True, "employees": employees.status(_my_run(request, None)),
                "assignable": roles.assignable()}


@app.get("/api/employees/{employee_id}")
def get_employee(employee_id: str):
    if not roles.exists(employee_id):
        raise HTTPException(404, lang.t("err.noEmployee", id=employee_id))
    e = roles.get(employee_id)
    row = e.info()
    row["mock"] = employees.is_mock(e)
    row["system"] = e.system        # 무엇을 시켰는지 CEO 가 볼 수 있어야 한다
    row["worst_case_usd"] = round(employees.worst_case_cost(employee_id), 4)
    return row


@app.post("/api/employees/{employee_id}/model")
def set_employee_model(employee_id: str, req: ModelReq2):
    """직원 한 명의 모델만 바꾼다 (§7).

    단가를 모르는 모델은 거부한다 — 비용이 0 으로 잡히면 예산 상한(§18)이
    그 직원에게는 걸리지 않는다.
    """
    if not roles.exists(employee_id):
        raise HTTPException(404, lang.t("err.noEmployee", id=employee_id))
    if req.model not in config.PRICES:
        raise HTTPException(400, lang.t("err.modelNotPriced", model=req.model))
    roles.set_model(employee_id, req.model)
    return {"ok": True, "employee": roles.get(employee_id).info()}


# ── 첨부 자료 ───────────────────────────────────────────────────────
@app.get("/api/attachments")
def list_attachments():
    return {"attachments": attachments.listing()}


@app.post("/api/attachments")
async def upload_attachment(file: UploadFile = File(...)):
    data = await file.read()
    try:
        return attachments.save(file.filename or "upload.bin", data, source="upload")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/attachments/{aid}/preview")
def attachment_preview(aid: str):
    url = attachments.data_url(aid)
    if not url:
        raise HTTPException(404, lang.t("err.noPreview"))
    return {"id": aid, "data_url": url}


@app.delete("/api/attachments/{aid}")
def delete_attachment(aid: str):
    if not attachments.delete(aid):
        raise HTTPException(404, lang.t("err.noAttachment"))
    return {"ok": True}


# ── 이벤트 스트림 ───────────────────────────────────────────────────
@app.get("/api/stream")
def stream(request: Request, run: str | None = None, after: int = 0):
    """실시간 작업 로그 (§13).

    `run` 을 주면 그 프로젝트의 이벤트만 온다. 안 주면 전부 — 여러
    프로젝트를 한 화면에서 보는 대시보드(§12)가 그렇게 쓴다.

    SSE 는 끊긴다. 프록시가 끊고, 노트북이 잠들고, 탭이 백그라운드로 간다.
    브라우저가 재연결하면서 보내는 `Last-Event-ID` 를 받아 그 뒤부터만
    보낸다. 안 그러면 끊긴 동안의 작업 로그를 사용자가 영영 못 본다.
    """
    last = request.headers.get("last-event-id")
    try:
        after = max(after, int(last)) if last else after
    except ValueError:
        pass

    def gen_memory():
        """대시보드(§12)용. 이 인스턴스가 본 이벤트만 안다 — 아직 여러
        인스턴스를 못 넘는다(`run=None` 은 id 가 프로세스마다 따로 세여서
        파일들을 그냥 합칠 수 없다)."""
        sub = bus.subscribe(run, after)
        try:
            yield ": connected\n\n"
            yield "retry: 5000\n\n"
            while True:
                try:
                    ev = sub.q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield (f"id: {ev['id']}\n"
                       f"event: {ev['type']}\n"
                       f"data: {json.dumps(ev, ensure_ascii=False)}\n\n")
        finally:
            bus.unsubscribe(sub)

    def gen_file(run_id: str):
        """프로젝트 하나(§12 상세)용. 트레이스 파일을 따라간다 — 실행을
        맡은 인스턴스가 어디든, 보는 인스턴스가 어디든 같은 로그가 나온다
        (DAY 23). 대가는 폴링 지연(`BUS_FILE_POLL_INTERVAL`, 기본 0.3초)뿐."""
        yield ": connected\n\n"
        yield "retry: 5000\n\n"
        last_sent = time.time()
        for ev in bus.tail_trace(run_id, after):
            if ev is None:
                if time.time() - last_sent >= 15:
                    yield ": keepalive\n\n"
                    last_sent = time.time()
                continue
            last_sent = time.time()
            yield (f"id: {ev['id']}\n"
                   f"event: {ev['type']}\n"
                   f"data: {json.dumps(ev, ensure_ascii=False)}\n\n")

    gen = gen_file(run) if run else gen_memory()
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/events")
def events(run: str | None = None, after: int = 0):
    """SSE 를 못 쓰는 상황(테스트·프록시·폴링)에서의 같은 이력.

    SSE 하나에만 기대면, 그 경로가 막힌 환경에서 화면이 통째로 빈다.

    `run` 이 있으면 트레이스 파일에서 읽는다 — 실행을 맡은 인스턴스와
    이 요청을 받은 인스턴스가 다를 수 있어서다(DAY 23). 없으면(대시보드)
    이 인스턴스의 메모리만 본다.
    """
    rows = bus.read_trace(run, after) if run else bus.replay(run, after)
    return {"events": rows, "last_id": rows[-1]["id"] if rows else after,
            "roster": bus.roster()}


@app.post("/api/projects/{slug}/narrate")
def narrate_project(slug: str, request: Request, force: bool = False):
    """작업 로그를 평범한 말로 설명한다 (DAY 23 · app/narrator.py).

    검증(§11)과 같은 규칙으로 **CEO 가 누를 때만** 돈다 — 돈이 드는
    호출을 자동으로 돌리면 아무도 안 보는 요약에 비용이 계속 나간다.
    """
    if not store.exists(slug):
        raise HTTPException(404, lang.t("err.noProject"))
    auth.require_owner(request, store.meta(slug).get("owner"))
    try:
        return narrator.narrate(slug, owner=auth.owner_of(request), force=force)
    except tenant.NoPlan as e:
        raise HTTPException(402, str(e))
    except tenant.KeysMissing as e:
        raise HTTPException(409, str(e))
    except narrator.NoProgress as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:          # 예산 상한 등
        raise HTTPException(402, str(e))
    except employees.EmployeeFailed as e:
        raise HTTPException(502, secrets_broker.scrub(str(e)))


if __name__ == "__main__":
    if "--dir" in sys.argv:
        try:
            workspace.use(sys.argv[sys.argv.index("--dir") + 1])
            bus.bind("main")
            usage.bind("main")
        except (IndexError, workspace.Denied, OSError) as e:
            print(f"  폴더를 열지 못했습니다: {e}")
    cur = workspace.current()
    print("\n  http://127.0.0.1:8000")
    print(f"  작업 폴더: {cur or '(설정에서 열기)'}\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
