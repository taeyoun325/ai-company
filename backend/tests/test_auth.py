"""인증과 테넌트 분리 (DAY 15).

## 이 파일이 지키려는 것

1. **`owner` 는 서버가 정한다.** 쿼리 파라미터로 바꿀 수 없다. DAY 14까지
   `?owner=` 하나로 남의 지갑이 열렸다.
2. **목록만 거르는 것으로는 부족하다.** 주소를 알면 열리는 자원이 하나라도
   있으면 테넌트 분리는 없는 것이다. 그래서 파일·diff·삭제·MANUAL·정지까지
   전부 확인한다.
3. **로그인 실패의 이유를 알려주지 않는다.** "없는 이메일"과 "틀린 비밀번호"를
   구분해 답하면 그 차이가 곧 가입자 명단 조회 도구가 된다.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from fastapi.testclient import TestClient                       # noqa: E402

from app import config, main                                    # noqa: E402
from app.auth import deps, passwords, service, store             # noqa: E402
from app.database import index                                   # noqa: E402
from app.providers import registry                               # noqa: E402
from app.usage import credits                                    # noqa: E402

PW = "정말로긴비밀번호2026"
PW2 = "또다른긴비밀번호2026"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """계정·색인·프로젝트를 전부 임시 폴더로. saas 모드로 고정한다 —
    local 모드는 로그인 없이 통과하므로 분리를 확인할 수 없다."""
    monkeypatch.setenv("DEPLOY_MODE", "saas")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(credits, "WALLET_FILE", tmp_path / "credits.json")
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


def _client() -> TestClient:
    return TestClient(main.app)


def _signed_up(email: str, password: str = PW) -> TestClient:
    """가입하고 세션 쿠키를 들고 있는 클라이언트."""
    c = _client()
    r = c.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


# ── 비밀번호 해시 ──────────────────────────────────────────────────
def test_hash_is_salted():
    """같은 비밀번호를 쓰는 두 사람의 해시가 같으면, 하나가 풀릴 때
    둘 다 풀린다."""
    assert passwords.hash_password(PW) != passwords.hash_password(PW)


def test_verify_round_trip():
    h = passwords.hash_password(PW)
    assert passwords.verify(PW, h)
    assert not passwords.verify(PW + "x", h)


def test_verify_never_raises_on_broken_hash():
    """예외의 유무가 곧 '이 계정은 뭔가 다르다'는 신호가 된다."""
    for junk in ("", "말도안되는값", "scrypt$없는숫자$8$1$aa$bb", "bcrypt$x$y"):
        assert passwords.verify(PW, junk) is False


def test_needs_rehash_detects_weaker_parameters():
    """비용을 올리는 날 기존 사용자가 전부 로그인 실패하면 안 된다."""
    weak = passwords.hash_password(PW, n=2 ** 14)
    assert passwords.needs_rehash(weak)
    assert not passwords.needs_rehash(passwords.hash_password(PW))
    assert passwords.verify(PW, weak), "낡은 해시도 검증은 돼야 한다"


def test_password_rules_report_every_problem_at_once():
    """하나씩 알려주면 사용자가 하나씩 고치며 여러 번 거절당한다."""
    issues = passwords.problems("  short  ", email="short@example.com")
    assert len(issues) >= 2


def test_password_cannot_contain_the_email():
    assert passwords.problems("taeyoun입니다길게길게", "taeyoun@example.com")


# ── 가입 · 로그인 ──────────────────────────────────────────────────
def test_signup_then_me(client_email="a@example.com"):
    c = _signed_up(client_email)
    body = c.get("/api/auth/me").json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == client_email


def test_signup_rejects_duplicate_email():
    _signed_up("a@example.com")
    r = _client().post("/api/auth/signup",
                       json={"email": "A@Example.com", "password": PW})
    assert r.status_code == 400, "대소문자만 바꾸면 중복 가입이 된다"


def test_email_is_normalised():
    _signed_up("Taeyoun@Example.COM")
    r = _client().post("/api/auth/login",
                       json={"email": "taeyoun@example.com", "password": PW})
    assert r.status_code == 200, "가입과 로그인의 대소문자가 다르면 못 들어간다"


def test_signup_rejects_weak_password():
    r = _client().post("/api/auth/signup",
                       json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 400


def test_signup_rejects_bad_email():
    r = _client().post("/api/auth/signup",
                       json={"email": "이메일아님", "password": PW})
    assert r.status_code == 400


def test_login_failure_message_does_not_reveal_whether_the_account_exists():
    """이 둘이 다르면, 이메일 목록을 넣어보며 가입자를 알아낼 수 있다."""
    _signed_up("a@example.com")
    wrong_pw = _client().post("/api/auth/login",
                              json={"email": "a@example.com", "password": PW2})
    no_such = _client().post("/api/auth/login",
                             json={"email": "없는@example.com", "password": PW})
    assert wrong_pw.status_code == no_such.status_code == 401
    assert wrong_pw.json()["detail"] == no_such.json()["detail"]


def test_login_takes_similar_time_for_missing_accounts():
    """없는 계정에 해싱을 건너뛰면 응답이 빨라져서 시간만으로 구분된다."""
    _signed_up("a@example.com")
    c = _client()

    def timed(email):
        service.reset_rate_limits()
        t = time.perf_counter()
        c.post("/api/auth/login", json={"email": email, "password": PW2})
        return time.perf_counter() - t

    existing = min(timed("a@example.com") for _ in range(3))
    missing = min(timed("없는@example.com") for _ in range(3))
    assert missing > existing * 0.5, (
        f"없는 계정이 너무 빠르다 (있음 {existing*1000:.0f}ms / "
        f"없음 {missing*1000:.0f}ms)")


def test_repeated_failures_are_rate_limited():
    """비밀번호는 결국 추측당한다. 막는 방법은 속도를 떨어뜨리는 것뿐이다."""
    _signed_up("a@example.com")
    c = _client()
    codes = [c.post("/api/auth/login",
                    json={"email": "a@example.com", "password": PW2}).status_code
             for _ in range(service.MAX_ATTEMPTS + 2)]
    assert 429 in codes, "무한히 시도할 수 있다"


def test_successful_login_clears_the_failure_count():
    _signed_up("a@example.com")
    c = _client()
    for _ in range(3):
        c.post("/api/auth/login", json={"email": "a@example.com", "password": PW2})
    assert c.post("/api/auth/login",
                  json={"email": "a@example.com", "password": PW}).status_code == 200


# ── 세션 ───────────────────────────────────────────────────────────
def test_session_token_is_not_returned_in_the_body():
    """본문에 담으면 프론트엔드가 자바스크립트가 읽을 수 있는 곳에 저장한다."""
    c = _client()
    r = c.post("/api/auth/signup", json={"email": "a@example.com", "password": PW})
    assert "token" not in r.text and "session" not in r.json()


def test_session_cookie_is_httponly():
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@example.com", "password": PW})
    raw = c.cookies.jar._cookies  # noqa: SLF001
    assert deps.COOKIE in c.cookies, "세션 쿠키가 없다"
    assert raw, "쿠키가 저장되지 않았다"


def test_stored_session_token_is_hashed():
    """DB 가 새면 저장된 토큰이 곧 남의 로그인 상태다."""
    user = service.sign_up("a@example.com", PW)
    token = store.new_session(user.id)
    with store.conn() as c:
        rows = [r["token_hash"] for r in c.execute("SELECT token_hash FROM sessions")]
    assert token not in rows


def test_logout_invalidates_the_session():
    c = _signed_up("a@example.com")
    assert c.get("/api/auth/me").json()["authenticated"] is True
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").json()["authenticated"] is False


def test_expired_session_is_rejected():
    user = service.sign_up("a@example.com", PW)
    token = store.new_session(user.id, ttl=-1)
    assert store.session_user(token) is None


def test_changing_password_signs_out_every_browser():
    """훔쳐간 쪽이 계속 들어와 있으면 비밀번호를 바꾼 의미가 없다."""
    a = _signed_up("a@example.com")
    b = _client()
    b.post("/api/auth/login", json={"email": "a@example.com", "password": PW})
    assert b.get("/api/auth/me").json()["authenticated"] is True

    a.post("/api/auth/password", json={"current": PW, "new": PW2})
    assert b.get("/api/auth/me").json()["authenticated"] is False


def test_disabled_account_cannot_use_an_existing_session():
    """계정을 막았는데 이미 로그인한 브라우저가 계속 돌면 막은 의미가 없다."""
    user = service.sign_up("a@example.com", PW)
    token = store.new_session(user.id)
    with store.conn() as c:
        c.execute("UPDATE users SET disabled = 1 WHERE id = ?", (user.id,))
    assert store.session_user(token) is None


# ── 로그인 없이는 아무것도 ─────────────────────────────────────────
@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/state", None),
    ("get", "/api/projects", None),
    ("get", "/api/projects/stats", None),
    ("get", "/api/runs", None),
    ("get", "/api/credits", None),
    ("post", "/api/runs", {"requirement": "아무거나"}),
    ("post", "/api/manual", {"requirement": "아무거나"}),
    ("post", "/api/credits/topup", {"credits": 100}),
    ("post", "/api/credits/plan", {"plan": "pro"}),
])
def test_saas_requires_login(method, path, body):
    r = getattr(_client(), method)(path, **({"json": body} if body else {}))
    assert r.status_code == 401, f"{path} 가 로그인 없이 열려 있다"


def test_public_endpoints_stay_public():
    """로그인 화면을 그리려면 이것들은 로그인 전에도 보여야 한다."""
    c = _client()
    for path in ("/api/auth/me", "/api/deploy", "/api/plans"):
        assert c.get(path).status_code == 200, path


# ── 테넌트 분리 ────────────────────────────────────────────────────
@pytest.fixture
def two_users():
    a = _signed_up("a@example.com")
    b = _signed_up("b@example.com")
    slug = a.post("/api/manual", json={"requirement": "A 의 비밀 프로젝트"}).json()["slug"]
    return a, b, slug


def test_owner_cannot_be_forged_by_query_parameter(two_users):
    """DAY 14까지 `?owner=` 하나로 남의 지갑이 열렸다."""
    _a, b, _slug = two_users
    body = b.get("/api/projects", params={"owner": "a@example.com"}).json()
    assert body["total"] == 0, "쿼리 파라미터로 남의 목록을 봤다"


def test_credits_are_per_user(two_users):
    a, b, _ = two_users
    a.post("/api/credits/topup", json={"credits": 500})
    assert b.get("/api/credits").json()["balance"] < \
        a.get("/api/credits").json()["balance"], "지갑이 공유되고 있다"


def test_project_list_is_scoped(two_users):
    a, b, _ = two_users
    assert a.get("/api/projects").json()["total"] == 1
    assert b.get("/api/projects").json()["total"] == 0


def test_project_stats_are_scoped(two_users):
    _a, b, _ = two_users
    assert b.get("/api/projects/stats").json()["projects"] == 0


@pytest.mark.parametrize("method,path,params,body", [
    ("get", "/api/runs/{slug}", None, None),
    ("get", "/api/projects/{slug}/files", None, None),
    ("get", "/api/projects/{slug}/file", {"path": "src/calc.py"}, None),
    ("get", "/api/projects/{slug}/diff", {"path": "src/calc.py", "a": 1}, None),
    ("get", "/api/manual/{slug}", None, None),
    ("post", "/api/runs/{slug}/cancel", None, None),
    ("post", "/api/manual/{slug}/verify", None, None),
    ("delete", "/api/projects/{slug}", None, None),
])
def test_other_users_project_is_not_reachable_by_url(two_users, method, path,
                                                     params, body):
    """목록만 거르고 주소로 열리는 것을 빼먹으면, 막은 것처럼 보여서 더 위험하다."""
    _a, b, slug = two_users
    kw = {}
    if params:
        kw["params"] = params
    if body:
        kw["json"] = body
    r = getattr(b, method)(path.format(slug=slug), **kw)
    assert r.status_code == 404, f"{path} 로 남의 프로젝트에 닿았다 ({r.status_code})"


def test_other_users_manual_instruction_is_rejected(two_users):
    _a, b, slug = two_users
    r = b.post(f"/api/manual/{slug}/instruct",
               json={"employee": "developer", "message": "지워줘"})
    assert r.status_code == 404


def test_owner_still_reaches_their_own_project(two_users):
    """막느라 자기 것까지 막으면 그건 고장이다."""
    a, _b, slug = two_users
    assert a.get(f"/api/manual/{slug}").status_code == 200
    assert a.get(f"/api/runs/{slug}").status_code == 200


def test_running_list_hides_other_users_slugs(two_users):
    """진행 중 목록에 남의 slug 가 보이면 그 자체로 존재를 알려주는 것이다."""
    _a, b, slug = two_users
    assert slug not in b.get("/api/runs").json()["running"]


def test_usage_of_another_users_run_is_not_exposed(two_users):
    """`run=` 파라미터를 검사하지 않으면 남의 프로젝트 사용량이 샌다.
    소유권 검사를 목록에만 걸고 부수적인 파라미터에 빼먹는 것이
    테넌트 분리가 뚫리는 가장 흔한 방식이다."""
    a, b, slug = two_users
    a.post(f"/api/manual/{slug}/instruct",
           json={"employee": "developer", "message": "사칙연산을 구현해주세요"})
    rows = b.get("/api/employees", params={"run": slug}).json()["employees"]
    assert all(not r["usage"].get("calls") for r in rows), "남의 사용량이 보인다"


def test_deleting_someone_elses_project_does_not_delete_it(two_users):
    a, b, slug = two_users
    b.delete(f"/api/projects/{slug}")
    assert a.get(f"/api/manual/{slug}").status_code == 200, "남이 지웠다"


# ── 로컬 모드 ──────────────────────────────────────────────────────
def test_local_mode_does_not_require_login(monkeypatch):
    """개발자가 매번 계정을 만들어야 하면 아무도 안 지키는 규칙이 된다."""
    monkeypatch.setenv("DEPLOY_MODE", "local")
    c = _client()
    assert c.get("/api/state").status_code == 200
    assert c.get("/api/auth/me").json()["required"] is False


def test_local_owner_is_stable(monkeypatch):
    monkeypatch.setenv("DEPLOY_MODE", "local")
    assert _client().get("/api/state").json()["user"]["id"] == deps.LOCAL_OWNER
