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
import ast
import io
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

# SaaS 로 열리는 경로들. 이 파일들 안의 거절 문장은 사용자가 본다.
GUARDED = ("main.py", "auth/deps.py", "api/auth.py", "api/projects.py",
           "auth/service.py", "auth/passwords.py",
           "orchestrator/engine.py", "secrets_broker.py",
           "providers/base.py", "providers/registry.py",
           "providers/claude.py", "providers/gemini.py",
           "providers/openai.py", "providers/anthropic_client.py",
           "attachments.py", "orchestrator/manual.py", "usage/credits.py",
           "auth/mail.py",
           "tools/project_fs.py", "agents/json_io.py",
           "agents/employee.py")

KOREAN = re.compile(r"[가-힣]")
# 따옴표 안의 한국어. 주석은 위에서 지웠고, 번역된 호출의 인자는 키라
# ASCII 다 — 그래서 여기 걸리는 것은 "손으로 쓴 문장"뿐이다.
KOREAN_LITERAL = re.compile(
    r'"[^"\n]*[가-힣][^"\n]*"'      # "…한국어…"
    r"|'[^'\n]*[가-힣][^'\n]*'"     # '…한국어…'
)
# 사용자가 읽는 거절이 만들어지는 자리들. HTTPException 뿐 아니라
# 도메인 예외도 화면까지 그대로 올라간다 — 엔드포인트가 `str(e)` 를
# 그대로 넘기기 때문이다.
RAISE = re.compile(r"HTTPException\(|Delivery\(|AuthError\(|out\.append\("
                   r"|Stop\(|ProviderUnavailable\(|TransientError\(|RefusedError\(|Busy\(|Denied\(|super\(\).__init__\(|ParseFailed\(|EmployeeFailed\(")


# 로그로 나가는 문장도 사용자가 읽는다. 다만 `bus.say` 는 **옛 제품의
# 로컬 도구**(agents/core.py · approvals.py · tools/agent_tools.py)에서도
# 잔뜩 쓰인다 — 거기는 DEPLOY_MODE=local 전용이라 번역 대상이 아니다.
# 그래서 SaaS 경로로 열리는 파일에서만 본다.
SAY_FILES = ("orchestrator/engine.py", "orchestrator/manual.py",
             "providers/anthropic_client.py", "providers/base.py")
# 프로젝트 화면의 "중단 사유"도 사용자가 읽는다. 그 자리는 `save_meta`
# 로 들어간다 — DAY 22 에 한국어 한 줄이 거기 남아 있었다.
META = re.compile(r"save_meta" + chr(92) + "(")
META_FILES = ("orchestrator/engine.py", "orchestrator/manual.py")
SAY = re.compile(r"bus" + chr(92) + ".say" + chr(92) + "(|bus" + chr(92) + ".phase" + chr(92) + "(")


# `ValueError` 는 두 가지로 쓰인다 — 사용자에게 보이는 거절과, 개발자만
# 보는 불변식 위반("빈 비밀번호는 해싱하지 않습니다"). 뒤쪽은 번역할 것이
# 아니라 애초에 사용자에게 갈 일이 없는 문장이므로, 앞쪽 파일에서만 본다.
USER_VALUE_ERRORS = ("attachments.py", "orchestrator/manual.py",
                     "usage/credits.py")
VALUE_ERROR = re.compile(r"ValueError" + chr(92) + "(")


def _code(path: Path) -> list[str]:
    """주석과 독스트링을 뺀 줄들. 설명까지 잡으면 검사가 못 쓰게 된다.

    독스트링은 **줄 수를 유지한 채** 지운다. 그냥 지우면 뒤쪽 줄 번호가
    전부 밀려서 검사가 엉뚱한 줄을 가리킨다 — 실제로 그랬다. 잘못된
    자리를 가리키는 검사는 고치는 사람을 한 번 더 헤매게 만든다.

    **삼중따옴표를 전부 지우면 안 된다.** 설명만 그 모양인 게 아니라,
    대입된 긴 문자열도 그 모양이다 — 거기 한국어 문장을 넣으면 검사가
    통째로 못 본다. `tests/test_portability.py` 가 같은 이유로 SQL 의
    대부분을 못 보고 있었다(DAY 22). 그래서 문법 트리로 **독스트링
    노드만** 고른다.
    """
    text = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(text)
    except SyntaxError:                                        # pragma: no cover
        tree = None
    drop: set[int] = set()
    for node in ast.walk(tree) if tree else []:
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            drop.update(range(first.lineno,
                              (first.end_lineno or first.lineno) + 1))
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        out.append("" if i in drop else re.sub(r"#.*$", "", line))
    return out


