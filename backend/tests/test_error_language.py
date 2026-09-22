"""거절 문장도 번역표를 거친다 (DAY 22).

## 왜 이 검사가 있나

화면은 서버가 준 문장을 **그대로** 찍는다(`frontend/src/lib/i18n.tsx` 의
`useErrorText`). 그래서 `HTTPException(404, "없는 프로젝트")` 처럼 여기서
한국어를 쓰면, 화면 글자를 전부 번역해놓고도 **무언가 잘못됐을 때만**
한국어가 튀어나온다. 하필 사용자가 제일 주의 깊게 읽는 순간이다.

DAY 22 에 세어보니 그런 자리가 40군데였다. 손으로 고쳤지만, 손으로 고친
것은 다음 주에 다시 늘어난다 — 새 엔드포인트를 쓰면서 문장을 바로 적는
것이 제일 자연스럽기 때문이다. 그래서 기계가 지키게 한다.

## 무엇을 검사하지 않나

`app/api/local_tools.py` 는 `DEPLOY_MODE=local` 에서만 열린다(§배포 자세).
혼자 쓰는 도구라 화면도 한국어 하나뿐이고, 번역할 대상이 아니다.
"""
import io
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# SaaS 로 열리는 경로들. 이 파일들 안의 거절 문장은 사용자가 본다.
GUARDED = ("main.py", "auth/deps.py", "api/auth.py", "api/projects.py",
           "auth/service.py", "auth/passwords.py",
           "orchestrator/engine.py", "secrets_broker.py",
           "providers/base.py", "providers/registry.py",
           "providers/claude.py", "providers/gemini.py",
           "providers/openai.py", "providers/anthropic_client.py",
           "attachments.py", "orchestrator/manual.py", "usage/credits.py")

KOREAN = re.compile(r"[가-힣]")
# 사용자가 읽는 거절이 만들어지는 자리들. HTTPException 뿐 아니라
# 도메인 예외도 화면까지 그대로 올라간다 — 엔드포인트가 `str(e)` 를
# 그대로 넘기기 때문이다.
RAISE = re.compile(r"HTTPException\(|AuthError\(|out\.append\("
                   r"|Stop\(|ProviderUnavailable\(|TransientError\(|RefusedError\(|Busy\(")


# `ValueError` 는 두 가지로 쓰인다 — 사용자에게 보이는 거절과, 개발자만
# 보는 불변식 위반("빈 비밀번호는 해싱하지 않습니다"). 뒤쪽은 번역할 것이
# 아니라 애초에 사용자에게 갈 일이 없는 문장이므로, 앞쪽 파일에서만 본다.
USER_VALUE_ERRORS = ("attachments.py", "orchestrator/manual.py",
                     "usage/credits.py")
VALUE_ERROR = re.compile(r"ValueError" + chr(92) + "(")


def _code(path: Path) -> list[str]:
    """주석과 독스트링을 뺀 줄들. 설명까지 잡으면 검사가 못 쓰게 된다."""
    text = io.open(path, encoding="utf-8").read()
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    out = []
    for line in text.splitlines():
        stripped = re.sub(r"#.*$", "", line)
        out.append(stripped)
    return out


def test_rejections_go_through_the_translation_table():
    bad = []
    for rel in GUARDED:
        path = APP / rel
        if not path.exists():
            continue
        lines = _code(path)
        for i, line in enumerate(lines):
            hit = RAISE.search(line) or (
                rel in USER_VALUE_ERRORS and VALUE_ERROR.search(line))
            if not hit:
                continue
            # 문장이 다음 줄로 넘어가는 경우가 있다. 세 줄까지 본다.
            blob = " ".join(lines[i:i + 3])
            if KOREAN.search(blob) and "lang.t(" not in blob:
                bad.append(f"{rel}:{i + 1}: {line.strip()[:70]}")
    assert not bad, (
        "거절 문장이 번역표를 거치지 않습니다. `app/lang.py` 에 키를 넣고 "
        "`lang.t(...)` 로 바꾸세요:\n" + "\n".join(bad))


def test_the_table_answers_in_every_language():
    """키만 넣고 번역을 안 채우면 `t()` 가 키를 그대로 돌려준다 —
    화면에 `err.noProject` 가 찍힌다. 그건 번역이 아니라 고장이다."""
    from app import lang

    # 거절에 쓰는 앞자리 전부. 하나 늘릴 때마다 여기에 적는다.
    prefixes = ("err.", "auth.", "pw.", "stop.", "prov.",
                "att.", "manual.", "plan.")
    keys = [k for k in lang._M if k.startswith(prefixes)]
    assert len(keys) > 20, f"거절 문장 키가 너무 적습니다: {len(keys)}"
    for key in keys:
        for code in lang.LANGS:
            with lang.bind(code):
                out = lang.t(key)
            assert out and out != key, f"{key} 가 {code} 에서 비어 있습니다"


def test_signup_rejections_follow_the_request_language():
    """가입 화면은 제품에서 **제일 먼저** 보는 화면이다. 여기가 한국어면
    영어로 쓰는 사람은 계정을 만들다 막히고, 막힌 이유도 못 읽는다."""
    from app import lang
    from app.auth import passwords, service

    with lang.bind("en"):
        try:
            service.sign_up("not-an-email", "Str0ng-Passphrase-42")
        except service.AuthError as e:
            assert "valid email" in str(e), str(e)
        else:
            raise AssertionError("잘못된 이메일이 통과했습니다")

        issues = passwords.problems("short", "someone@example.com")
        assert issues and not any(_korean(i) for i in issues), issues
        assert service.same_message() == "Email or password is incorrect."

    with lang.bind("ja"):
        assert "パスワード" in service.same_message()


def _korean(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)
