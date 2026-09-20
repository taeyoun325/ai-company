"""인증과 테넌트 분리 (DAY 15).

    passwords.py   scrypt 해시. 파라미터를 해시에 같이 적어 나중에 올릴 수 있다
    store.py       계정 · 로그인 수단 · 세션. **색인 DB 와 파일을 나눈다**
    service.py     가입 · 로그인 · 횟수 제한. 실패 이유를 알려주지 않는다
    deps.py        요청 → 사용자. `owner` 는 **서버가 정한다**

구글 로그인은 `store.identities` 에 한 줄(`provider='google'`)을 더하는
일이 되도록 설계했다 — users 테이블도, 세션도, 라우트 관문도 바뀌지 않는다.
"""
from app.auth.deps import (COOKIE, LOCAL_OWNER, clear_session_cookie,  # noqa: F401
                           current_user, owner_of, owns, require_owner,
                           require_user, set_session_cookie)
from app.auth.service import AuthError, RateLimited  # noqa: F401
