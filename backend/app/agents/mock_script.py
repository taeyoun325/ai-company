"""Mock 직원 대본 — 키 없이 회사 전체를 돌리기 위한 것 (지시서 §1).

## 이건 임시방편이 아니다

방침상 API 키는 맨 마지막에 들어온다. 그러면 DAY 13까지 오케스트레이터·
화면·저장·과금이 **전부 이 대본 위에서만** 돌아간다. 그러니 대본은
"그럴듯한 글"이 아니라 **스키마를 지키는 진짜 응답**이어야 한다.
JSON 이 깨지면 그건 Mock 의 문제가 아니라, 우리가 만든 파서와 복구
경로가 한 번도 제대로 시험되지 않았다는 뜻이다.

## 어떻게 스키마를 아는가

`employee.ask()` 가 시스템 프롬프트에 `## 출력 스키마: Plan` 헤더를 넣는다.
그 한 줄을 읽는다. 제공자 인터페이스를 바꾸지 않아도 되고(§7), 실제 제공자가
보는 것과 **같은 프롬프트**를 보게 된다.

(스키마 본문의 첫 `"title"` 을 읽지 않는다 — 그건 최상위가 아니라 `$defs`
안의 필드일 수 있다. 실제로 처음엔 그렇게 짰다가 `"Id"` 를 집었다.)

## 결정적이다

같은 입력에 같은 답. 화면을 고칠 때마다 다른 글이 나오면 무엇이 바뀐
건지 알 수 없고, 테스트는 흔들린다. 재작업 분기도 난수가 아니라
**입력에 반려 사유가 들어 있는가**로 가른다.

## 대본도 언어를 따른다 (DAY 22)

실제 모델은 프롬프트로 언어를 정한다(`lang.prompt_line()`). **Mock 은
프롬프트를 읽지 않으므로** 그 길이 없고, 그래서 영어로 화면을 쓰는 사람이
Mock 을 돌리면 대사·문서·명세가 전부 한국어로 나왔다. 무료 요금제가 없는
제품에서 Mock 은 사실상 **데모**이고, 데모가 읽히지 않으면 결제 버튼은
눌리지 않는다.

대본 문장은 이 파일이 들고 있다 — `app/lang.py` 는 제품이 하는 말의 표이고,
여기 있는 것은 **데모 콘텐츠**다. 섞으면 그 표가 대본 저장소가 된다.

판단 로직은 언어를 타지 않는다. 재작업 여부는 프롬프트에 들어오는
`# 반려 사유` 헤더(`orchestrator/prompts.py` · 모델용이라 번역하지 않는다)로
가르고, 산출물 경로와 스키마는 그대로다.
"""
from __future__ import annotations

import json
import re

from app import lang
from app.agents import json_io
from app.providers.base import GenerateRequest

_TITLE = re.compile(re.escape(json_io.NAME_HEADER) + r"([A-Za-z]+)")

# 반려 사유가 프롬프트에 들어오면 '고친 버전'을 낸다. 난수가 아니라 입력으로 가른다.
# 이 글자는 프롬프트(모델용)에서 오므로 대본 번역에 흔들리지 않는다.
_REWORK_MARK = "반려"


def _schema_name(req: GenerateRequest) -> str | None:
    m = _TITLE.search(req.system)
    return m.group(1) if m else None


def _j(obj: dict) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"


def _requirement(req: GenerateRequest) -> str:
    text = req.last_user_text
    m = re.search(r"# 의뢰인 요구사항\n(.+)", text)
    line = (m.group(1) if m else text).strip().splitlines()[0]
    return line[:80]


