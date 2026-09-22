"""번역표에 빈칸이 없는가 (DAY 22).

## 왜 이 파일이 있나

DAY 22 에 번역 결함을 열 몇 개 고쳤는데, **전부 같은 모양**이었다: 표에
없는 문자열이 아니라, 표를 **거치지 않고** 화면에 닿는 경로였다. 그건
`tests/test_error_language.py` 가 막는다.

남은 위험은 반대쪽 둘이다:

1. 표 **안의 빈칸**. `t()` 는 없는 언어를 기본값(한국어)으로 떨어뜨린다.
   화면은 멀쩡히 돌고, 그 줄만 조용히 한국어로 나온다.
2. 표에 **없는 키를 부르는 곳**. 그때는 화면에 `office.ask` 같은 키가
   그대로 찍힌다. 빈 문자열로 두는 것보다는 낫지만 제품은 아니다.

둘 다 지금은 하나도 없다(백엔드 114키 · 화면 304키, 빈칸 0). 그러나
"지금 맞다"와 "계속 맞다"는 다르다. 언어를 하나 빠뜨린 채 키를 추가하는
것은 5초면 되고, 그걸 알아차리는 데는 며칠이 걸린다.

## 화면 표를 파이썬이 읽는 것에 대해

프런트엔드에는 테스트 러너가 없다. 러너를 들이는 것은 이 검사 하나보다
큰 일이므로, 그때까지는 여기서 TS 파일을 읽는다. 파서가 아니라 **중괄호
세기**다 — 표의 모양이 바뀌면 이 검사가 먼저 깨지고, 깨지면 고치면 된다.
조용히 통과하지만 않으면 된다(아래 `test_the_frontend_table_was_actually_read`).
"""
import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
I18N = ROOT / "frontend" / "src" / "lib" / "i18n.tsx"
SRC = ROOT / "frontend" / "src"

sys.path.insert(0, str(ROOT / "backend"))

from app import lang                                            # noqa: E402


def _block(text: str, open_at: int) -> tuple[str, int]:
    """`{` 위치에서 짝이 맞는 `}` 까지. 문자열 안의 중괄호는 이 표에 없다."""
    depth = 0
    i = open_at
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at:i + 1], i
        i += 1
    raise AssertionError("중괄호가 닫히지 않았습니다 — 표의 모양이 바뀌었습니다")


def _frontend_entries() -> list[tuple[str, str]]:
    src = io.open(I18N, encoding="utf-8").read()
    start = src.index("{", src.index("const S"))
    table, _ = _block(src, start)
    out = []
    for m in re.finditer(r'"([\w.]+)":\s*\{', table):
        body, _ = _block(table, m.end() - 1)
        out.append((m.group(1), body))
    return out


def test_the_backend_table_has_every_language():
    """`t()` 는 없는 언어를 조용히 한국어로 떨어뜨린다. 화면은 멀쩡히
    돌고 그 줄만 한국어로 나간다 — 제일 찾기 어려운 종류다."""
    bad = []
    for key, row in lang._M.items():
        for code in lang.LANGS:
            if not (row.get(code) or "").strip():
                bad.append(f"{key} → {code}")
    assert not bad, "번역이 빠진 자리:\n" + "\n".join(bad)


def test_the_frontend_table_has_every_language():
    bad = []
    for key, body in _frontend_entries():
        for code in ("ko", "en", "ja"):
            if not re.search(rf"\b{code}\s*:", body):
                bad.append(f"{key} → {code}")
    assert not bad, "번역이 빠진 자리:\n" + "\n".join(bad)


def test_the_frontend_table_was_actually_read():
    """중괄호 세기가 빗나가 0개를 읽고 **통과해 버리는** 것이 이 검사의
    유일한 실패 방식이다. 개수를 확인한다."""
    entries = _frontend_entries()
    assert len(entries) > 200, f"표를 제대로 읽지 못했습니다: {len(entries)}개"
    assert len(lang._M) > 80, f"서버 표가 너무 작습니다: {len(lang._M)}개"


def test_every_key_the_screens_ask_for_exists():
    """없는 키를 부르면 화면에 `office.ask` 가 그대로 찍힌다."""
    keys = {k for k, _ in _frontend_entries()}
    used: dict[str, str] = {}
    for f in list(SRC.rglob("*.tsx")) + list(SRC.rglob("*.ts")):
        if f.name == "i18n.tsx":
            continue
        text = io.open(f, encoding="utf-8").read()
        for m in re.finditer(r'\bt\(\s*"([\w.]+)"', text):
            used.setdefault(m.group(1), str(f.relative_to(SRC)))
    assert used, "t() 호출을 하나도 못 찾았습니다 — 검사가 아무것도 안 봅니다"
    missing = {k: where for k, where in used.items() if k not in keys}
    assert not missing, (
        "표에 없는 키를 부릅니다 (화면에 키가 그대로 찍힙니다):\n"
        + "\n".join(f"{k}  ({where})" for k, where in missing.items()))


@pytest.mark.parametrize("code", ["en", "ja"])
def test_no_language_silently_falls_back_to_korean(code):
    """번역이 채워져 있어도 **한국어를 그대로 복사해 넣으면** 표는 꽉 찬
    것처럼 보인다. 사람 이름·고유명사·코드가 아닌 줄에서 그런 자리를
    찾는다.
    """
    suspects = []
    for key, row in lang._M.items():
        ko, other = row.get("ko", ""), row.get(code, "")
        if not other or other != ko:
            continue
        # 같아도 되는 것들: 숫자·경로·고유명사만 들어 있는 줄.
        if not re.search(r"[가-힣]", ko):
            continue
        suspects.append(key)
    assert not suspects, (
        f"{code} 가 한국어와 똑같습니다 — 번역이 아니라 복사입니다: {suspects}")
