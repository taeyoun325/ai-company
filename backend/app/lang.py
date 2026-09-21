"""서버 쪽 언어 (DAY 21) — 한국어 · English · 日本語.

## 화면 번역과 무엇이 다른가

화면(`frontend/src/lib/i18n.tsx`)은 자기 글을 자기가 번역하면 된다.
서버는 두 가지를 더 해야 한다:

1. **우리가 보내는 문장.** 오류·거절 사유가 그렇다. 화면이 그대로
   보여주므로, 영어로 쓰는 사람에게 한국어 거절 사유가 가면 그 화면만
   번역이 깨진 것처럼 보인다.
2. **직원이 쓰는 글.** 이건 번역표로 못 한다 — 모델이 **생성**하는
   글이기 때문이다. 프롬프트에서 언어를 정해야 하고, 그러면 산출물
   (문서·주석·커밋 메시지)까지 그 언어로 나온다.

두 번째가 진짜다. 영어 사용자가 한국어 주석이 달린 코드를 받으면
그건 번역 문제가 아니라 **쓸 수 없는 산출물**이다.

## 언어는 요청에서 온다

브라우저가 `Accept-Language` 를 보낸다. 화면에서 고른 언어도 같은
헤더로 실어 보낸다 — 계정에 저장하지 않는 이유는 화면 쪽과 같다
(계정 스키마와 API 가 함께 움직여야 한다).

## 실행 스레드에서는 다시 세운다

컨텍스트 변수는 스레드를 따라가지 않는다. 실행을 시작할 때 언어를
집어서 스레드 안에서 다시 세운다 — `tenant` 와 같은 이유, 같은 방식이다.
"""
from __future__ import annotations

import contextvars

LANGS = ("ko", "en", "ja")
DEFAULT = "ko"

_current: contextvars.ContextVar[str] = contextvars.ContextVar(
    "lang", default=DEFAULT)


def current() -> str:
    return _current.get()


def set(lang: str) -> str:                                     # noqa: A001
    value = lang if lang in LANGS else DEFAULT
    _current.set(value)
    return value


def bind(lang: str):
    """`with lang.bind("en"):` — 블록을 벗어나면 되돌린다."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        token = _current.set(lang if lang in LANGS else DEFAULT)
        try:
            yield
        finally:
            _current.reset(token)

    return _cm()


def from_header(header: str | None) -> str:
    """`Accept-Language: ja,en-US;q=0.9` → "ja".

    q 값은 보지 않는다. 브라우저는 선호 순으로 보내므로 **처음 맞는
    것**을 쓰면 충분하고, q 파싱을 넣으면 그 파서가 또 다른 버그 자리가
    된다.
    """
    if not header:
        return DEFAULT
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return DEFAULT


# ── 우리가 보내는 문장 ──────────────────────────────────────────────
_M: dict[str, dict[str, str]] = {
    "plan.required": {
        "ko": "요금제를 선택해야 시작할 수 있습니다. 요금제 화면에서 하나를 고르세요.",
        "en": "Choose a plan before starting. Pick one on the pricing screen.",
        "ja": "開始するにはプランの選択が必要です。料金画面で選んでください。",
    },
    "byok.missing": {
        "ko": "자체 키 요금제입니다. 설정 화면에 본인 API 키를 등록하세요 — 아직 없는 키: {keys}. 이 요금제에서는 운영자 키로 대신 호출하지 않습니다.",
        "en": "This is the bring-your-own-key plan. Register your own API keys in settings — still missing: {keys}. This plan never falls back to the operator's keys.",
        "ja": "自前キープランです。設定画面でご自身の API キーを登録してください — 未登録: {keys}。このプランでは運営者のキーで代わりに呼び出すことはありません。",
    },
    "credits.short": {
        "ko": "크레딧이 부족합니다 — 이 작업의 최대 예상치 {needed} 크레딧, 잔액 {balance} 크레딧",
        "en": "Not enough credits — this run needs up to {needed}, and you have {balance}.",
        "ja": "クレジットが不足しています — この作業の最大見積もり {needed}、残高 {balance}。",
    },
    "run.concurrent": {
        "ko": "동시 실행 한도({n})에 도달했습니다. 진행 중인 작업이 끝난 뒤에 시작하세요.",
        "en": "You have reached the concurrent run limit ({n}). Start again when a running job finishes.",
        "ja": "同時実行の上限（{n}）に達しました。実行中の作業が終わってから開始してください。",
    },
    # 단계 설명. 화면 한가운데(사무실 탁자)에 뜨므로 번역되지 않으면
    # 눈에 제일 먼저 띈다. 태스크 제목처럼 **사용자가 쓴 글**은 번역하지
    # 않는다 — 그건 그 사람의 문장이다.
    "phase.plan": {
        "ko": "전략가가 계획을 세우는 중",
        "en": "The strategist is planning",
        "ja": "ストラテジストが計画中",
    },
    "phase.write_tests": {
        "ko": "분석가가 인수기준으로 테스트 작성",
        "en": "The analyst is writing tests from the criteria",
        "ja": "アナリストが受け入れ基準からテストを作成",
    },
    "phase.finalize": {
        "ko": "최종 검수",
        "en": "Final review",
        "ja": "最終検収",
    },
    "phase.manual": {
        "ko": "{who} · 직접 지시",
        "en": "{who} · direct instruction",
        "ja": "{who} · 直接指示",
    },
    "phase.review_manual": {
        "ko": "CEO 요청으로 검증",
        "en": "Review requested by the CEO",
        "ja": "CEO の要請で検証",
    },
    "staff.fired": {
        "ko": "{name} 은(는) 지금 채용되어 있지 않습니다. 사무실에서 다시 채용하세요.",
        "en": "{name} is not currently hired. Hire them again from the office screen.",
        "ja": "{name} は現在雇用されていません。オフィス画面で再度雇用してください。",
    },
}


def t(key: str, **vars: object) -> str:
    row = _M.get(key)
    if row is None:
        return key          # 표에 없으면 키를 그대로 — 조용히 비우지 않는다
    out = row.get(current()) or row[DEFAULT]
    for k, v in vars.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ── 직원이 쓰는 글 ──────────────────────────────────────────────────
_WRITE_IN = {
    "ko": "",          # 기본 프롬프트가 이미 한국어다. 덧붙일 말이 없다.
    "en": (
        "\n\n# Language\n"
        "Write everything in English — messages to the team, summaries, "
        "documents, code comments, and identifiers meant for humans. "
        "The CEO reads English. Do not switch to another language even if "
        "the files you are given are written in one."
    ),
    "ja": (
        "\n\n# 言語\n"
        "すべて日本語で書いてください — チームへのメッセージ、要約、"
        "ドキュメント、コードのコメント、人が読む識別子。"
        "CEO は日本語を読みます。渡されたファイルが別の言語でも、"
        "その言語に切り替えないでください。"
    ),
}


def prompt_line() -> str:
    """직원 프롬프트 끝에 붙일 언어 지시.

    한국어에서는 빈 문자열이다 — 프롬프트가 이미 한국어이므로 "한국어로
    쓰세요"를 덧붙이면 토큰만 쓴다. 프롬프트 캐싱(§14)도 이 꼬리가
    고정이어야 잘 맞는다.
    """
    return _WRITE_IN.get(current(), "")