# ── 대본 문장 ───────────────────────────────────────────────────────
# 키는 영어로 둔다 — 한국어 키를 쓰면 이 표를 읽는 사람이 한국어를 알아야
# 한다. 없는 언어는 한국어로 떨어뜨린다(표가 비어 화면이 비는 것보다 낫다).
_SAY: dict[str, dict[str, str]] = {
    "plan.msg": {
        "ko": "요구사항을 인수기준 3개와 태스크 3개로 정리했습니다.",
        "en": "I turned the requirement into 3 acceptance criteria and 3 tasks.",
        "ja": "要件を受け入れ基準 3 件とタスク 3 件に整理しました。",
    },
    "ac1": {
        "ko": "add, sub, mul, div 네 함수가 정상 동작한다",
        "en": "add, sub, mul and div all work",
        "ja": "add, sub, mul, div の 4 関数が正しく動作する",
    },
    "ac2": {
        "ko": "0으로 나누면 ValueError를 발생시킨다",
        "en": "dividing by zero raises ValueError",
        "ja": "0 で割ると ValueError を発生させる",
    },
    "ac3": {
        "ko": "README 에 네 함수의 사용법이 적혀 있다",
        "en": "the README documents how to use all four functions",
        "ja": "README に 4 関数の使い方が書かれている",
    },
    "t1.title": {
        "ko": "사칙연산 네 함수 구현", "en": "Implement the four operations",
        "ja": "四則演算 4 関数の実装",
    },
    "t1.done": {
        "ko": "네 함수를 import 할 수 있고 div(1,0)이 ValueError를 낸다",
        "en": "all four functions import and div(1,0) raises ValueError",
        "ja": "4 関数が import でき、div(1,0) が ValueError を出す",
    },
    "t2.title": {"ko": "사용법 문서", "en": "Usage documentation",
                 "ja": "使い方のドキュメント"},
    "t2.done": {
        "ko": "네 함수의 시그니처와 예시가 문서에 있다",
        "en": "the doc has the signature and an example for each function",
        "ja": "4 関数のシグネチャと例がドキュメントにある",
    },
    "t3.title": {"ko": "결과 화면 명세", "en": "Result screen spec",
                 "ja": "結果画面の仕様"},
    "t3.done": {
        "ko": "비어 있음·불러오는 중·실패 세 상태가 명세되어 있다",
        "en": "the empty, loading and failed states are all specified",
        "ja": "空・読み込み中・失敗の 3 状態が仕様化されている",
    },
    "div.error": {
        "ko": "0으로 나눌 수 없습니다", "en": "cannot divide by zero",
        "ja": "0 で割ることはできません",
    },
    "design.msg": {
        "ko": "결과 화면을 세 상태로 나눠 명세했습니다.",
        "en": "I specified the result screen in three states.",
        "ja": "結果画面を 3 つの状態に分けて仕様化しました。",
    },
    "design.title": {"ko": "# 결과 화면", "en": "# Result screen",
                     "ja": "# 結果画面"},
    "design.tokens": {
        "ko": "- 여백 16px · 본문 #111827 · 강조 #2563EB",
        "en": "- padding 16px · text #111827 · accent #2563EB",
        "ja": "- 余白 16px · 本文 #111827 · 強調 #2563EB",
    },
    "design.states": {"ko": "## 상태", "en": "## States", "ja": "## 状態"},
    "design.empty": {
        "ko": "1. 비어 있음 — '계산할 식을 입력하세요'",
        "en": "1. Empty — \"Enter an expression to calculate\"",
        "ja": "1. 空 — 「計算する式を入力してください」",
    },
    "design.loading": {
        "ko": "2. 불러오는 중 — 버튼 비활성 + 회전 표시",
        "en": "2. Loading — button disabled + spinner",
        "ja": "2. 読み込み中 — ボタン無効 + スピナー",
    },
    "design.failed": {
        "ko": "3. 실패 — 붉은 배너(#DC2626)에 오류 문장 그대로",
        "en": "3. Failed — red banner (#DC2626) with the error text verbatim",
        "ja": "3. 失敗 — 赤いバナー(#DC2626)にエラー文をそのまま",
    },
    "design.summary": {
        "ko": "결과 화면의 세 상태를 값으로 명세했다.",
        "en": "Specified the three states of the result screen with values.",
        "ja": "結果画面の 3 状態を値で仕様化した。",
    },
    "design.check": {
        "ko": "상태 3개를 모두 적었다. 실제 구현과 대조하지는 못했다.",
        "en": "Wrote all three states. Did not check them against the "
              "implementation.",
        "ja": "3 状態すべてを書いた。実装との照合はできていない。",
    },
    "docs.msg": {
        "ko": "네 함수의 사용법을 예시와 함께 적었습니다.",
        "en": "I documented all four functions with examples.",
        "ja": "4 関数の使い方を例とともに書きました。",
    },
    "docs.lead": {
        "ko": "사칙연산 네 함수.", "en": "The four arithmetic functions.",
        "ja": "四則演算の 4 関数。",
    },
    "docs.note": {
        "ko": "`div` 는 두 번째 인자가 0이면 `ValueError` 를 냅니다.",
        "en": "`div` raises `ValueError` when the second argument is 0.",
        "ja": "`div` は第 2 引数が 0 のとき `ValueError` を出します。",
    },
    "docs.summary": {
        "ko": "네 함수의 시그니처와 예시를 문서에 적었다.",
        "en": "Wrote the signature and an example for each function.",
        "ja": "4 関数のシグネチャと例をドキュメントに書いた。",
    },
    "docs.check": {
        "ko": "코드를 읽고 썼다. 실행해 보지는 않았다.",
        "en": "Wrote it from reading the code. Did not run it.",
        "ja": "コードを読んで書いた。実行はしていない。",
    },
    "code.fixed": {
        "ko": "반려 사유대로 div 에 0 검사를 넣었습니다.",
        "en": "As the rejection asked, I added a zero check to div.",
        "ja": "差し戻しの理由どおり、div に 0 チェックを入れました。",
    },
    "code.msg": {
        "ko": "사칙연산 네 개 구현했습니다. 확인 부탁드립니다.",
        "en": "I implemented the four operations. Please review.",
        "ja": "四則演算を 4 つ実装しました。確認をお願いします。",
    },
    "code.fixedSummary": {
        "ko": "div 가 0 을 받으면 ValueError 를 내도록 고쳤다.",
        "en": "Fixed div to raise ValueError when it gets 0.",
        "ja": "div が 0 を受け取ったら ValueError を出すよう直した。",
    },
    "code.summary": {
        "ko": "add·sub·mul·div 를 구현했다.",
        "en": "Implemented add, sub, mul and div.",
        "ja": "add・sub・mul・div を実装した。",
    },
    "code.fixedCheck": {
        "ko": "0 나눗셈을 확인했다.", "en": "Checked division by zero.",
        "ja": "0 除算を確認した。",
    },
    "code.check": {
        "ko": "네 함수의 기본 동작만 확인했다. 예외 경로는 확인하지 못했다.",
        "en": "Checked only the happy path of the four functions, not the "
              "error paths.",
        "ja": "4 関数の基本動作のみ確認した。例外経路は確認できていない。",
    },
    "tests.msg": {
        "ko": "인수기준 3개 중 2개를 테스트로 묶었습니다. ac3 은 사람이 봐야 합니다.",
        "en": "I covered 2 of the 3 acceptance criteria with tests. ac3 needs "
              "a human.",
        "ja": "受け入れ基準 3 件のうち 2 件をテストにしました。ac3 は人が見る必要があります。",
    },
    "verdict.failMsg": {
        "ko": "내가 쓴 테스트가 실패합니다. div 가 0 을 그대로 나눕니다 — ac2 위반이라 반려합니다.",
        "en": "The test I wrote fails. div divides by zero as-is — that "
              "violates ac2, so I am rejecting it.",
        "ja": "私が書いたテストが失敗します。div が 0 をそのまま割っています — ac2 違反のため差し戻します。",
    },
    "verdict.issue": {
        "ko": "0 나눗셈 미처리", "en": "division by zero not handled",
        "ja": "0 除算が未処理",
    },
    "verdict.why": {
        "ko": "ac2 는 ValueError 를 요구하는데 ZeroDivisionError 가 난다",
        "en": "ac2 requires ValueError but ZeroDivisionError is raised",
        "ja": "ac2 は ValueError を要求しているが ZeroDivisionError が出る",
    },
    "verdict.fix": {
        "ko": "div 에서 b == 0 이면 ValueError 를 발생시킬 것",
        "en": "raise ValueError in div when b == 0",
        "ja": "div で b == 0 のとき ValueError を発生させること",
    },
    "verdict.passMsg": {
        "ko": "테스트가 전부 통과하고 코드도 인수기준과 일치합니다. 통과.",
        "en": "All tests pass and the code matches the acceptance criteria. "
              "Pass.",
        "ja": "テストはすべて通り、コードも受け入れ基準と一致します。合格。",
    },
    "final.msg": {
        "ko": "인수기준 3개 전부 충족했습니다. 납품 가능합니다.",
        "en": "All three acceptance criteria are met. Ready to hand over.",
        "ja": "受け入れ基準 3 件すべてを満たしました。納品可能です。",
    },
    "final.summary": {
        "ko": "src/calc.py · docs/README.md · design/screen.md 를 만들었고 테스트가 통과했습니다.",
        "en": "Created src/calc.py, docs/README.md and design/screen.md; the "
              "tests pass.",
        "ja": "src/calc.py · docs/README.md · design/screen.md を作成し、テストが通りました。",
    },
    "route.writer": {
        "ko": "문서 작업이라 작가에게 맡깁니다.",
        "en": "This is documentation work, so the writer takes it.",
        "ja": "ドキュメント作業なのでライターに任せます。",
    },
    "route.designer": {
        "ko": "화면 명세라 디자이너에게 맡깁니다.",
        "en": "This is a screen spec, so the designer takes it.",
        "ja": "画面仕様なのでデザイナーに任せます。",
    },
    "route.developer": {
        "ko": "코드를 써야 하는 일이라 개발자에게 맡깁니다.",
        "en": "This needs code, so the developer takes it.",
        "ja": "コードを書く仕事なので開発者に任せます。",
    },
    "plain.ack": {
        "ko": "[MOCK] 요청을 확인했습니다 — \"{what}\"",
        "en": "[MOCK] Got the request — \"{what}\"",
        "ja": "[MOCK] 依頼を確認しました — 「{what}」",
    },
    "plain.note": {
        "ko": "실제 모델이 아니라 Mock 제공자가 만든 답입니다. 설정에서 API 키를 "
              "등록하면 실제 직원이 답합니다.",
        "en": "This answer came from the Mock provider, not a real model. "
              "Register API keys in settings and real employees will answer.",
        "ja": "実際のモデルではなく Mock プロバイダーが作った回答です。設定で "
              "API キーを登録すると実際の社員が答えます。",
    },
    "mock.tail": {
        "ko": "(이 응답은 Mock 제공자가 만든 것입니다. 실제 모델이 아닙니다.)",
        "en": "(This response came from the Mock provider, not a real model.)",
        "ja": "(この応答は Mock プロバイダーが作ったものです。実際のモデルではありません。)",
    },
}


