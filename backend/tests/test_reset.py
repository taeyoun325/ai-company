"""비밀번호 재설정과 이메일 확인 (DAY 22 · auth/mail.py · auth/service.py).

## 이 파일이 지키려는 것

1. **계정이 있는지 알려주지 않는다.** "그런 계정 없습니다"는 친절해
   보이지만, 아무나 주소를 넣어보며 가입 여부를 확인할 수 있다는 뜻이다.
   가입 여부는 그 자체로 사생활이다 — 어느 서비스를 쓰는지가 드러난다.
2. **토큰은 한 번만 쓴다.** 메일은 남고, 메일함은 털린다.
3. **재설정하면 기존 세션이 전부 끊긴다.** 비밀번호를 되찾는 이유는 대개
   누가 들어와 있기 때문이다. 안 끊으면 되찾은 의미가 없다.
4. **메일이 안 나갔으면 안 나갔다고 한다.** 여기서 "보냈다"고 답하면
   운영자는 설정을 빠뜨린 채 배포하고, 사용자는 오지 않는 메일을
   영원히 기다린다.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/

from app.auth import mail, service, store                      # noqa: E402

EMAIL = "kim@example.com"
PASSWORD = "Qx7-vault-river-92"
NEW_PASSWORD = "Zt4-harbor-lantern-58"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("SMTP_URL", raising=False)
    store.close()
    service.reset_rate_limits()
    yield
    store.close()


@pytest.fixture
def user():
    return service.sign_up(EMAIL, PASSWORD)


# ── 계정 존재를 흘리지 않는다 ──────────────────────────────────────
def test_unknown_email_looks_the_same_as_a_known_one(user):
    known = service.request_reset(EMAIL)
    unknown = service.request_reset("nobody@example.com")
    # 밖에서 보이는 모양이 같아야 한다. 둘 다 예외 없이 끝난다.
    assert type(known) is type(unknown)
    assert known.delivered == unknown.delivered


def test_request_alone_changes_nothing(user):
    """남이 내 주소로 요청을 눌러도 내 비밀번호는 그대로다."""
    service.request_reset(EMAIL)
    who, _token = service.log_in(EMAIL, PASSWORD)
    assert who.id == user.id


# ── 토큰 ───────────────────────────────────────────────────────────
def _issue(user_id: str) -> str:
    return store.new_token(user_id, "reset", service.RESET_TTL)


def test_token_works_once(user):
    token = _issue(user.id)
    service.reset_password(token, NEW_PASSWORD)
    with pytest.raises(service.AuthError):
        service.reset_password(token, "Another-pass-word-77")


def test_expired_token_is_refused(user):
    token = store.new_token(user.id, "reset", -1)   # 이미 만료
    with pytest.raises(service.AuthError):
        service.reset_password(token, NEW_PASSWORD)


def test_a_new_request_kills_the_previous_link(user):
    """메일을 세 번 보내면 링크가 세 개 살아 있게 된다. 그중 둘은
    사용자가 잊은 채 메일함에 남는다. 가장 최근 것만 산다."""
    old = _issue(user.id)
    new = _issue(user.id)
    with pytest.raises(service.AuthError):
        service.reset_password(old, NEW_PASSWORD)
    service.reset_password(new, NEW_PASSWORD)      # 예외가 나면 실패


def test_verify_token_cannot_reset_a_password(user):
    """종류가 다른 토큰은 서로의 자리에서 쓸 수 없다."""
    token = store.new_token(user.id, "verify", 60)
    with pytest.raises(service.AuthError):
        service.reset_password(token, NEW_PASSWORD)


def test_reset_enforces_password_rules(user):
    token = _issue(user.id)
    with pytest.raises(service.AuthError):
        service.reset_password(token, "1234")


# ── 세션 ───────────────────────────────────────────────────────────
def test_reset_drops_every_existing_session(user):
    """되찾는 이유는 대개 누가 들어와 있기 때문이다."""
    _who, stolen = service.log_in(EMAIL, PASSWORD)
    assert store.session_user(stolen) is not None
    service.reset_password(_issue(user.id), NEW_PASSWORD)
    assert store.session_user(stolen) is None, "훔쳐간 세션이 살아 있다"


def test_old_password_stops_working(user):
    service.reset_password(_issue(user.id), NEW_PASSWORD)
    with pytest.raises(service.AuthError):
        service.log_in(EMAIL, PASSWORD)
    service.log_in(EMAIL, NEW_PASSWORD)           # 예외가 나면 실패


# ── 이메일 확인 ────────────────────────────────────────────────────
def test_new_account_is_not_verified(user):
    assert store.user_by_id(user.id).email_verified is False
    assert user.public()["email_verified"] is False


def test_verification_link_marks_the_address(user):
    service.request_verification(user.id)
    token = store.new_token(user.id, "verify", service.VERIFY_TTL)
    service.verify_email(token)
    assert store.user_by_id(user.id).email_verified is True


def test_opening_a_reset_link_also_verifies_the_address(user):
    """재설정 링크를 열었다는 것은 그 메일함을 실제로 쓴다는 뜻이다."""
    service.reset_password(_issue(user.id), NEW_PASSWORD)
    assert store.user_by_id(user.id).email_verified is True


# ── 메일 ───────────────────────────────────────────────────────────
def test_without_smtp_we_say_it_did_not_go_out(user):
    """여기서 '보냈다'고 답하면 사용자는 오지 않는 메일을 기다린다."""
    d = service.request_reset(EMAIL)
    assert d.delivered is False
    assert d.how in ("log", "none")


def test_the_link_points_at_the_public_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://ai-company.example/")
    assert mail.public_url() == "https://ai-company.example"


def test_log_delivery_does_not_print_the_whole_address(monkeypatch, capsys):
    """로그는 오래 남고 여러 사람이 본다."""
    events = []
    monkeypatch.setattr(mail.bus, "say",
                        lambda who, text, **kw: events.append(text))
    mail.send_reset("verylongname@example.com", "tok")
    body = "\n".join(events)
    assert "verylongname@example.com" not in body
    assert "example.com" in body            # 어느 도메인인지는 남는다


def test_rate_limit_applies_to_reset_requests(user):
    """남의 메일함을 우리 서버로 때리는 일도 남용이다."""
    with pytest.raises(service.AuthError):
        for _ in range(50):
            service.request_reset(EMAIL)
