"""메일 발송기를 **실제로 태워본다** (DAY 22).

## 왜 이 파일이 있나

`STATUS.md` 에 이렇게 적혀 있었다: "`SMTPSender` 는 한 번도 실제 서버에
붙여본 적이 없다." SMTP 계정이 없어서였다. 그런데 계정이 없다는 것은
**남의 서버**가 없다는 뜻이고, 프로토콜을 말하는 서버는 우리가 이 자리에서
띄울 수 있다.

그래서 소켓 하나로 SMTP 를 흉내 내는 서버를 띄우고, 우리 코드가 보낸
바이트를 받아 확인한다. 이걸로 잡히는 것:

  - `EmailMessage` 가 실제로 전송 가능한 형태인가 (From/To/Subject/본문)
  - `smtplib` 사용 순서가 맞는가 (EHLO → MAIL FROM → RCPT TO → DATA → QUIT)
  - 링크가 메일 본문에 들어가는가
  - STARTTLS 를 안 내미는 서버를 만났을 때의 판단

이걸로 **안 잡히는 것**: 진짜 제공자의 TLS·인증·스팸 정책. 그건 계정이
생기는 날의 몫이다. 다만 "코드가 문법적으로 맞아 보인다"와 "서버가 받았다"
사이의 거리는 여기서 지워진다.
"""
import socket
import threading
from email import message_from_string

import pytest

from app.auth import mail


class FakeSMTP:
    """STARTTLS 를 내밀지 않는 평문 SMTP 서버. 한 통만 받고 닫는다.

    우리가 확인하려는 것은 **우리 쪽 대화**이므로, 서버는 문법을 아는
    최소한만 한다. 실제 서버처럼 굴 필요는 없다 — 그렇게 만들면 이 파일이
    테스트가 아니라 또 하나의 제품이 된다.
    """

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.commands: list[str] = []
        self.data = ""
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        conn, _ = self.sock.accept()
        with conn:
            f = conn.makefile("rwb")
            f.write(b"220 fake.local ESMTP\r\n")
            f.flush()
            in_data = False
            while True:
                line = f.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if in_data:
                    if text == ".":
                        in_data = False
                        f.write(b"250 OK queued\r\n")
                        f.flush()
                        continue
                    self.data += text + "\n"
                    continue
                self.commands.append(text)
                upper = text.upper()
                if upper.startswith("EHLO") or upper.startswith("HELO"):
                    # 능력 목록에 STARTTLS 를 **넣지 않는다.** 로컬 릴레이가
                    # 대개 이렇고, 그 경로가 여기서 확인하려는 것이다.
                    f.write(b"250-fake.local\r\n250 SIZE 10240000\r\n")
                elif upper.startswith("DATA"):
                    in_data = True
                    f.write(b"354 end with .\r\n")
                elif upper.startswith("QUIT"):
                    f.write(b"221 bye\r\n")
                    f.flush()
                    return
                else:
                    f.write(b"250 OK\r\n")
                f.flush()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


@pytest.fixture
def fake_smtp():
    server = FakeSMTP()
    yield server
    server.close()


def test_a_real_socket_receives_the_reset_mail(fake_smtp, monkeypatch):
    """이 제품이 보낸 바이트를 서버가 받는다. 계정 없이 확인되는 마지막 구간."""
    monkeypatch.setenv("SMTP_URL", f"smtp://127.0.0.1:{fake_smtp.port}")
    monkeypatch.setenv("MAIL_FROM", "no-reply@ai-company.test")
    monkeypatch.setenv("PUBLIC_URL", "https://app.example.test")

    d = mail.send_reset("someone@example.test", "tok-123")

    assert d.delivered is True, d.detail
    assert d.how == "smtp"

    fake_smtp.thread.join(timeout=5)
    said = " ".join(fake_smtp.commands).upper()
    assert "EHLO" in said
    assert "MAIL FROM:<NO-REPLY@AI-COMPANY.TEST>" in said
    assert "RCPT TO:<SOMEONE@EXAMPLE.TEST>" in said
    assert "DATA" in said

    # 받은 바이트를 **메일로 읽는다.** 한국어 본문은 base64 로 나가므로
    # 날 문자열 검사로는 통과하지 않는다 — 그 사실도 이 검사가 알려줬다.
    received = message_from_string(fake_smtp.data)
    assert received["Subject"] and "AI COMPANY" in received["Subject"]
    assert received["To"] == "someone@example.test"
    text = received.get_payload(decode=True).decode("utf-8")
    # 링크가 메일에 실제로 들어갔는가. 토큰만 보내면 사용자는 그걸 어디에
    # 붙여야 하는지 모른다.
    assert "https://app.example.test/reset?token=tok-123" in text


