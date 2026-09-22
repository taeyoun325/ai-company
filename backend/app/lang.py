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
    # ── 작업 로그에 흐르는 문장 (DAY 22) ───────────────────────────
    #
    # 실행 중에 사용자가 제일 오래 보는 칸이다. 여기가 한국어로 남으면
    # 다른 화면을 다 번역해도 "번역이 안 된 제품"으로 읽힌다.
    #
    # 직원이 **생성하는** 글(대사·요약·산출물)은 여기 없다. 그건 표로
    # 옮길 수 없고 프롬프트에서 언어를 정한다(`prompt_line()`).
    "log.mock": {
        "ko": "지금은 **Mock 직원**이 일합니다. 산출물은 실제 AI 의 작업 결과가 아닙니다. 설정에서 API 키를 등록하세요.",
        "en": "**Mock employees** are working. The output is not the work of a real model. Register API keys in settings.",
        "ja": "今は **Mock 社員**が働いています。成果物は実際の AI の作業結果ではありません。設定で API キーを登録してください。",
    },
    "log.attached": {"ko": "첨부: {what}", "en": "Attached: {what}", "ja": "添付: {what}"},
    "log.pytest": {
        "ko": "격리 환경에서 pytest 실행 중…",
        "en": "Running pytest in an isolated environment…",
        "ja": "隔離環境で pytest を実行中…",
    },
    "log.testWritten": {
        "ko": "`{path}` 작성 — 검증 대상 {covers}",
        "en": "`{path}` written — covers {covers}",
        "ja": "`{path}` を作成 — 検証対象 {covers}",
    },
    "log.uncovered": {
        "ko": "자동 검증 불가로 남긴 인수기준: {ids}",
        "en": "Acceptance criteria left unverifiable by tests: {ids}",
        "ja": "自動検証できずに残した受け入れ基準: {ids}",
    },
    "log.unspecified": {"ko": "미지정", "en": "unspecified", "ja": "未指定"},
    "log.denied": {
        "ko": "`{path}` 거부됨 — {why}",
        "en": "`{path}` refused — {why}",
        "ja": "`{path}` 拒否 — {why}",
    },
    "log.testDenied": {
        "ko": "테스트 파일 거부됨 — `{path}` ({why})",
        "en": "Test file refused — `{path}` ({why})",
        "ja": "テストファイル拒否 — `{path}`（{why}）",
    },
    "log.created": {"ko": "`{path}` 새로 만듦", "en": "`{path}` created", "ja": "`{path}` を新規作成"},
    "log.updated": {
        "ko": "`{path}` 수정 ({n}줄)",
        "en": "`{path}` updated ({n} lines)",
        "ja": "`{path}` を修正（{n} 行）",
    },
    "log.stopRequested": {
        "ko": "CEO 가 정지를 요청했습니다 — 현재 단계가 끝나면 멈춥니다.",
        "en": "The CEO asked to stop — we will halt at the end of this step.",
        "ja": "CEO が停止を要請しました — 現在の段階が終わったら止まります。",
    },
    "log.stopped": {"ko": "중단: {why}", "en": "Stopped: {why}", "ja": "中断: {why}"},
    "log.cycle": {
        "ko": "태스크 의존성에 순환이 있습니다 — 남은 것은 정의된 순서대로 처리합니다.",
        "en": "The task graph has a cycle — the rest runs in the order it was defined.",
        "ja": "タスクの依存に循環があります — 残りは定義順に処理します。",
    },
    "log.badAssignee": {
        "ko": "'{task}' 의 담당자 `{who}` 는 맡길 수 없는 직원입니다. {fallback} 에게 넘깁니다.",
        "en": "'{task}' was assigned to `{who}`, who cannot take tasks. Handing it to {fallback}.",
        "ja": "'{task}' の担当 `{who}` は任せられない社員です。{fallback} に回します。",
    },
    "log.reask": {
        "ko": "{who}의 답을 읽지 못해 형식을 고쳐 다시 요청합니다 — {why}",
        "en": "Could not parse {who}'s answer; asking again with the format corrected — {why}",
        "ja": "{who} の回答を読めなかったため、形式を直して再依頼します — {why}",
    },
    "log.retry": {
        "ko": "{who} 호출 실패 — {delay}초 뒤 재시도 ({n}/{max}) · {why}",
        "en": "{who} call failed — retrying in {delay}s ({n}/{max}) · {why}",
        "ja": "{who} の呼び出し失敗 — {delay} 秒後に再試行（{n}/{max}）· {why}",
    },
    "log.fallback": {
        "ko": "{who} 사용 불가 — 다음 제공자로 넘깁니다 ({why})",
        "en": "{who} unavailable — falling back to the next provider ({why})",
        "ja": "{who} は利用不可 — 次のプロバイダに回します（{why}）",
    },
    "log.manualMode": {
        "ko": "MANUAL 모드입니다. 직원을 골라 직접 지시하세요.",
        "en": "This is MANUAL mode. Pick an employee and instruct them directly.",
        "ja": "MANUAL モードです。社員を選んで直接指示してください。",
    },
    "mail.notSent": {
        "ko": "메일이 **발송되지 않았습니다** (SMTP_URL 이 없습니다). 받는 사람 {to} · 제목 {subject}",
        "en": "The mail was **not sent** (no SMTP_URL). To {to} · subject {subject}",
        "ja": "メールは**送信されませんでした**（SMTP_URL がありません）。宛先 {to} · 件名 {subject}",
    },
    # 테스트 결과. 이 한 줄이 검증자의 판정 근거이자 화면의 점수다.
    "test.blocked": {
        "ko": "테스트 실행 차단됨 (샌드박스 아님)",
        "en": "Test run blocked (not sandboxed)",
        "ja": "テスト実行はブロックされました（サンドボックスではありません）",
    },
    "test.none": {"ko": "테스트 없음", "en": "no tests", "ja": "テストなし"},
    "test.timeout": {
        "ko": "타임아웃 ({n}초)", "en": "timed out ({n}s)", "ja": "タイムアウト（{n} 秒）",
    },
    "test.counts": {
        "ko": "{passed}통과·{failed}실패",
        "en": "{passed} passed · {failed} failed",
        "ja": "{passed} 成功 · {failed} 失敗",
    },
    "test.passed": {"ko": "테스트 통과", "en": "Tests passed", "ja": "テスト合格"},
    "test.failed": {
        "ko": "테스트 실패 — {detail}",
        "en": "Tests failed — {detail}",
        "ja": "テスト失敗 — {detail}",
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
    # ── 거절 문장 (DAY 22) ─────────────────────────────────────────
    # 화면은 서버가 준 문장을 **그대로** 찍는다(`useErrorText`). 그래서
    # 여기서 한국어로 쓰면, 화면을 전부 번역해도 무언가 잘못됐을 때만
    # 한국어가 튀어나온다. 하필 사용자가 제일 주의 깊게 읽는 순간이다.
    "err.noProject": {"ko": "없는 프로젝트", "en": "No such project",
                      "ja": "存在しないプロジェクト"},
    "err.noEmployee": {"ko": "없는 직원: {id}", "en": "No such employee: {id}",
                       "ja": "存在しない社員: {id}"},
    "err.emptyRequirement": {
        "ko": "요구사항이 비어 있습니다",
        "en": "The requirement is empty",
        "ja": "要件が空です",
    },
    "err.autoRunning": {
        "ko": "AUTO 실행이 진행 중입니다",
        "en": "An AUTO run is in progress",
        "ja": "AUTO 実行が進行中です",
    },
    "err.runningDelete": {
        "ko": "진행 중인 프로젝트는 지울 수 없습니다",
        "en": "A running project cannot be deleted",
        "ja": "実行中のプロジェクトは削除できません",
    },
    "err.notRunning": {"ko": "진행 중이 아닙니다", "en": "Not running",
                       "ja": "実行中ではありません"},
    "err.unknownProvider": {
        "ko": "알 수 없는 제공자: {name}",
        "en": "Unknown provider: {name}",
        "ja": "不明なプロバイダー: {name}",
    },
    "err.modelNotPriced": {
        "ko": "단가표에 없는 모델입니다: {model}. pricing.json 에 단가를 먼저 "
              "등록하세요 — 단가를 모르면 비용 상한이 걸리지 않습니다.",
        "en": "This model is not in the price table: {model}. Add its price to "
              "pricing.json first — without a price, the cost cap cannot hold.",
        "ja": "単価表にないモデルです: {model}。pricing.json に単価を先に登録して"
              "ください — 単価が分からないとコスト上限が効きません。",
    },
    "err.noKey": {"ko": "등록된 키가 없습니다", "en": "No key is registered",
                  "ja": "登録された鍵がありません"},
    "err.loginRequired": {"ko": "로그인이 필요합니다.", "en": "Sign in first.",
                          "ja": "ログインが必要です。"},
    "err.localNoPassword": {
        "ko": "로컬 사용자는 비밀번호가 없습니다.",
        "en": "Local users do not have a password.",
        "ja": "ローカルユーザーにはパスワードがありません。",
    },
    "err.noAttachment": {"ko": "없는 첨부", "en": "No such attachment",
                         "ja": "存在しない添付"},
    "err.noPreview": {"ko": "미리볼 수 없는 첨부",
                      "en": "This attachment cannot be previewed",
                      "ja": "プレビューできない添付"},
    # ── 직원 소개 (DAY 22) ─────────────────────────────────────────
    # 직함과 설명은 **지금 살아 있는 데이터**다. 실행 기록과 달리 만들어진
    # 시점이 없으므로 보는 사람의 언어로 적는 것이 맞다. 이름은 번역하지
    # 않는다 — 사람 이름은 옮기는 것이 아니라 부르는 것이다.
    "role.strategist": {"ko": "전략가", "en": "Strategist", "ja": "ストラテジスト"},
    "role.developer": {"ko": "개발자", "en": "Developer", "ja": "開発者"},
    "role.analyst": {"ko": "분석가", "en": "Analyst", "ja": "アナリスト"},
    "role.writer": {"ko": "작가", "en": "Writer", "ja": "ライター"},
    "role.designer": {"ko": "디자이너", "en": "Designer", "ja": "デザイナー"},
    "desc.strategist": {
        "ko": "요구사항을 인수기준과 작업 그래프로 바꾼다. 파일은 쓰지 않는다.",
        "en": "Turns the requirement into acceptance criteria and a task graph. Writes no files.",
        "ja": "要件を受け入れ基準とタスクグラフに変換します。ファイルは書きません。",
    },
    "desc.developer": {
        "ko": "코드를 쓴다. src/ 에만 쓸 수 있고 tests/ 는 읽지도 못한다.",
        "en": "Writes code. Can only write to src/, and cannot even read tests/.",
        "ja": "コードを書きます。src/ にのみ書き込め、tests/ は読むこともできません。",
    },
    "desc.analyst": {
        "ko": "다른 회사 모델로 교차검증한다. tests/ 에만 쓰고 코드는 읽기만 한다.",
        "en": "Cross-checks with a model from another company. Writes only to tests/, reads code.",
        "ja": "別会社のモデルで交差検証します。tests/ にのみ書き、コードは読むだけです。",
    },
    "desc.writer": {
        "ko": "문서·카피를 쓴다. docs/ 에만 쓴다.",
        "en": "Writes documentation and copy. Writes only to docs/.",
        "ja": "ドキュメントとコピーを書きます。docs/ にのみ書きます。",
    },
    "desc.designer": {
        "ko": "화면과 비주얼을 명세한다. design/ 에만 쓴다.",
        "en": "Specifies screens and visuals. Writes only to design/.",
        "ja": "画面とビジュアルを仕様化します。design/ にのみ書きます。",
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