def _s(key: str, **vars: object) -> str:
    row = _SAY[key]
    out = row.get(lang.current()) or row["ko"]
    for k, v in vars.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ── 각 스키마의 대본 ────────────────────────────────────────────────
def _plan(req: GenerateRequest) -> dict:
    return {
        "message_to_team": _s("plan.msg"),
        "project_name": "mock-project",
        "acceptance_criteria": [
            {"id": "ac1", "text": _s("ac1")},
            {"id": "ac2", "text": _s("ac2")},
            {"id": "ac3", "text": _s("ac3")},
        ],
        "tasks": [
            {"id": "t1", "title": _s("t1.title"), "assignee": "developer",
             "deps": [], "files": ["src/calc.py"], "covers": ["ac1", "ac2"],
             "done_when": _s("t1.done")},
            {"id": "t2", "title": _s("t2.title"), "assignee": "writer",
             "deps": ["t1"], "files": ["docs/README.md"], "covers": ["ac3"],
             "done_when": _s("t2.done")},
            {"id": "t3", "title": _s("t3.title"), "assignee": "designer",
             "deps": ["t1"], "files": ["design/screen.md"], "covers": [],
             "done_when": _s("t3.done")},
        ],
    }


_CALC_BAD = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    "def div(a, b):\n    return a / b\n"
)