def test_plaintext_outside_this_machine_is_refused(monkeypatch):
    """평문으로 나가는 메일에는 비밀번호 재설정 링크가 들어 있다.

    예전 코드는 `starttls()` 를 무조건 불러 결과적으로는 막혔지만, 운영자가
    받는 문장은 "SMTPNotSupportedError" 였다. 무엇을 해야 하는지가 없다.
    """
    server = FakeSMTP()
    try:
        # 같은 서버를 **남의 기계 이름으로** 가리킨다. 호스트 판단만 바뀐다.
        monkeypatch.setattr(mail, "_is_local", lambda host: False)
        monkeypatch.setenv("SMTP_URL", f"smtp://127.0.0.1:{server.port}")

        d = mail.send("someone@example.test", "제목", "본문")

        assert d.delivered is False
        assert "STARTTLS" in d.detail
    finally:
        server.close()


def test_login_without_tls_is_refused(monkeypatch):
    """같은 기계라도 비밀번호는 평문으로 흘리지 않는다."""
    server = FakeSMTP()
    try:
        monkeypatch.setenv(
            "SMTP_URL", f"smtp://user:secret@127.0.0.1:{server.port}")

        d = mail.send("someone@example.test", "제목", "본문")

        assert d.delivered is False
        assert "TLS" in d.detail
    finally:
        server.close()


def test_without_smtp_url_nothing_is_claimed_to_be_sent():
    """발송기가 없을 때 `delivered=True` 를 돌려주면, 사용자는 오지 않는
    메일을 영원히 기다리고 운영자는 그 사실을 모른다."""
    d = mail.send("someone@example.test", "제목", "본문")
    assert d.delivered is False
    assert d.how == "log"


# ── 출항 전 점검 (DAY 22) ──────────────────────────────────────────
def _mail_rows(monkeypatch, **env):
    from app import preflight

    monkeypatch.setenv("DEPLOY_MODE", "saas")
    monkeypatch.setenv("PUBLIC_URL", "https://app.example.test")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return [r for r in preflight.checks() if r["check"].startswith("메일")]


def test_preflight_mail_checks_actually_run(monkeypatch):
    """이 줄들은 **한 번도 실행된 적이 없었다.**

    `app/preflight.py` 에 `import os` 가 없는데 메일 점검이 `os.getenv` 를
    쓰고 있었다. SaaS 이고 SMTP 가 설정돼 있을 때만 닿는 줄이라, 개발
    중에는 영원히 안 닿는다 — 배포하는 날 NameError 로 터진다.

    점검은 "배포 전에 문제를 말해주는 것"이므로, 점검 자체가 터지면
    최악이다. 그래서 갈래마다 한 번씩 밟는다.
    """
    rows = _mail_rows(monkeypatch, SMTP_URL="smtps://u:p@smtp.example.test")
    assert [r["level"] for r in rows] == ["ok"]
    assert "SMTPS" in rows[0]["detail"]


def test_preflight_warns_about_plaintext_smtp_to_another_machine(monkeypatch):
    """발송기가 런타임에 거절할 조건을 **미리** 말한다. 그 조건은 비밀번호를
    잊은 사용자가 처음 버튼을 누르는 날에 드러나고, 그때는 아무도 보고
    있지 않다."""
    rows = _mail_rows(monkeypatch, SMTP_URL="smtp://smtp.example.test")
    assert rows and rows[0]["level"] == "warn"
    assert "STARTTLS" in rows[0]["detail"]
    assert rows[0]["fix"]

    # 로컬 릴레이는 경고하지 않는다 — 평문이 네트워크를 타지 않는다.
    rows = _mail_rows(monkeypatch, SMTP_URL="smtp://127.0.0.1:1025")
    assert [r["level"] for r in rows] == ["ok"]

    # 같은 기계라도 계정이 붙어 있으면 발송이 거절되므로 경고한다.
    rows = _mail_rows(monkeypatch, SMTP_URL="smtp://u:p@localhost:1025")
    assert rows and rows[0]["level"] == "warn"


def test_preflight_still_warns_when_the_link_would_point_at_localhost(monkeypatch):
    from app import preflight

    monkeypatch.setenv("DEPLOY_MODE", "saas")
    monkeypatch.setenv("SMTP_URL", "smtps://u:p@smtp.example.test")
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("BACKEND_ORIGIN", raising=False)

    rows = [r for r in preflight.checks() if r["check"].startswith("메일")]
    assert rows and rows[0]["level"] == "warn"
    assert "localhost" in rows[0]["detail"]
