"""인증 라우트 (DAY 15).

main.py 가 800줄을 넘어서 여기로 뺐다 — `app/api/__init__.py` 에
"라우트가 늘어나면 쪼갠다"고 적어둔 그 지점이다.

## 응답에 무엇을 담지 않는가

세션 토큰을 **본문에 담지 않는다.** 쿠키로만 나간다. 본문에 담으면
프론트엔드가 그걸 어딘가에 저장하고 싶어지고, 저장할 수 있는 곳은
자바스크립트가 읽을 수 있는 곳뿐이다.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import deploy
from app.auth import deps, service, store

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignUpReq(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LogInReq(BaseModel):
    email: str
    password: str


class ChangePasswordReq(BaseModel):
    current: str
    new: str


def _client_ip(request: Request) -> str:
    """역프록시 뒤에서는 X-Forwarded-For 가 실제 주소다.

    다만 **프록시가 없으면 이 헤더는 공격자가 마음대로 적는 값**이다.
    그래서 saas 에서만 신뢰한다 — 그때는 앞에 프록시가 있다는 전제이고,
    없다면 그건 배포 설정이 잘못된 것이다.
    """
    if deploy.is_saas():
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/me")
def me(request: Request):
    """지금 누구로 로그인해 있나. 화면이 제일 먼저 부르는 것."""
    user = deps.current_user(request)
    return {
        "user": user.public() if user else None,
        "authenticated": user is not None,
        # 로컬 모드에서는 로그인 없이도 동작한다는 사실을 화면이 알아야
        # "로그인하세요"를 띄울지 말지 정할 수 있다.
        "required": deploy.is_saas(),
        "first_user": service.is_first_user(),
        "identities": store.identities_of(user.id) if user else [],
    }


@router.post("/signup")
def sign_up(req: SignUpReq, request: Request, response: Response):
    try:
        user = service.sign_up(req.email, req.password, req.display_name)
    except service.AuthError as e:
        raise HTTPException(400, str(e))
    # 가입하면 바로 로그인 상태로 만든다. 방금 만든 비밀번호를 다시
    # 입력하게 하는 것은 사용자에게 아무 도움이 안 된다.
    _, token = service.log_in(req.email, req.password,
                              ip=_client_ip(request),
                              user_agent=request.headers.get("user-agent", ""))
    deps.set_session_cookie(response, token, request)
    return {"user": user.public(), "authenticated": True}


@router.post("/login")
def log_in(req: LogInReq, request: Request, response: Response):
    try:
        user, token = service.log_in(
            req.email, req.password, ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""))
    except service.RateLimited as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.retry_after)})
    except service.AuthError as e:
        # 401 이지만 이유는 항상 같은 문장이다. 구분해서 답하면 그 차이가
        # 곧 가입자 명단 조회 도구가 된다.
        raise HTTPException(401, str(e))
    deps.set_session_cookie(response, token, request)
    return {"user": user.public(), "authenticated": True}


@router.post("/logout")
def log_out(request: Request, response: Response):
    service.log_out(deps.token_of(request))
    deps.clear_session_cookie(response, request)
    return {"ok": True}


@router.post("/password")
def change_password(req: ChangePasswordReq, request: Request, response: Response):
    user = deps.require_user(request)
    if user.id == deps.LOCAL_OWNER:
        raise HTTPException(400, "로컬 사용자는 비밀번호가 없습니다.")
    try:
        service.change_password(user.id, req.current, req.new)
    except service.AuthError as e:
        raise HTTPException(400, str(e))
    # 모든 세션을 끊었으므로 이 브라우저도 로그아웃된다. 쿠키를 지워서
    # 화면이 "로그인 상태인데 401" 인 이상한 상태에 빠지지 않게 한다.
    deps.clear_session_cookie(response, request)
    return {"ok": True, "signed_out": True}


@router.post("/sessions/revoke")
def revoke_sessions(request: Request, response: Response):
    """다른 기기에서 전부 로그아웃. 비밀번호가 샜을 것 같을 때."""
    user = deps.require_user(request)
    n = store.drop_all_sessions(user.id)
    deps.clear_session_cookie(response, request)
    return {"ok": True, "revoked": n}


# ── 비밀번호 재설정 · 이메일 확인 (DAY 22) ──────────────────────────
class ForgotReq(BaseModel):
    email: str


class ResetReq(BaseModel):
    token: str
    password: str


class TokenReq(BaseModel):
    token: str


@router.post("/forgot")
def forgot(req: ForgotReq, request: Request):
    """재설정 메일을 보낸다.

    **계정이 있든 없든 같은 답을 준다.** "그런 계정 없습니다"는 친절해
    보이지만, 아무나 주소를 넣어보며 가입 여부를 확인할 수 있다는 뜻이다.
    가입 여부는 그 자체로 사생활이다.

    메일이 실제로 나갔는지는 숨기지 않는다 — `delivered` 가 false 면
    운영자가 SMTP 를 아직 붙이지 않은 것이고, 화면이 그 사실을 말해야
    사용자가 **오지 않는 메일을 기다리지 않는다.**
    """
    try:
        d = service.request_reset(req.email, ip=_client_ip(request))
    except service.RateLimited as e:
        raise HTTPException(429, str(e))
    except service.AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "delivered": d.delivered, "how": d.how,
            "detail": d.detail}


@router.post("/reset")
def reset(req: ResetReq, response: Response, request: Request):
    """새 비밀번호를 정한다. 토큰은 한 번만 쓴다.

    성공하면 **기존 세션이 전부 끊긴다** — 비밀번호를 되찾는 이유는 대개
    누가 들어와 있기 때문이다. 그 다음 이 요청을 보낸 브라우저에만 새
    세션을 준다. 바로 로그인시키는 이유는, 안 그러면 방금 정한 비밀번호를
    한 번 더 입력하게 되기 때문이다.
    """
    try:
        user = service.reset_password(req.token, req.password)
    except service.AuthError as e:
        raise HTTPException(400, str(e))
    token = store.new_session(
        user.id, user_agent=request.headers.get("user-agent", ""))
    deps.set_session_cookie(response, token, request)
    return {"ok": True, "user": user.public()}


@router.post("/verify/send")
def send_verification(request: Request):
    user = deps.current_user(request)
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    d = service.request_verification(user.id)
    return {"ok": True, "delivered": d.delivered, "how": d.how,
            "detail": d.detail}


@router.post("/verify")
def verify(req: TokenReq):
    try:
        user = service.verify_email(req.token)
    except service.AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "user": user.public()}
