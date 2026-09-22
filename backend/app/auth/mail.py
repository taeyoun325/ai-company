"""메일 발송 (DAY 22).

## 계정이 없어도 구조는 끝난다

비밀번호 재설정과 이메일 인증은 **메일이 나가야** 완성되는 기능이다.
그런데 SMTP 계정은 사람이 가입해서 만들어야 하고, 그게 없다고 코드를
안 쓰면 계정이 생기는 날 처음부터 만들게 된다.

그래서 발송기를 인터페이스로 두고, 기본을 **로그 발송기**로 한다.
메일은 실제로 나가지 않고 서버 로그에 찍힌다 — 개발과 시연에서는 그
편이 낫고(받은 편지함을 열 필요가 없다), 운영에서는 `SMTP_URL` 한 줄로
바뀐다.

## 나가지 않았다는 사실을 숨기지 않는다

로그 발송기는 "보냈다"고 답하지 않는다. `delivered=False` 로 답하고,
화면은 그 사실을 그대로 보여준다. 여기서 True 를 돌려주면 운영자가
메일 설정을 빠뜨린 채 배포하고, 사용자는 **오지 않는 메일을 영원히
기다린다.**

## 링크를 우리가 만든다

토큰만 보내면 사용자가 그걸 어디에 붙여야 하는지 모른다. 주소는
`PUBLIC_URL` 에서 온다 — 없으면 `BACKEND_ORIGIN`, 그것도 없으면
localhost 다. 운영에서 이 값을 빠뜨리면 메일 속 링크가 localhost 를
가리키므로, 프리플라이트가 그걸 경고한다.

## 아직 확인되지 않은 것

`SMTPSender` 는 **한 번도 실제 서버에 붙여본 적이 없다.** 계정이 없기
때문이다(`docs/deploy.md`). 코드는 표준 라이브러리 `smtplib` 의 일반적인
사용법대로 썼지만, 그게 동작한다는 증거는 아니다.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import urlparse

from app import bus, lang


@dataclass(frozen=True)
class Delivery:
    """보냈는가. **보내려고 했는가가 아니다.**"""
    delivered: bool
    how: str                 # "log" | "smtp"
    detail: str = ""


def public_url() -> str:
    """메일 속 링크가 가리킬 주소."""
    for key in ("PUBLIC_URL", "BACKEND_ORIGIN"):
        value = os.getenv(key, "").strip().rstrip("/")
        if value:
            return value
    return "http://localhost:3000"


def smtp_url() -> str:
    return os.getenv("SMTP_URL", "").strip()


def configured() -> bool:
    return bool(smtp_url())


def _log_send(to: str, subject: str, body: str) -> Delivery:
    """메일을 서버 로그로 흘린다.

    주소를 통째로 찍지 않는다 — 로그는 오래 남고 여러 사람이 본다.
    """
    masked = to.split("@")[0][:2] + "…@" + to.split("@")[-1]
    bus.say("SYSTEM",
            lang.t("mail.notSent", to=masked, subject=subject)
            + "\n" + body,
            kind="error")
    return Delivery(False, "log", lang.t("mail.logOnly"))


# 같은 기계 안의 릴레이. 여기까지는 평문이 네트워크를 타지 않는다.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _is_local(host: str) -> bool:
    return host.lower() in LOCAL_HOSTS


def _smtp_send(to: str, subject: str, body: str) -> Delivery:
    """실제 발송.

    ## 암호화를 조용히 건너뛰지 않는다

    예전에는 `starttls()` 를 무조건 불렀다. 서버가 STARTTLS 를 안 내밀면
    smtplib 가 예외를 던지므로 결과적으로는 막혔지만, 예외 문장은
    "SMTPNotSupportedError" 뿐이어서 운영자가 무엇을 해야 할지 알 수 없었다.

    이제 서버가 내미는 것을 보고 판단한다. 내밀면 쓰고, **안 내밀면 같은
    기계(localhost)일 때만** 평문으로 보낸다. 밖으로 나가는 평문은 거절한다
    — 메일 본문에 비밀번호 재설정 링크가 들어 있고, 계정 정보를 곁들여
    보내는 경우에는 로그인 정보까지 같이 흐른다.
    """
    url = urlparse(smtp_url())
    msg = EmailMessage()
    msg["From"] = os.getenv("MAIL_FROM", "no-reply@ai-company.local")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    host = url.hostname or "localhost"
    port = url.port or (465 if url.scheme == "smtps" else 587)
    try:
        if url.scheme == "smtps":
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()          # TLS 뒤에는 능력 목록을 다시 받는다
            elif not _is_local(host):
                server.quit()
                return Delivery(
                    False, "smtp",
                    lang.t("mail.noTls", host=host))
            elif url.username:
                # 같은 기계라도 **비밀번호는** 평문으로 흘리지 않는다.
                server.quit()
                return Delivery(
                    False, "smtp",
                    lang.t("mail.noPlainLogin"))
        with server:
            if url.username:
                server.login(url.username, url.password or "")
            server.send_message(msg)
        return Delivery(True, "smtp")
    except Exception as e:                                     # noqa: BLE001
        # 실패를 성공으로 적지 않는다. 사용자는 오지 않는 메일을 기다리게
        # 되고, 운영자는 그 사실을 모른다.
        return Delivery(False, "smtp", f"{type(e).__name__}: {e}")


def send(to: str, subject: str, body: str) -> Delivery:
    return _smtp_send(to, subject, body) if configured() else _log_send(to, subject, body)


# ── 우리가 보내는 메일 ──────────────────────────────────────────────
def send_reset(to: str, token: str) -> Delivery:
    link = f"{public_url()}/reset?token={token}"
    return send(
        to,
        "[AI COMPANY] 비밀번호 재설정",
        f"아래 주소에서 새 비밀번호를 정하세요. 30분 뒤에 만료됩니다.\n\n"
        f"{link}\n\n"
        f"본인이 요청하지 않았다면 이 메일을 무시하세요. "
        f"요청만으로는 비밀번호가 바뀌지 않습니다.\n",
    )


def send_verification(to: str, token: str) -> Delivery:
    link = f"{public_url()}/verify?token={token}"
    return send(
        to,
        "[AI COMPANY] 이메일 확인",
        f"아래 주소를 열면 이 이메일 주소가 확인됩니다. 24시간 뒤에 만료됩니다.\n\n"
        f"{link}\n",
    )