def _calc_good() -> str:
    """고친 버전. 예외 **문장**만 언어를 따른다 — 코드는 그대로다."""
    return _CALC_BAD.replace(
        "def div(a, b):\n    return a / b\n",
        'def div(a, b):\n    if b == 0:\n'
        f'        raise ValueError("{_s("div.error")}")\n'
        "    return a / b\n")


def _assignee_of(text: str) -> str | None:
    """AUTO 요청문 맨 위의 '맡은 태스크' 블록에서 담당자를 읽는다.

    DAY 24 까지는 요청문 **어디에든** "design/" 이 있으면 디자이너 대본을
    골랐다. 태스크가 한 번에 하나씩 돌 때는 작가가 디자인 파일을 볼 일이
    없어서 우연히 맞았다. 태스크가 동시에 돌자(DAY 25) 디자이너가 먼저 쓴
    `design/screen.md` 가 작가의 요청문 '지금까지의 산출물'에 실렸고, 작가가
    디자이너 대본을 읽어 design/ 에 쓰려다 거부당했다 — 순서에 따라 문서가
    생기기도 하고 안 생기기도 했다.
    """
    head = text.split("# 인수기준", 1)[0]
    if "# 맡은 태스크" not in head:
        return None
    for who in ("designer", "writer", "developer"):
        if f'"assignee": "{who}"' in head:
            return who
    return None