def test_rejections_go_through_the_translation_table():
    bad = []
    for rel in GUARDED:
        path = APP / rel
        if not path.exists():
            continue
        lines = _code(path)
        for i, line in enumerate(lines):
            meta_hit = rel in META_FILES and META.search(line)
            hit = RAISE.search(line) or (
                rel in USER_VALUE_ERRORS and VALUE_ERROR.search(line)) or (
                rel in SAY_FILES and SAY.search(line)) or meta_hit
            if not hit:
                continue
            # 문장이 다음 줄로 넘어가는 경우가 있다. 세 줄까지 본다.
            # `save_meta` 는 여러 줄짜리 딕셔너리를 받으므로 더 본다 —
            # 3줄로 두니 실제로 있던 한국어 한 줄을 놓쳤다.
            blob = " ".join(lines[i:i + (10 if meta_hit else 3)])
            # "이 줄 어딘가에 lang.t 가 있으면 통과"로 하면 **섞인 줄**이
            # 빠져나간다 — 한쪽 분기만 번역돼 있어도 통과했다. 실제로 그런
            # 줄이 MANUAL 로그에 있었다. 그래서 한국어가 **문자열 리터럴
            # 안에** 있는지를 본다. 번역된 호출의 인자는 키(ASCII)라
            # 한국어가 남을 수 없다.
            if KOREAN_LITERAL.search(blob):
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
                "att.", "manual.", "plan.", "fs.", "json.", "mail.")
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


def test_permission_refusals_read_in_the_users_language(tmp_path, monkeypatch):
    """이 문장은 **작업 로그 안으로 들어간다** (`log.denied` 의 {why} 자리).

    직원이 자기 구역 밖에 쓰려 했다는 사실은 이 제품의 핵심 장치다. 틀은
    번역해두고 이유만 한국어로 박히면, 영어로 쓰는 사람은 로그에서 무엇을
    막았는지 읽을 수 없다.
    """
    from app import config, lang
    from app.database import store
    from app.tools import project_fs as pfs

    monkeypatch.setattr(config, "PROJECTS", tmp_path / "projects")
    slug = store.new_project("permission refusal")
    pfs.use(slug)
    try:
        with lang.bind("en"):
            with pytest.raises(pfs.Denied) as got:
                pfs.write("src/backdoor.py", "import os", "writer")
            why = str(got.value)
            assert "cannot write to src/" in why, why
            # 직함도 번역된 값으로 나온다 — "이서준(작가)" 이 아니라
            # "이서준(Writer)". **이름은 번역하지 않는다**(사람 이름이고
            # 고객이 바꿔둔 것일 수도 있다), 그래서 이 줄에 한글이 남는
            # 것은 정상이다 — 남으면 안 되는 것은 직함과 설명이다.
            assert "Writer" in why, why
            assert "작가" not in why, why

            with pytest.raises(pfs.Denied) as got:
                pfs.write("../escape.py", "x", "SYSTEM")
            assert "outside the project folder" in str(got.value)

        with lang.bind("ja"):
            with pytest.raises(pfs.Denied) as got:
                pfs.write("src/backdoor.py", "import os", "writer")
            assert "書き込み権限" in str(got.value)
    finally:
        pfs.release()


def test_the_log_speaker_labels_follow_the_language():
    """로그의 **말하는 이** 표시가 `bus.roster()` 에서 나온다.

    이 한 줄이 한국어면 영어 로그의 모든 말풍선에 한국어 직함이 붙는다.
    이름은 번역하지 않는다(테넌트가 바꿀 수 있다), 직함 글자만 따라간다.
    """
    from app import bus, lang

    with lang.bind("en"):
        roster = bus.roster()
    assert "(Developer)" in roster["developer"]["name"], roster["developer"]
    assert "(개발자)" not in roster["developer"]["name"]

    with lang.bind("ja"):
        assert "(開発者)" in bus.roster()["developer"]["name"]


def test_unreadable_model_answers_are_reported_in_the_users_language():
    """모델이 스키마를 어긴 사실은 로그에 뜨고, 세 번 실패하면 화면의
    실패 사유가 된다. 같은 문장이 모델에게 되돌아가는 수정 요청에도 들어간다."""
    from app import lang
    from app.agents import json_io
    from app.agents.schemas import Plan

    with lang.bind("en"):
        with pytest.raises(json_io.ParseFailed) as got:
            json_io.parse("여기에는 객체가 없습니다", Plan)
        assert "no JSON object" in str(got.value), str(got.value)

        with pytest.raises(json_io.ParseFailed) as got:
            json_io.parse('{"project_name": 1}', Plan)
        assert "Schema violation" in str(got.value), str(got.value)

    with lang.bind("ja"):
        with pytest.raises(json_io.ParseFailed) as got:
            json_io.parse("オブジェクトがありません", Plan)
        assert "オブジェクト" in str(got.value)


# 이 파일들의 글은 **전부** 사용자에게 간다. 프롬프트(모델용)나 내부
# 불변식이 섞이지 않으므로, 한국어 리터럴이 하나라도 있으면 번역표를
# 안 거친 것이다.
#
# 줄 근처를 보는 검사(`test_rejections_...`)는 이걸 못 잡는다. 문장을
# 상수로 빼서 이름으로 부르면 보이지 않기 때문이다 — DAY 22 에 탐침을
# 넣어보고 알았고, 실제로 **메일 제목·본문 전체**가 그렇게 숨어 있었다.
ALL_USER_FACING = ("auth/mail.py", "auth/deps.py")


def test_files_that_only_talk_to_users_have_no_korean_left():
    bad = []
    for rel in ALL_USER_FACING:
        for i, line in enumerate(_code(APP / rel), 1):
            if KOREAN_LITERAL.search(line):
                bad.append(f"{rel}:{i}: {line.strip()[:70]}")
    assert not bad, (
        "이 파일의 글은 전부 사용자에게 갑니다. 번역표로 옮기세요:\n"
        + "\n".join(bad))
