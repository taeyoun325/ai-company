"""비밀번호 해시 (DAY 15).

## 왜 scrypt 인가

bcrypt·argon2 는 이 환경에 설치돼 있지 않고, 의존성을 하나 늘리는 것보다
표준 라이브러리로 제대로 하는 편이 낫다고 봤다. `hashlib.scrypt` 는
**메모리 하드**라서 GPU 로 병렬 추측하는 공격에 강하다 — 그게 이 자리에서
중요한 성질이다. `pbkdf2_hmac` 도 표준이지만 메모리를 안 쓰므로 같은
예산이면 훨씬 많이 시도당한다.

## 왜 파라미터를 해시 문자열에 같이 적나

컴퓨터는 매년 빨라지므로 비용(n)을 올려야 하는 날이 온다. 파라미터를
코드에 박아두면 올리는 순간 **기존 사용자가 전부 로그인 실패**한다.
그래서 해시마다 자기가 어떤 파라미터로 만들어졌는지 들고 다닌다:

    scrypt$65536$8$1$<salt-b64>$<hash-b64>

검증은 저장된 파라미터로, 새 해시는 현재 기본값으로 만든다.
`needs_rehash()` 가 "이 해시는 낡았다"를 알려주므로, 로그인에 성공한
그 순간(평문을 쥐고 있는 유일한 시점) 조용히 다시 해싱할 수 있다.

## 상수 시간 비교

`==` 로 비교하면 앞에서부터 몇 글자가 맞았는지가 **시간 차이로 샌다.**
`hmac.compare_digest` 를 쓴다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app import lang

SCHEME = "scrypt"

# OWASP 권고에 가까운 값. n 은 2의 거듭제곱이어야 한다.
# 이 조합은 이 개발 머신에서 약 220ms · 64MB 다.
N = 2 ** 16
R = 8
P = 1
DKLEN = 32
SALT_BYTES = 16

# scrypt 는 maxmem 을 넘기면 거부한다. 필요한 양(128*n*r)에 여유를 둔다.
_MAXMEM = 128 * N * R * 2


class InvalidHash(ValueError):
    """저장된 해시를 읽을 수 없다. 데이터가 깨졌거나 다른 형식이다."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str, *, n: int = N, r: int = R, p: int = P) -> str:
    """평문을 저장 가능한 문자열로. 같은 비밀번호라도 매번 다르게 나온다.

    소금(salt)을 사용자마다 따로 두는 이유: 같은 비밀번호를 쓰는 두 사람의
    해시가 같으면, 하나가 풀릴 때 둘 다 풀린다. 미리 계산해둔 표
    (레인보우 테이블)도 소금이 있으면 쓸모가 없다.
    """
    if not password:
        raise ValueError("빈 비밀번호는 해싱하지 않습니다")
    salt = os.urandom(SALT_BYTES)
    raw = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                         dklen=DKLEN, maxmem=128 * n * r * 2)
    return f"{SCHEME}${n}${r}${p}${_b64(salt)}${_b64(raw)}"


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes]:
    try:
        scheme, n, r, p, salt, raw = stored.split("$")
    except ValueError as e:
        raise InvalidHash("해시 형식이 아닙니다") from e
    if scheme != SCHEME:
        raise InvalidHash(f"모르는 해시 방식: {scheme}")
    try:
        return int(n), int(r), int(p), _unb64(salt), _unb64(raw)
    except (ValueError, base64.binascii.Error) as e:   # type: ignore[attr-defined]
        raise InvalidHash("해시를 읽지 못했습니다") from e


def verify(password: str, stored: str) -> bool:
    """맞으면 True. **어떤 경우에도 예외로 새어나가지 않는다.**

    깨진 해시에 예외를 던지면, 그 예외의 유무가 곧 "이 계정은 뭔가
    다르다"는 신호가 된다. 읽지 못하는 해시는 그냥 불일치로 본다.
    """
    if not password or not stored:
        return False
    try:
        n, r, p, salt, expected = _parse(stored)
        got = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                             dklen=len(expected), maxmem=128 * n * r * 2)
    except (InvalidHash, ValueError, MemoryError):
        return False
    return hmac.compare_digest(got, expected)


def needs_rehash(stored: str) -> bool:
    """현재 기본값보다 약한 파라미터로 만들어진 해시인가.

    로그인에 성공한 순간은 평문을 쥐고 있는 유일한 시점이다. 그때
    다시 해싱하면 사용자는 아무것도 안 해도 보호 수준이 올라간다.
    """
    try:
        n, r, p, _salt, _raw = _parse(stored)
    except InvalidHash:
        return True
    return (n, r, p) < (N, R, P)


# ── 비밀번호 규칙 ───────────────────────────────────────────────────
MIN_LENGTH = 10

# 길이가 짧은 것보다 **흔한 것**이 먼저 뚫린다. 전체 목록을 들고 있을 수는
# 없으니, 실제 유출 목록 상위에서 이 제품과 관련될 법한 것만 막는다.
# 이건 방어가 아니라 '가장 나쁜 선택'을 거르는 체다.
_COMMON = {
    "password", "passw0rd", "p@ssword", "qwertyuiop", "1234567890",
    "12345678910", "aicompany", "aicompany1", "letmein123", "iloveyou1",
    "administrator", "1q2w3e4r5t", "asdfghjkl1", "zxcvbnm123",
}


def problems(password: str, email: str = "") -> list[str]:
    """비밀번호가 규칙에 안 맞는 이유들. 빈 목록이면 통과.

    이유를 **전부** 돌려주는 이유: 하나씩 알려주면 사용자가 하나씩
    고치며 여러 번 거절당한다. 한 번에 보여준다.
    """
    out: list[str] = []
    if len(password) < MIN_LENGTH:
        out.append(lang.t("pw.short", n=MIN_LENGTH))
    if len(password) > 200:
        # 상한을 두는 이유: scrypt 는 입력 길이에 비례해 시간을 쓰므로,
        # 아주 긴 비밀번호를 반복 제출하면 그 자체가 부하 공격이 된다.
        out.append(lang.t("pw.long"))
    if password.lower() in _COMMON:
        out.append(lang.t("pw.common"))
    local = email.split("@")[0].strip().lower()
    if local and len(local) >= 3 and local in password.lower():
        out.append(lang.t("pw.hasEmail"))
    if password.strip() != password:
        # 앞뒤 공백은 붙여넣기 사고로 들어오고, 사용자는 왜 로그인이
        # 안 되는지 영영 모른다.
        out.append(lang.t("pw.spaces"))
    return out