def _work(req: GenerateRequest) -> dict:
    text = req.last_user_text
    fixed = _REWORK_MARK in text
    who = _assignee_of(text)

    if who == "designer" or (who is None and ("designer" in text
                                              or "design/" in text)):
        return {
            "message_to_team": _s("design.msg"),
            "files": [{"path": "design/screen.md", "content": (
                f"{_s('design.title')}\n\n"
                f"{_s('design.tokens')}\n\n"
                f"{_s('design.states')}\n"
                f"{_s('design.empty')}\n"
                f"{_s('design.loading')}\n"
                f"{_s('design.failed')}\n")}],
            "summary": _s("design.summary"),
            "self_check": _s("design.check"),
        }

    if who == "writer" or (who is None and ("writer" in text or "docs/" in text)):
        return {
            "message_to_team": _s("docs.msg"),
            "files": [{"path": "docs/README.md", "content": (
                "# calc\n\n"
                f"{_s('docs.lead')}\n\n"
                "```python\n"
                "from calc import add, sub, mul, div\n\n"
                "add(2, 3)   # 5\n"
                "sub(5, 2)   # 3\n"
                "mul(3, 4)   # 12\n"
                "div(10, 4)  # 2.5\n"
                "```\n\n"
                f"{_s('docs.note')}\n")}],
            "summary": _s("docs.summary"),
            "self_check": _s("docs.check"),
        }

    return {
        "message_to_team": _s("code.fixed") if fixed else _s("code.msg"),
        "files": [{"path": "src/calc.py",
                   "content": _calc_good() if fixed else _CALC_BAD}],
        "summary": (_s("code.fixedSummary") if fixed else _s("code.summary")),
        "self_check": (_s("code.fixedCheck") if fixed else _s("code.check")),
    }


