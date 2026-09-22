"""요청 → 사용자 (DAY 15). 테넌트 분리는 여기서 시작한다.

## 한 가지 규칙, 그게 전부다

**`owner` 는 서버가 정한다. 클라이언트가 보낸 값을 절대 쓰지 않는다.**

DAY 14까지 이 코드는 `owner` 를 쿼리 파라미터로 받았다:

    GET /api/credits?owner=local

값을 바꿔 보내면 그대로 남의 지갑이 열린다. 인증이 없어서 막을 근거가
없었다. 이제 `owner` 는 세션 쿠키에서만 나온다. 라우트가 `owner` 를
받는 길을 **아예 없앤다** — 남겨두면 언젠가 누군가 그 길로 들어온다.

## 로컬 모드에서는 로그인을 요구하지 않는다

`DEPLOY_MODE=local` 은 "내 컴퓨터에서 내가 쓴다"이다(§DAY 13). 거기서
로그인을 강제하면 개발자가 매번 계정을 만들어야 하고, 그건 아무도
지키지 않는 규칙이 된다. 대신 `local` 이라는 고정 사용자로 동작한다.

`saas` 에서는 예외가 없다. 로그인하지 않으면 401 이다.

## 왜 쿠키인가

토큰을 자바스크립트가 읽을 수 있는 곳(localStorage)에 두면, XSS 한 번에
세션이 통째로 털린다. `httponly` 쿠키는 스크립트가 읽지 못한다.
대신 CSRF 를 신경 써야 하므로 `samesite=lax` 를 건다 — 다른 사이트에서
넘어온 POST 에는 쿠키가 붙지 않는다.
"""
from __future__ import annotations

from fastapi import HTTPException, Request, Response

from app import deploy, lang
from app.auth import service, store

COOKIE = "ai_company_session"

# 로컬 모드에서 쓰는 고정 사용자. 실제 계정이 아니다.
LOCAL_OWNER = "local"
LOCAL_USER = store.User(id=LOCAL_OWNER, email="local@localhost",
                        display_name=lang.t("who.localUser"), created_at=0.0)


def is_https(request: Request | None) -> bool:
    """이 요청이 실제로 암호화된 연결로 왔는가.

    `Secure` 쿠키는 https 로만 전송된다. 그래서 이 판단이 틀리면 둘 중
    하나가 일어난다:

      - http 인데 Secure 를 걸면 → **브라우저가 쿠키를 안 보낸다.**
        로그인이 성공했는데 계속 로그아웃 상태로 보인다
      - https 인데 안 걸면 → 실수로 http 로 새는 요청에 세션이 평문으로 간다

    배포 모드(`DEPLOY_MODE`)로 판단하면 안 되는 이유가 여기 있다. TLS 를
    앞단 프록시가 끊으면 앱이 보는 스킴은 http 다 — saas 인데 http 인 것이
    정상인 배치가 있다. 그래서 요청에서 본다.

    `x-forwarded-proto` 는 프록시가 없으면 공격자가 마음대로 적는 값이므로,
    앞에 프록시가 있다는 전제인 saas 에서만 믿는다(§DAY 13 과 같은 규칙).
    """
    if request is None:
        return deploy.is_saas()
    if request.url.scheme == "https":
        return True
    if deploy.is_saas():
        proto = request.headers.get("x-forwarded-proto", "")
        return proto.split(",")[0].strip().lower() == "https"
    return False


def set_session_cookie(response: Response, token: str,
                       request: Request | None = None,
                       max_age: int = store.SESSION_TTL) -> None:
    response.set_cookie(
        COOKIE, token,
        max_age=max_age,
        httponly=True,               # 스크립트가 못 읽는다
        samesite="lax",              # 다른 사이트發 POST 에는 안 붙는다
        secure=is_https(request),
        path="/",
    )


def clear_session_cookie(response: Response,
                         request: Request | None = None) -> None:
    # 지울 때도 같은 속성을 줘야 브라우저가 같은 쿠키로 인식한다.
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax",
                           secure=is_https(request))


def token_of(request: Request) -> str:
    return request.cookies.get(COOKIE, "")


def current_user(request: Request) -> store.User | None:
    """로그인한 사용자. 없으면 None.

    로컬 모드에서는 로그인 없이도 고정 사용자를 돌려준다.
    """
    user = service.me(token_of(request))
    if user is not None:
        return user
    return None if deploy.is_saas() else LOCAL_USER


def require_user(request: Request) -> store.User:
    """로그인 필수인 라우트가 쓴다. 401 은 화면이 로그인으로 보내는 신호다."""
    user = current_user(request)
    if user is None:
        raise HTTPException(401, lang.t("err.loginRequired"))
    return user


def owner_of(request: Request) -> str:
    """이 요청이 **누구 것**인가.

    모든 데이터 접근이 이 한 줄을 지나야 한다. 쿼리 파라미터·본문·헤더에서
    owner 를 읽는 코드가 하나라도 남아 있으면 테넌트 분리는 없는 것이다.
    """
    return require_user(request).id


def owns(request: Request, record_owner: str | None) -> bool:
    """이 요청자가 그 자원의 주인인가."""
    return (record_owner or LOCAL_OWNER) == owner_of(request)


def require_owner(request: Request, record_owner: str | None) -> None:
    """남의 자원이면 **404** 로 답한다.

    403("권한 없음")으로 답하면 "그 자원은 존재한다"를 알려주는 셈이다.
    목록에 안 보이는 프로젝트의 존재 여부를 주소만으로 확인할 수 있게 된다.
    없는 것과 남의 것을 같은 말로 답한다.
    """
    if not owns(request, record_owner):
        raise HTTPException(404, lang.t("err.noProject"))