def _tests(req: GenerateRequest) -> dict:
    return {
        "message_to_team": _s("tests.msg"),
        "files": [{"path": "tests/test_calc.py", "covers": ["ac1", "ac2"], "content": (
            "import pytest\n\n"
            "from calc import add, sub, mul, div\n\n\n"
            "def test_basic():\n"
            "    assert add(2, 3) == 5\n"
            "    assert sub(5, 2) == 3\n"
            "    assert mul(3, 4) == 12\n"
            "    assert div(10, 4) == 2.5\n\n\n"
            "def test_div_zero_raises_value_error():\n"
            "    with pytest.raises(ValueError):\n"
            "        div(1, 0)\n")}],
        "uncovered": ["ac3"],
    }


def _verdict(req: GenerateRequest) -> dict:
    text = req.last_user_text
    # 테스트 리포트가 실패로 들어왔거나, 코드에 0 검사가 없으면 반려한다.
    failed = '"ok": false' in text.lower() or (
        "def div" in text and "ValueError" not in text)
    if failed:
        return {
            "message_to_team": _s("verdict.failMsg"),
            "verdict": "fail", "severity": "major",
            "findings": [{"file": "src/calc.py", "issue": _s("verdict.issue"),
                          "why": _s("verdict.why")}],
            "required_fixes": [_s("verdict.fix")],
            "confidence": 0.8,
        }
    return {
        "message_to_team": _s("verdict.passMsg"),
        "verdict": "pass", "severity": "none", "findings": [], "required_fixes": [],
        "confidence": 0.95,
    }


def _final(req: GenerateRequest) -> dict:
    return {
        "message_to_team": _s("final.msg"),
        "summary": _s("final.summary"),
        "met_criteria": ["ac1", "ac2", "ac3"],
        "unmet_criteria": [],
    }


# 요구사항은 **사용자가 쓴 글**이므로 언어를 고를 수 없다. 세 언어의 낱말을
# 모두 본다 — 영어로 "usage docs" 라고 쓴 사람이 개발자에게 배정되면,
# 데모에서 라우팅이 고장 난 것처럼 보인다.
_WRITER_WORDS = ("문서", "글", "카피", "README", "readme", "doc", "docs",
                 "documentation", "copy", "guide", "ドキュメント", "文書")
_DESIGNER_WORDS = ("화면", "디자인", "UI", "배치", "ui", "design", "screen",
                   "layout", "mockup", "画面", "デザイン")


def _routing(req: GenerateRequest) -> dict:
    text = req.last_user_text
    if any(k in text for k in _WRITER_WORDS):
        return {"employee": "writer", "why": _s("route.writer")}
    if any(k in text for k in _DESIGNER_WORDS):
        return {"employee": "designer", "why": _s("route.designer")}
    return {"employee": "developer", "why": _s("route.developer")}


_SCRIPTS = {
    "Plan": _plan,
    "WorkResult": _work,
    "TestSuite": _tests,
    "Verdict": _verdict,
    "FinalReport": _final,
    "Routing": _routing,
}


def responder(req: GenerateRequest) -> str:
    """`MockProvider` 에 꽂는 응답 함수."""
    name = _schema_name(req)
    script = _SCRIPTS.get(name or "")
    if script is None:
        # 구조화 요청이 아니다 — 평문 한마디(§11 MANUAL 직접 지시 등).
        return (_s("plain.ack", what=_requirement(req)) + "\n\n"
                + _s("plain.note"))
    body = _j(script(req))
    # Mock 이 만든 것임이 산출물 밖에서도 보여야 한다. JSON 안에 섞으면
    # 스키마 위반이 되므로 코드펜스 뒤에 붙인다 — 파서는 펜스만 읽는다.
    return f"{body}\n\n{_s('mock.tail')}"
