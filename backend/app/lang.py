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


def from_query(value: str | None) -> str | None:
    """주소에 적힌 언어. 아는 언어가 아니면 None — 헤더로 넘어간다.

    EventSource 가 헤더를 못 보내기 때문에 필요하다(app/main.py 의 미들웨어).
    """
    code = (value or "").strip().lower()[:2]
    return code if code in LANGS else None


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
    "cost.dailyExceeded": {
        "ko": "오늘 사용한도(${limit})를 넘습니다 — 이 호출까지 더하면 ${projected}. "
              "자정(UTC)이 지나면 다시 시작할 수 있습니다.",
        "en": "Today's cost cap (${limit}) would be exceeded — adding this call "
              "reaches ${projected}. Try again after UTC midnight.",
        "ja": "本日の利用上限(${limit})を超えます — この呼び出しを加えると "
              "${projected}。UTC 深夜0時以降に再度お試しください。",
    },
    "cost.userExceeded": {
        "ko": "누적 사용한도(${limit})를 넘습니다 — 이 호출까지 더하면 ${projected}. "
              "운영자에게 문의하세요.",
        "en": "Lifetime cost cap (${limit}) would be exceeded — adding this call "
              "reaches ${projected}. Contact the operator.",
        "ja": "累計利用上限(${limit})を超えます — この呼び出しを加えると "
              "${projected}。運営者にお問い合わせください。",
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
    "log.resumed": {
        "ko": "멈췄던 지점에서 이어갑니다 — 이미 끝난 태스크 {n}개는 다시 "
              "하지 않습니다.",
        "en": "Resuming from where it stopped — the {n} task(s) already done "
              "won't be redone.",
        "ja": "止まったところから再開します — すでに完了したタスク{n}件は"
              "やり直しません。",
    },
    "resume.notStopped": {
        "ko": "멈춘 실행만 재개할 수 있습니다 — 지금 상태: {status}.",
        "en": "Only a stopped run can be resumed — current status: {status}.",
        "ja": "停止した実行のみ再開できます — 現在の状態: {status}。",
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
    "log.badResponse": {
        "ko": "{who} 응답 처리 실패 — 재시도 ({why})",
        "en": "Could not handle {who}'s response — retrying ({why})",
        "ja": "{who} の応答処理に失敗 — 再試行（{why}）",
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
    # 메일 제목·본문 (DAY 22). 받는 사람이 우리 화면을 안 보고 읽는
    # 유일한 글이다 — 여기가 한국어면 영어로 가입한 사람은 재설정 메일을
    # 받고도 무엇을 하라는 건지 모른다. 요청 언어를 그대로 따른다.
    "mail.resetSubject": {
        "ko": "[AI COMPANY] 비밀번호 재설정",
        "en": "[AI COMPANY] Reset your password",
        "ja": "[AI COMPANY] パスワードの再設定",
    },
    "mail.resetBody": {
        "ko": "아래 주소에서 새 비밀번호를 정하세요. 30분 뒤에 만료됩니다."
              + "\n\n" + "{link}" + "\n\n"
              + "본인이 요청하지 않았다면 이 메일을 무시하세요. 요청만으로는 "
                "비밀번호가 바뀌지 않습니다." + "\n",
        "en": "Set a new password at the link below. It expires in 30 minutes."
              + "\n\n" + "{link}" + "\n\n"
              + "If you did not ask for this, ignore this mail. The request "
                "alone does not change your password." + "\n",
        "ja": "以下のリンクで新しいパスワードを設定してください。30 分後に期限が切れます。"
              + "\n\n" + "{link}" + "\n\n"
              + "心当たりがない場合はこのメールを無視してください。リクエストだけでは"
                "パスワードは変わりません。" + "\n",
    },
    "mail.verifySubject": {
        "ko": "[AI COMPANY] 이메일 확인",
        "en": "[AI COMPANY] Confirm your email",
        "ja": "[AI COMPANY] メールアドレスの確認",
    },
    "mail.verifyBody": {
        "ko": "아래 주소를 열면 이 이메일 주소가 확인됩니다. 24시간 뒤에 만료됩니다."
              + "\n\n" + "{link}" + "\n",
        "en": "Open the link below to confirm this email address. It expires "
              "in 24 hours." + "\n\n" + "{link}" + "\n",
        "ja": "以下のリンクを開くと、このメールアドレスが確認されます。24 時間後に"
              "期限が切れます。" + "\n\n" + "{link}" + "\n",
    },
    "who.localUser": {"ko": "로컬 사용자", "en": "Local user",
                      "ja": "ローカルユーザー"},
    "fs.beforeOverwrite": {
        "ko": "{who} 덮어쓰기 직전",
        "en": "just before {who} overwrote it",
        "ja": "{who} が上書きする直前",
    },
    "log.badAssigneeFallback": {
        "ko": "{who} 는 맡길 수 없는 직원이라 기본 담당자로 배정했습니다.",
        "en": "{who} cannot take tasks, so the default assignee took it.",
        "ja": "{who} は任せられない社員のため、既定の担当者に割り当てました。",
    },
    "stop.employeeFailed": {
        "ko": "직원 호출 실패 — {why}",
        "en": "The employee call failed — {why}",
        "ja": "社員の呼び出しに失敗 — {why}",
    },
    "mail.logOnly": {
        "ko": "SMTP_URL 이 설정되지 않아 로그로만 남겼습니다",
        "en": "No SMTP_URL is set, so this was only written to the log",
        "ja": "SMTP_URL が設定されていないため、ログにのみ残しました",
    },
    "mail.noTls": {
        "ko": "{host} 가 STARTTLS 를 제공하지 않습니다 — 평문으로 보내지 "
              "않습니다. smtps:// 를 쓰거나 TLS 를 켜세요.",
        "en": "{host} does not offer STARTTLS — we will not send in the "
              "clear. Use smtps:// or turn TLS on.",
        "ja": "{host} は STARTTLS を提供していません — 平文では送信しません。"
              "smtps:// を使うか TLS を有効にしてください。",
    },
    "mail.noPlainLogin": {
        "ko": "TLS 없이 SMTP 로그인을 하지 않습니다. 계정이 필요 없는 로컬 "
              "릴레이라면 SMTP_URL 에서 계정을 빼세요.",
        "en": "We do not log in to SMTP without TLS. If the local relay needs "
              "no account, remove the credentials from SMTP_URL.",
        "ja": "TLS なしで SMTP ログインは行いません。アカウント不要のローカル"
              "リレーなら SMTP_URL から認証情報を外してください。",
    },
    "mail.alreadyVerified": {
        "ko": "이미 확인된 주소입니다",
        "en": "That address is already verified",
        "ja": "すでに確認済みのアドレスです",
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
    # 채팅로그 헤드라인 (DAY 24). 단계가 바뀔 때만 한 줄 — 모델을 불러
    # 매 줄을 요약하면 비용이 끝없이 나간다(narrator.py 와 같은 규칙).
    "bus.handoff": {
        "ko": "{frm} 완료 — {to}에게 전달",
        "en": "{frm} done — handed to {to}",
        "ja": "{frm} 完了 — {to} に引き継ぎ",
    },
    "bus.started": {
        "ko": "{who} 시작",
        "en": "{who} started",
        "ja": "{who} 開始",
    },
    # ── 제공자·키 (DAY 22) ─────────────────────────────────────────
    # 설정 화면이 이 문장을 그대로 보여준다. 키를 넣는 사람은 대개
    # 막혀서 온 사람이고, 막힌 이유가 읽히지 않으면 거기서 끝난다.
    "prov.noKey": {
        "ko": "{label} API 키가 없습니다. 설정에서 등록하세요.",
        "en": "No {label} API key. Add one in settings.",
        "ja": "{label} の API キーがありません。設定で登録してください。",
    },
    "prov.noKeyEnv": {
        "ko": "{label} API 키가 없습니다. 설정 화면에서 등록하거나 {env} "
              "환경변수를 설정하세요.",
        "en": "No {label} API key. Add one in settings, or set the {env} "
              "environment variable.",
        "ja": "{label} の API キーがありません。設定画面で登録するか、{env} "
              "環境変数を設定してください。",
    },
    "prov.noPackage": {
        "ko": "{package} 패키지가 없습니다: {detail}",
        "en": "The {package} package is missing: {detail}",
        "ja": "{package} パッケージがありません: {detail}",
    },
    "prov.none": {
        "ko": "쓸 수 있는 제공자가 없습니다: {name}",
        "en": "No usable provider: {name}",
        "ja": "使用できるプロバイダーがありません: {name}",
    },
    # 모델이 답을 안 준 경우. 우리 잘못도 사용자 잘못도 아닐 수 있지만,
    # 무엇이 일어났는지는 읽혀야 한다.
    "prov.refused": {
        "ko": "모델이 요청을 거절했습니다: {detail}",
        "en": "The model refused the request: {detail}",
        "ja": "モデルがリクエストを拒否しました: {detail}",
    },
    "prov.blocked": {
        "ko": "모델이 응답을 차단했습니다: {detail}",
        "en": "The model blocked its response: {detail}",
        "ja": "モデルが応答をブロックしました: {detail}",
    },
    "prov.cutOff": {
        "ko": "응답이 중단됐습니다: {detail}",
        "en": "The response was cut off: {detail}",
        "ja": "応答が中断されました: {detail}",
    },
    "prov.empty": {
        "ko": "빈 응답 (finish_reason={detail})",
        "en": "Empty response (finish_reason={detail})",
        "ja": "空の応答 (finish_reason={detail})",
    },
    "prov.retries": {
        "ko": "재시도 상한에 걸렸습니다.",
        "en": "Retry limit reached.",
        "ja": "再試行の上限に達しました。",
    },
    "prov.allFailed": {
        "ko": "모든 제공자가 실패했습니다.",
        "en": "Every provider failed.",
        "ja": "すべてのプロバイダーが失敗しました。",
    },
    "prov.unknown": {
        "ko": "알 수 없는 제공자: {name}",
        "en": "Unknown provider: {name}",
        "ja": "不明なプロバイダー: {name}",
    },
    "prov.realNoKey": {
        "ko": "PROVIDER_MODE=real 인데 {name} 키가 없습니다. Mock 으로 "
              "대신하지 않습니다.",
        "en": "PROVIDER_MODE=real but there is no {name} key. We do not fall "
              "back to Mock.",
        "ja": "PROVIDER_MODE=real ですが {name} の鍵がありません。Mock で"
              "代用しません。",
    },
    # ── 판정 (DAY 22) ──────────────────────────────────────────────
    # 검증자의 판정 줄 접두어. 이 제품에서 제일 중요한 두 단어이고, 로그의
    # 굵은 글씨로 나간다. (Mock 의 재작업 판단은 프롬프트의 `# 반려 사유`
    # 헤더를 보므로 — 모델용이라 번역하지 않는다 — 이 번역에 흔들리지 않는다.)
    "verdict.pass": {"ko": "통과", "en": "Pass", "ja": "合格"},
    "verdict.fail": {
        "ko": "반려 ({severity})", "en": "Rejected ({severity})",
        "ja": "差し戻し（{severity}）",
    },
    # ── 로그의 말하는 이 (DAY 22) ──────────────────────────────────
    # 직원이 아닌 화자들. "시스템" 은 실행마다 여러 줄을 말하므로, 이 한
    # 단어가 영어 로그에서 제일 자주 보이는 한국어였다.
    "who.system": {"ko": "시스템", "en": "System", "ja": "システム"},
    "who.legacyDev": {
        "ko": "개발자 (Claude)", "en": "Developer (Claude)",
        "ja": "開発者 (Claude)",
    },
    "who.legacyQa": {
        "ko": "검증자 (Gemini)", "en": "Verifier (Gemini)",
        "ja": "検証者 (Gemini)",
    },
    # ── 모델 응답을 읽지 못했을 때 (DAY 22) ────────────────────────
    # 이 문장도 로그에 뜬다 — `log.reask` 의 {why} 자리이고, 세 번 실패하면
    # 화면의 실패 사유가 된다. 모델에게 되돌려주는 수정 요청에도 같은
    # 문장이 들어가므로, 사용자와 모델이 같은 말을 보게 된다.
    "json.noObject": {
        "ko": "응답에 JSON 객체가 없습니다. 객체 하나만 내보내세요.",
        "en": "The response contains no JSON object. Emit exactly one object.",
        "ja": "応答に JSON オブジェクトがありません。オブジェクト一つだけを出力してください。",
    },
    "json.unclosed": {
        "ko": "JSON 객체의 괄호가 닫히지 않았습니다.",
        "en": "The JSON object is not closed.",
        "ja": "JSON オブジェクトの括弧が閉じられていません。",
    },
    "json.syntax": {
        "ko": "JSON 문법 오류: {msg} (줄 {line}, 열 {col})",
        "en": "JSON syntax error: {msg} (line {line}, column {col})",
        "ja": "JSON 構文エラー: {msg} (行 {line}, 列 {col})",
    },
    "json.notObject": {
        "ko": "최상위가 객체가 아닙니다.",
        "en": "The top level is not an object.",
        "ja": "最上位がオブジェクトではありません。",
    },
    "json.schema": {
        "ko": "스키마 위반:\n{errors}",
        "en": "Schema violation:\n{errors}",
        "ja": "スキーマ違反:\n{errors}",
    },
    "json.gaveUp": {
        "ko": "응답을 스키마로 읽지 못했습니다.\n{last}",
        "en": "Could not read the response into the schema.\n{last}",
        "ja": "応答をスキーマとして読み取れませんでした。\n{last}",
    },
    # ── 권한 거절 (DAY 22) ─────────────────────────────────────────
    # 이 문장은 **작업 로그 안으로 들어간다** — `log.denied` 의 {why} 자리다.
    # 틀은 번역돼 있는데 이유가 한국어로 박혀 들어가고 있었다. 직원이
    # 자기 구역 밖에 쓰려 했다는 사실은 이 제품의 핵심 장치라, 그 줄이
    # 읽히지 않으면 무엇을 막았는지 알 수 없다.
    "fs.outside": {
        "ko": "프로젝트 폴더 밖 경로입니다: {path}",
        "en": "That path is outside the project folder: {path}",
        "ja": "プロジェクトフォルダー外のパスです: {path}",
    },
    "fs.notArea": {
        "ko": "{top}/ 은(는) 산출물 구역이 아닙니다. 허용: {allowed}",
        "en": "{top}/ is not a deliverable area. Allowed: {allowed}",
        "ja": "{top}/ は成果物の区域ではありません。許可: {allowed}",
    },
    "fs.noWrite": {
        "ko": "{who}는 {top}/ 에 쓰기 권한이 없습니다. 허용: {allowed}",
        "en": "{who} cannot write to {top}/. Allowed: {allowed}",
        "ja": "{who} は {top}/ への書き込み権限がありません。許可: {allowed}",
    },
    "fs.noRead": {
        "ko": "{who}는 {top}/ 에 읽기 권한이 없습니다. 허용: {allowed}",
        "en": "{who} cannot read {top}/. Allowed: {allowed}",
        "ja": "{who} は {top}/ の読み取り権限がありません。許可: {allowed}",
    },
    # 크기는 KB 로 적는다. MB 로 반올림하면 상한이 작을 때 "0.0MB 인데
    # 0.0MB 까지입니다" 같은 말이 된다 — 실제로 그렇게 나왔다.
    "fs.tooBig": {
        "ko": "파일이 너무 큽니다 ({kb}KB). 한 파일은 {max}KB 까지입니다.",
        "en": "That file is too big ({kb}KB). One file may be up to {max}KB.",
        "ja": "ファイルが大きすぎます ({kb}KB)。1 ファイルは {max}KB までです。",
    },
    "fs.projectFull": {
        "ko": "이 프로젝트의 산출물이 상한({max}KB)에 닿았습니다. 더 쓸 수 "
              "없습니다.",
        "en": "This project's deliverables hit the cap ({max}KB). Nothing more "
              "can be written.",
        "ja": "このプロジェクトの成果物が上限({max}KB)に達しました。これ以上は"
              "書き込めません。",
    },
    "fs.forbiddenName": {
        "ko": "{name} 은(는) 테스트 실행 환경을 바꿀 수 있어 금지된 파일명입니다",
        "en": "{name} is a forbidden filename — it could change the test "
              "environment",
        "ja": "{name} はテスト実行環境を変えられるため禁止されたファイル名です",
    },
    "fs.none": {"ko": "(없음)", "en": "(none)", "ja": "(なし)"},
    # ── 첨부 · 수동 지시 · 요금제 (DAY 22) ─────────────────────────
    # 사용자가 직접 하는 행동이 막히는 자리다 — 파일을 올리고, 직원에게
    # 지시하고, 요금제를 고른다. 막힌 이유가 읽히지 않으면 다시 시도할
    # 방법도 모른다.
    "att.tooBig": {
        "ko": "파일이 너무 큽니다 ({mb}MB). 최대 {max}MB.",
        "en": "That file is too big ({mb}MB). The limit is {max}MB.",
        "ja": "ファイルが大きすぎます ({mb}MB)。最大 {max}MB です。",
    },
    "att.badType": {
        "ko": "지원하지 않는 형식입니다: {type}. 이미지 / PDF / 텍스트만 받습니다.",
        "en": "Unsupported format: {type}. Only images, PDF and text are accepted.",
        "ja": "対応していない形式です: {type}。画像 / PDF / テキストのみ受け付けます。",
    },
    "att.tooMany": {
        "ko": "첨부 총량이 너무 큽니다. 일부를 빼고 다시 시도하세요.",
        "en": "The attachments are too large in total. Remove some and try again.",
        "ja": "添付の合計が大きすぎます。いくつか外して再試行してください。",
    },
    "manual.busy": {
        "ko": "{name}이(가) 아직 작업 중입니다. 끝난 뒤에 지시하세요.",
        "en": "{name} is still working. Wait until they finish.",
        "ja": "{name} はまだ作業中です。終わってから指示してください。",
    },
    "manual.empty": {
        "ko": "지시 내용이 비어 있습니다",
        "en": "The instruction is empty",
        "ja": "指示の内容が空です",
    },
    "manual.cost": {
        "ko": "비용 상한(${limit}) — 이 호출의 최악 비용까지 더하면 "
              "${projected}가 되어 지시를 받지 않습니다.",
        "en": "Cost cap (${limit}) — adding the worst case of this call would "
              "reach ${projected}, so the instruction is refused.",
        "ja": "コスト上限(${limit}) — この呼び出しの最悪コストを加えると "
              "${projected} になるため指示を受け付けません。",
    },
    # ── 로그를 평범한 말로 (DAY 23 · app/narrator.py) ────────────────
    "narrate.empty": {
        "ko": "아직 설명할 로그가 없습니다. 일이 시작되면 다시 눌러주세요.",
        "en": "Nothing to explain yet. Try again once work has started.",
        "ja": "まだ説明できるログがありません。作業が始まったらもう一度お試しください。",
    },
    "plan.unknown": {"ko": "없는 요금제: {name}", "en": "No such plan: {name}",
                     "ja": "存在しない料金プラン: {name}"},
    "plan.notSelectable": {
        "ko": "고를 수 없는 요금제: {name}",
        "en": "That plan cannot be selected: {name}",
        "ja": "選択できない料金プラン: {name}",
    },
    "plan.badTopup": {
        "ko": "0 이하를 충전할 수 없습니다",
        "en": "Cannot top up zero or less",
        "ja": "0 以下をチャージすることはできません",
    },
    # ── 실행이 멈춘 이유 (DAY 22) ──────────────────────────────────
    # 이 문장은 로그와 프로젝트 화면의 "중단 사유"에 남는다. 돈이 걸린
    # 거절이라 사용자가 제일 오래 들여다보는 줄이고, 여기가 한국어면
    # 무엇 때문에 멈췄는지 못 읽은 채 크레딧이 줄어 있다.
    "stop.restarted": {
        "ko": "서버가 다시 시작되어 중단됐습니다. 그때까지 만든 산출물은 "
              "그대로 남아 있습니다.",
        "en": "The server restarted, so this run was stopped. Everything it "
              "made up to then is still here.",
        "ja": "サーバーが再起動したため中断されました。それまでに作った成果物は"
              "そのまま残っています。",
    },
    "stop.byCeo": {"ko": "CEO 가 정지시켰습니다.", "en": "Stopped by the CEO.",
                   "ja": "CEO が停止しました。"},
    "stop.rounds": {
        "ko": "라운드 상한({n}) 도달 — 중단합니다.",
        "en": "Round limit ({n}) reached — stopping.",
        "ja": "ラウンド上限({n})に達しました — 停止します。",
    },
    "stop.cost": {
        "ko": "비용 상한(${limit}) — 다음 호출의 최악 비용까지 더하면 "
              "${projected}가 되어 중단합니다.",
        "en": "Cost cap (${limit}) — adding the worst case of the next call "
              "would reach ${projected}, so we stop here.",
        "ja": "コスト上限(${limit}) — 次の呼び出しの最悪コストを加えると "
              "${projected} になるため停止します。",
    },
    "stop.credits": {
        "ko": "크레딧이 부족합니다 — 잔액 {left} 크레딧으로는 다음 작업을 "
              "시작할 수 없습니다.",
        "en": "Not enough credits — {left} left is not enough to start the "
              "next step.",
        "ja": "クレジットが不足しています — 残高 {left} では次の作業を"
              "開始できません。",
    },
    "stop.noTasks": {
        "ko": "계획에 태스크가 하나도 없습니다 — 진행할 수 없습니다.",
        "en": "The plan has no tasks — cannot continue.",
        "ja": "計画にタスクが一つもありません — 続行できません。",
    },
    "stop.replans": {
        "ko": "재기획 상한({n}) 도달 — '{task}' 에서 진전이 없습니다.",
        "en": "Replan limit ({n}) reached — no progress on '{task}'.",
        "ja": "再計画の上限({n})に達しました — '{task}' で進展がありません。",
    },
    "log.rollback": {
        "ko": "'{task}' 를 {n}회 반려 끝에 포기합니다 — 이 태스크가 건드린 "
              "{files} 을(를) 시작 전 상태로 되돌립니다.",
        "en": "Giving up on '{task}' after {n} rejections — reverting "
              "{files} to how they were before this task started.",
        "ja": "'{task}' を{n}回の反려の末に断念します — このタスクが触れた "
              "{files} を開始前の状態に戻します。",
    },
    # ── 가입·로그인 (DAY 22) ───────────────────────────────────────
    # 제품에서 **제일 먼저** 보는 화면이다. 여기가 한국어면 영어로 쓰는
    # 사람은 계정을 만들다 막히고, 막힌 이유도 못 읽는다.
    "auth.rateLimited": {
        "ko": "시도가 너무 많습니다. {n}분 뒤에 다시 하세요.",
        "en": "Too many attempts. Try again in {n} minutes.",
        "ja": "試行回数が多すぎます。{n} 分後にもう一度お試しください。",
    },
    "auth.badEmail": {
        "ko": "이메일 주소 형식이 아닙니다.",
        "en": "That is not a valid email address.",
        "ja": "メールアドレスの形式ではありません。",
    },
    "auth.longEmail": {
        "ko": "이메일 주소가 너무 깁니다.",
        "en": "That email address is too long.",
        "ja": "メールアドレスが長すぎます。",
    },
    "auth.taken": {
        "ko": "이미 가입된 이메일입니다.",
        "en": "That email is already registered.",
        "ja": "すでに登録されているメールアドレスです。",
    },
    # 로그인 실패는 **어느 쪽이 틀렸는지 알려주지 않는다.** 알려주면
    # 가입된 이메일 목록을 만들 수 있다.
    "auth.badLogin": {
        "ko": "이메일 또는 비밀번호가 올바르지 않습니다.",
        "en": "Email or password is incorrect.",
        "ja": "メールアドレスまたはパスワードが正しくありません。",
    },
    "auth.noAccount": {
        "ko": "계정을 찾을 수 없습니다.",
        "en": "Account not found.",
        "ja": "アカウントが見つかりません。",
    },
    "auth.wrongCurrent": {
        "ko": "현재 비밀번호가 올바르지 않습니다.",
        "en": "The current password is incorrect.",
        "ja": "現在のパスワードが正しくありません。",
    },
    "auth.deadLink": {
        "ko": "링크가 만료됐거나 이미 사용됐습니다. 다시 요청하세요.",
        "en": "That link has expired or was already used. Request a new one.",
        "ja": "リンクの有効期限が切れたか、すでに使用されています。再度リクエストしてください。",
    },
    # 비밀번호 규칙. 이유를 **한 번에 전부** 돌려준다(passwords.problems).
    "pw.short": {
        "ko": "{n}자 이상이어야 합니다.",
        "en": "Must be at least {n} characters.",
        "ja": "{n} 文字以上にしてください。",
    },
    "pw.long": {
        "ko": "200자를 넘을 수 없습니다.",
        "en": "Cannot be longer than 200 characters.",
        "ja": "200 文字を超えることはできません。",
    },
    "pw.common": {
        "ko": "너무 흔한 비밀번호입니다.",
        "en": "That password is too common.",
        "ja": "よく使われすぎているパスワードです。",
    },
    "pw.hasEmail": {
        "ko": "이메일 주소가 그대로 들어 있습니다.",
        "en": "It contains your email address.",
        "ja": "メールアドレスがそのまま含まれています。",
    },
    "pw.spaces": {
        "ko": "앞뒤 공백은 넣을 수 없습니다.",
        "en": "Leading or trailing spaces are not allowed.",
        "ja": "前後の空白は使用できません。",
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
    # ── 승인 게이트 (DAY 25 · HITL) ────────────────────────────────
    "stop.gate": {
        "ko": "CEO 가 승인 단계에서 실행을 멈췄습니다.",
        "en": "The CEO stopped the run at an approval step.",
        "ja": "CEO が承認ステップで実行を停止しました。",
    },
    "phase.revise": {
        "ko": "CEO 의견으로 계획 수정",
        "en": "Revising the plan with the CEO's comments",
        "ja": "CEO の意見で計画を修正",
    },
    "log.parked": {
        "ko": "대표님의 승인을 기다립니다 (대기 {n}건). 할 수 있는 일은 다 했고, "
              "결정이 오면 이어서 진행합니다 — 기다리는 동안 좌석은 쓰지 않습니다.",
        "en": "Waiting for the CEO's approval ({n} pending). Everything that "
              "could run has run; it continues once you decide — no seat is "
              "used while waiting.",
        "ja": "CEO の承認を待っています（{n}件）。できることはすべて終わり、"
              "決定が来たら続けます — 待機中は枠を使いません。",
    },
    "log.gateOpen": {
        "ko": "승인이 필요합니다 — {gate}: {title}",
        "en": "Approval needed — {gate}: {title}",
        "ja": "承認が必要です — {gate}: {title}",
    },
    "gate.name.plan": {"ko": "계획", "en": "Plan", "ja": "計画"},
    "gate.name.task": {"ko": "태스크", "en": "Task", "ja": "タスク"},
    "log.gate.approved": {
        "ko": "승인: {title}", "en": "Approved: {title}", "ja": "承認: {title}",
    },
    "log.gate.rejected": {
        "ko": "반려: {title}", "en": "Sent back: {title}", "ja": "差し戻し: {title}",
    },
    "log.gate.stopped": {
        "ko": "정지: {title}", "en": "Stopped: {title}", "ja": "停止: {title}",
    },
    "gate.unknown": {
        "ko": "모르는 승인 단계입니다: {gate} (가능한 값: {allowed}, task:<직원>)",
        "en": "Unknown approval step: {gate} (allowed: {allowed}, task:<employee>)",
        "ja": "不明な承認ステップです: {gate}（可能な値: {allowed}, task:<社員>）",
    },
    "gate.badEmployee": {
        "ko": "{who} 에게는 태스크가 배정되지 않아 이 승인 단계는 영영 걸리지 않습니다.",
        "en": "{who} is never assigned tasks, so this approval step would never trigger.",
        "ja": "{who} にはタスクが割り当てられないため、この承認ステップは発動しません。",
    },
    "gate.badDecision": {
        "ko": "결정은 {allowed} 중 하나여야 합니다.",
        "en": "The decision must be one of: {allowed}.",
        "ja": "決定は {allowed} のいずれかである必要があります。",
    },
    "gate.needComment": {
        "ko": "반려하려면 무엇을 고칠지 적어주세요 — 사유 없는 반려는 같은 결과를 한 번 더 삽니다.",
        "en": "Say what to fix when sending back — a rejection without a reason buys the same result again.",
        "ja": "差し戻す場合は直すべき点を書いてください — 理由のない差し戻しは同じ結果をもう一度買うことになります。",
    },
    "gate.alreadyDecided": {
        "ko": "이미 결정된 승인입니다 ({status}).",
        "en": "This approval was already decided ({status}).",
        "ja": "この承認はすでに決定済みです（{status}）。",
    },
    "gate.notFound": {
        "ko": "없는 승인 요청입니다.",
        "en": "No such approval request.",
        "ja": "その承認リクエストはありません。",
    },
    # ── 프로젝트별 권한 (DAY 25) ───────────────────────────────────
    "perm.badShape": {
        "ko": "{who} 의 권한 값({what})은 폴더 이름 목록이어야 합니다.",
        "en": "Permissions for {who} ({what}) must be a list of folder names.",
        "ja": "{who} の権限（{what}）はフォルダ名のリストである必要があります。",
    },
    "perm.unknownArea": {
        "ko": "모르는 구역입니다: {area} (가능한 값: {allowed})",
        "en": "Unknown area: {area} (allowed: {allowed})",
        "ja": "不明な領域です: {area}（可能な値: {allowed}）",
    },
    "perm.unknownEmployee": {
        "ko": "없는 직원입니다: {id}",
        "en": "No such employee: {id}",
        "ja": "その社員はいません: {id}",
    },
    "perm.floorTestsWrite": {
        "ko": "{who} 에게 tests/ 쓰기는 줄 수 없습니다 — 구현자가 판정 기준을 고칠 수 "
              "있으면 '통과'가 아무것도 보증하지 않습니다.",
        "en": "{who} cannot be given write access to tests/ — if an implementer "
              "can edit the judge, a 'pass' guarantees nothing.",
        "ja": "{who} に tests/ の書き込み権限は与えられません — 実装者が判定基準を"
              "変更できると「合格」は何も保証しません。",
    },
    "perm.floorVerifierWrites": {
        "ko": "검증자는 tests/ 외에는 쓸 수 없습니다 — 자기가 쓴 것을 자기가 검증하게 됩니다.",
        "en": "The verifier can only write to tests/ — otherwise it would verify its own work.",
        "ja": "検証者は tests/ 以外に書けません — 自分の成果物を自分で検証することになります。",
    },
    "perm.floorVerifierReads": {
        "ko": "검증자의 읽기 권한은 줄일 수 없습니다 — 못 보는 것을 검증하라는 것은 지어내라는 것입니다.",
        "en": "The verifier's read access cannot be reduced — verifying what it cannot see means making it up.",
        "ja": "検証者の読み取り権限は減らせません — 見えないものを検証させるのは、でっち上げさせることです。",
    },
    "perm.floorPlannerWrites": {
        "ko": "전략가는 파일을 쓰지 않습니다 — 계획에는 파일 칸이 없어 쓸 곳 없는 권한이 됩니다.",
        "en": "The strategist does not write files — its plan has no file slot, so the permission would do nothing.",
        "ja": "戦略担当はファイルを書きません — 計画にファイル欄がないため、使い道のない権限になります。",
    },
    "perm.riskNeedsAck": {
        "ko": "구현자가 tests/ 를 읽으면 테스트에 맞춰 짤 수 있어 교차검증이 약해집니다. "
              "그래도 켜려면 위험을 확인해 주세요.",
        "en": "Letting an implementer read tests/ lets it code to the tests, which "
              "weakens cross-checking. Confirm the risk to turn it on anyway.",
        "ja": "実装者が tests/ を読むとテストに合わせて書けるため、クロスチェックが"
              "弱まります。それでも有効にするにはリスクを確認してください。",
    },
    "err.permsWhileRunning": {
        "ko": "실행 중에는 권한을 바꿀 수 없습니다 — 동시에 도는 태스크끼리 같은 파일을 쓰게 될 수 있습니다. 멈추거나 승인 대기일 때 바꾸세요.",
        "en": "Permissions can't change while the run is active — tasks running in parallel could end up writing the same file. Change them while stopped or awaiting approval.",
        "ja": "実行中は権限を変更できません — 並行して動くタスクが同じファイルを書く恐れがあります。停止中か承認待ちのときに変更してください。",
    },
    # ── 사무실 (DAY 25 · 사규) ─────────────────────────────────────
    "stop.planDiscarded": {
        "ko": "대표가 계획을 폐기했습니다.",
        "en": "The CEO discarded the plan.",
        "ja": "CEO が計画を破棄しました。",
    },
    "log.discarded": {
        "ko": "대표가 '{task}' 를 폐기했습니다 — 계획에서 빼고 건드린 파일({files})을 되돌립니다. 나머지는 계속합니다.",
        "en": "The CEO discarded '{task}' — dropping it from the plan and reverting its files ({files}). The rest continues.",
        "ja": "CEO が「{task}」を破棄しました — 計画から外し、触れたファイル({files})を元に戻します。残りは続行します。",
    },
    "log.gate.held": {"ko": "보류: {title}", "en": "On hold: {title}", "ja": "保留: {title}"},
    "log.gate.discarded": {"ko": "폐기: {title}", "en": "Discarded: {title}", "ja": "破棄: {title}"},
    "office.int.byok": {
        "ko": "내 API 키({label})가 등록되지 않았습니다 — 설정에서 등록해야 시작합니다.",
        "en": "Your own API key ({label}) isn't registered — add it in settings to start.",
        "ja": "自分の API キー({label})が未登録です — 設定で登録すると開始できます。",
    },
    "office.int.mockMode": {
        "ko": "{label} 는 Mock 모드로 묶여 있습니다 — 대본이 대신 답합니다.",
        "en": "{label} is locked to Mock mode — a script answers instead.",
        "ja": "{label} は Mock モードに固定されています — 台本が代わりに答えます。",
    },
    "office.int.noKey": {
        "ko": "{label} 키가 연결되지 않았습니다 — 지금은 Mock 대본이 대신 일합니다.",
        "en": "No {label} key is connected — a Mock script is working in its place.",
        "ja": "{label} のキーが未接続です — 今は Mock 台本が代わりに働いています。",
    },
    "office.int.noSandbox": {
        "ko": "이 배포에서는 생성된 코드를 실행하지 않습니다(격리 환경 없음) — 테스트는 코드 읽기로만 판정합니다.",
        "en": "This deployment doesn't run generated code (no sandbox) — tests are judged by reading the code only.",
        "ja": "このデプロイでは生成コードを実行しません(隔離環境なし) — テストはコードを読むだけで判定します。",
    },
    "office.r.manualBusy": {"ko": "대표 지시를 처리하는 중", "en": "Working on your instruction", "ja": "社長の指示を処理中"},
    "office.r.manualIdle": {"ko": "직접 지시 모드 — 지목해서 시켜 주세요.", "en": "Manual mode — pick me and give an instruction.", "ja": "直接指示モード — 指名して指示してください。"},
    "office.r.away": {"ko": "자리가 비어 있습니다 — 채용되지 않았습니다.", "en": "Desk is empty — not hired.", "ja": "席が空いています — 雇用されていません。"},
    "office.r.held": {"ko": "대표님이 보류한 결재 — {title}", "en": "Held by the CEO — {title}", "ja": "CEO が保留中の決裁 — {title}"},
    "office.r.approval": {"ko": "대표 결재 대기 — {title}", "en": "Waiting for the CEO's approval — {title}", "ja": "CEO の決裁待ち — {title}"},
    "office.r.mockDone": {
        "ko": "Mock 으로 끝낸 일이라 완료로 치지 않습니다 — {label} 미연동",
        "en": "Finished with Mock, so not counted as done — {label} isn't connected",
        "ja": "Mock で終えた仕事なので完了扱いにしません — {label} 未接続",
    },
    "office.r.noRun": {"ko": "지시를 기다립니다.", "en": "Waiting for instructions.", "ja": "指示を待っています。"},
    "office.r.finalDone": {"ko": "최종 검수를 마쳤습니다.", "en": "Final review is done.", "ja": "最終検収を終えました。"},
    "office.r.reviewsDone": {"ko": "교차검증을 마쳤습니다 ({n}).", "en": "Cross-checks are done ({n}).", "ja": "クロスチェックを終えました ({n})。"},
    "office.r.tasksDone": {"ko": "맡은 태스크 {n}개를 마쳤습니다.", "en": "Finished all {n} assigned task(s).", "ja": "担当タスク{n}件を終えました。"},
    "office.r.planDone": {"ko": "계획을 마쳤습니다 — 최종 검수 때 다시 나옵니다.", "en": "The plan is done — back for the final review.", "ja": "計画を終えました — 最終検収で再登場します。"},
    "office.r.waitReview": {"ko": "구현이 끝나면 검토합니다.", "en": "Reviews each task once it's implemented.", "ja": "実装が終わり次第レビューします。"},
    "office.r.stopped": {"ko": "실행이 멈춰 있습니다 — {why}", "en": "The run is stopped — {why}", "ja": "実行が止まっています — {why}"},
    "office.r.parked": {"ko": "대표 결재가 끝나면 이어갑니다.", "en": "Continues once the CEO decides.", "ja": "CEO の決裁が済めば再開します。"},
    "office.r.waitDep": {"ko": "앞 단계 대기 — '{task}' 가 끝나야 시작합니다.", "en": "Waiting on the previous step — starts after '{task}'.", "ja": "前工程待ち — 「{task}」が終わってから始めます。"},
    "office.r.waitTurn": {"ko": "차례 대기 — '{task}'", "en": "Up next — '{task}'", "ja": "順番待ち — 「{task}」"},
    "office.r.waitPlan": {"ko": "{who} 의 계획을 기다립니다.", "en": "Waiting for {who}'s plan.", "ja": "{who} の計画を待っています。"},
    "office.r.noTask": {"ko": "이번 프로젝트에 맡은 일이 없습니다.", "en": "No work assigned in this project.", "ja": "このプロジェクトで担当する仕事はありません。"},
    "office.r.implement": {"ko": "'{task}' 구현 중", "en": "Implementing '{task}'", "ja": "「{task}」を実装中"},
    "office.r.pytest": {"ko": "'{task}' 테스트 실행 중(pytest)", "en": "Running tests for '{task}' (pytest)", "ja": "「{task}」のテスト実行中(pytest)"},
    "office.r.review": {"ko": "'{task}' 교차검증 중", "en": "Cross-checking '{task}'", "ja": "「{task}」をクロスチェック中"},
    "office.r.main.PLAN": {"ko": "요구사항을 인수기준과 태스크로 나누는 중", "en": "Turning the request into criteria and tasks", "ja": "要件を受け入れ基準とタスクに分けています"},
    "office.r.main.REPLAN": {"ko": "막힌 태스크를 다시 계획하는 중", "en": "Re-planning a stuck task", "ja": "詰まったタスクを再計画中"},
    "office.r.main.FINALIZE": {"ko": "인수기준별 최종 검수 중", "en": "Final review against each criterion", "ja": "受け入れ基準ごとに最終検収中"},
    "office.r.main.WRITE_TESTS": {"ko": "구현 전에 테스트를 먼저 쓰는 중", "en": "Writing the tests before any code", "ja": "実装の前にテストを先に書いています"},
    "office.r.waitingModel": {"ko": "모델 응답 {s}초째({model})", "en": "waiting {s}s for the model ({model})", "ja": "モデル応答待ち{s}秒({model})"},
    "office.dept.strategy": {"ko": "기획실", "en": "Strategy", "ja": "企画室"},
    "office.dept.dev": {"ko": "개발팀", "en": "Engineering", "ja": "開発チーム"},
    "office.dept.qa": {"ko": "검증팀", "en": "Verification", "ja": "検証チーム"},
    "office.dept.docs": {"ko": "문서팀", "en": "Docs", "ja": "ドキュメントチーム"},
    "office.dept.design": {"ko": "디자인팀", "en": "Design", "ja": "デザインチーム"},
    "office.dept.etc": {"ko": "기타", "en": "Other", "ja": "その他"},
    "office.state.done": {"ko": "완료", "en": "Done", "ja": "完了"},
    "office.state.working": {"ko": "진행 중", "en": "Working", "ja": "作業中"},
    "office.state.approval": {"ko": "승인 대기", "en": "Needs approval", "ja": "承認待ち"},
    "office.state.integration": {"ko": "연동 대기", "en": "Needs connection", "ja": "連携待ち"},
    "office.state.idle": {"ko": "대기", "en": "Waiting", "ja": "待機"},
    "office.step.arrive": {"ko": "출근", "en": "Clock in", "ja": "出勤"},
    "office.step.plan": {"ko": "기획", "en": "Plan", "ja": "企画"},
    "office.step.plan_gate": {"ko": "계획 승인", "en": "Plan approval", "ja": "計画承認"},
    "office.step.tests": {"ko": "테스트 선작성", "en": "Tests first", "ja": "テスト先行作成"},
    "office.step.implement": {"ko": "구현", "en": "Build", "ja": "実装"},
    "office.step.pytest": {"ko": "테스트 실행", "en": "Run tests", "ja": "テスト実行"},
    "office.step.review": {"ko": "교차검증", "en": "Cross-check", "ja": "クロスチェック"},
    "office.step.task_gate": {"ko": "결과 승인", "en": "Result approval", "ja": "成果承認"},
    "office.step.rework": {"ko": "재작업", "en": "Rework", "ja": "やり直し"},
    "office.step.finalize": {"ko": "최종 검수", "en": "Final review", "ja": "最終検収"},
    "office.step.saved": {"ko": "결과 저장", "en": "Saved", "ja": "成果保存"},
    "office.step.brief": {"ko": "비서실 브리핑", "en": "Briefing", "ja": "秘書室ブリーフィング"},
    "sec.noRun": {
        "ko": "{time} 기준 진행 중인 일이 없습니다. 아래 입력창에서 일을 맡기시면 전원 출근합니다.",
        "en": "As of {time}, nothing is in progress. Hand over some work below and everyone clocks in.",
        "ja": "{time} 時点で進行中の仕事はありません。下の入力欄で仕事を任せると全員出勤します。",
    },
    "sec.status.head": {"ko": "{time} 기준 · {name} · 지금 단계: {step}", "en": "As of {time} · {name} · current step: {step}", "ja": "{time} 時点 · {name} · 現在の段階: {step}"},
    "sec.runStatus.running": {"ko": "진행 중", "en": "running", "ja": "進行中"},
    "sec.runStatus.awaiting": {"ko": "대표 결재 대기", "en": "waiting for your approval", "ja": "CEO 決裁待ち"},
    "sec.runStatus.stopped": {"ko": "중단됨", "en": "stopped", "ja": "中断"},
    "sec.runStatus.done": {"ko": "완료", "en": "done", "ja": "完了"},
    "sec.runStatus.manual": {"ko": "직접 지시 모드", "en": "manual mode", "ja": "直接指示モード"},
    "sec.status.working": {"ko": "진행 중: {who}", "en": "Working: {who}", "ja": "作業中: {who}"},
    "sec.status.progress": {"ko": "진행률: {progress} (전체 {done}/{total})", "en": "Progress: {progress} (overall {done}/{total})", "ja": "進捗: {progress} (全体 {done}/{total})"},
    "sec.status.pending": {"ko": "대표님 결재 {n}건이 기다리고 있습니다.", "en": "{n} decision(s) are waiting for you.", "ja": "CEO の決裁が{n}件待っています。"},
    "sec.status.next": {"ko": "다음 순서: {step}", "en": "Next: {step}", "ja": "次の順番: {step}"},
    "sec.why.approval": {
        "ko": "원인은 하나예요 — 대표님 결재 대기입니다. 회의실에서 {n}명이 기다리고 있어요.\n'{title}' 을 승인만 주시면 바로 {next}로 넘어갑니다.",
        "en": "There's one cause — it's waiting for your approval. {n} people are waiting in the meeting room.\nApprove '{title}' and it moves straight on to {next}.",
        "ja": "原因は一つです — CEO の決裁待ちです。会議室で{n}人が待っています。\n「{title}」を承認いただければすぐ{next}に進みます。",
    },
    "sec.why.held": {
        "ko": "원인은 하나예요 — 대표님이 보류하신 결재입니다('{title}'). 회의실에서 {n}명이 기다리고 있어요.\n결정해 주시면 바로 {next}로 넘어갑니다.",
        "en": "There's one cause — a decision you put on hold ('{title}'). {n} people are waiting in the meeting room.\nDecide and it moves straight on to {next}.",
        "ja": "原因は一つです — CEO が保留中の決裁です(「{title}」)。会議室で{n}人が待っています。\n決めていただければすぐ{next}に進みます。",
    },
    "sec.why.nextPlan": {"ko": "테스트 선작성", "en": "writing the tests", "ja": "テスト先行作成"},
    "sec.why.nextTask": {"ko": "다음 태스크", "en": "the next task", "ja": "次のタスク"},
    "sec.why.more": {"ko": "그 뒤에 결재 {n}건이 더 있습니다.", "en": "{n} more decision(s) are queued after it.", "ja": "その後にさらに{n}件の決裁があります。"},
    "sec.why.alsoIntegration": {"ko": "그 외 연동 대기 {n}건은 외부 연결 문제라 결재와 별개로 막혀 있어요.", "en": "Separately, {n} connection issue(s) are blocking real work regardless of the decision.", "ja": "それとは別に、連携待ち{n}件は外部接続の問題で止まっています。"},
    "sec.why.noRun": {"ko": "진행 중인 일이 없습니다 — 지연 없습니다.", "en": "Nothing is running — no delay.", "ja": "進行中の仕事はありません — 遅延はありません。"},
    "sec.why.stopped": {
        "ko": "멈춰 있습니다 — 사유: {why}\n태스크 {done}/{total} 에서 멈췄고, 재개하면 끝난 것은 다시 하지 않습니다.",
        "en": "It's stopped — reason: {why}\nIt stopped at {done}/{total} tasks; resuming won't redo finished work.",
        "ja": "止まっています — 理由: {why}\nタスク {done}/{total} で止まっており、再開しても終わった分はやり直しません。",
    },
    "sec.why.callOk": {
        "ko": "{dept} {name} — '{task}' 에서 모델 응답을 {s}초째 기다리는 중({model}). 이 직원의 평소 p95 는 {p95}초라 정상 범위입니다. 진행률 {done}/{total}.",
        "en": "{dept} · {name} — waiting {s}s for the model on '{task}' ({model}). Their usual p95 is {p95}s, so this is normal. Progress {done}/{total}.",
        "ja": "{dept} {name} — 「{task}」でモデル応答を{s}秒待っています({model})。普段の p95 は{p95}秒なので正常範囲です。進捗 {done}/{total}。",
    },
    "sec.why.callSlow": {
        "ko": "병목은 {dept} {name} — '{task}' 에서 모델 응답을 {s}초째 기다리는 중({model}). 평소 p95 {p95}초보다 길어 느린 편입니다 — 제공자 쪽 지연일 가능성이 큽니다. 진행률 {done}/{total}.",
        "en": "The bottleneck is {dept} · {name} — waiting {s}s for the model on '{task}' ({model}). That's longer than their usual p95 of {p95}s — most likely a provider-side delay. Progress {done}/{total}.",
        "ja": "ボトルネックは{dept} {name} — 「{task}」でモデル応答を{s}秒待っています({model})。普段の p95 {p95}秒より長く、提供者側の遅延の可能性が高いです。進捗 {done}/{total}。",
    },
    "sec.why.stoppedPending": {
        "ko": "결재 {n}건도 남아 있습니다 — 지금 결정해 두면 재개할 때 그 결정부터 반영합니다.",
        "en": "{n} decision(s) are also pending — decide now and resuming applies them first.",
        "ja": "決裁も{n}件残っています — 今決めておけば、再開時にその決定から反映します。",
    },
    "sec.why.noTask": {"ko": "본 단계", "en": "the main step", "ja": "本工程"},
    "sec.why.working": {"ko": "{dept} {name} — {reason}. 정상 진행 중입니다. 진행률 {done}/{total}.", "en": "{dept} · {name} — {reason}. Running normally. Progress {done}/{total}.", "ja": "{dept} {name} — {reason}。正常に進行中です。進捗 {done}/{total}。"},
    "sec.why.integration": {"ko": "외부 연동 문제입니다 — {what} (영향: {who})", "en": "It's a connection problem — {what} (affects: {who})", "ja": "外部連携の問題です — {what} (影響: {who})"},
    "sec.why.moreIntegration": {"ko": "그 외 연동 대기 {n}건이 더 있습니다.", "en": "{n} more connection issue(s).", "ja": "ほかに連携待ちが{n}件あります。"},
    "sec.why.none": {"ko": "지연 없습니다.", "en": "No delay.", "ja": "遅延はありません。"},
    "sec.whois.state": {"ko": "[{state}] {reason}", "en": "[{state}] {reason}", "ja": "[{state}] {reason}"},
    "sec.whois.tasks": {"ko": "맡은 태스크 {done}/{total} 완료.", "en": "{done}/{total} of my tasks done.", "ja": "担当タスク {done}/{total} 完了。"},
    "sec.whois.usage": {"ko": "이번 프로젝트에서 호출 {n}회 · ${cost} · 평균 {avg}초.", "en": "This project: {n} call(s) · ${cost} · {avg}s on average.", "ja": "このプロジェクトで呼び出し{n}回 · ${cost} · 平均{avg}秒。"},
    "sec.whois.mock": {"ko": "참고로 저는 지금 Mock 입니다 — 제 결과를 실제 작업으로 보시면 안 됩니다.", "en": "Note: I'm running as Mock right now — don't treat my output as real work.", "ja": "なお、今の私は Mock です — 私の結果を実際の作業と見なさないでください。"},
    "sec.meeting.close": {"ko": "보고 끝났습니다. 각자 자리로 돌아갑니다.", "en": "That's everyone. Back to your desks.", "ja": "報告は以上です。各自席に戻ります。"},
    "sec.brief.head": {"ko": "{time} 브리핑 · {name} · {status}", "en": "{time} briefing · {name} · {status}", "ja": "{time} ブリーフィング · {name} · {status}"},
    "sec.brief.tasks": {"ko": "태스크 {done}/{total} · 완성도 {score}%", "en": "Tasks {done}/{total} · completeness {score}%", "ja": "タスク {done}/{total} · 完成度 {score}%"},
    "sec.brief.cost": {"ko": "비용 ${cost} · 걸린 시간 {mins}분", "en": "Cost ${cost} · {mins} min elapsed", "ja": "コスト ${cost} · 所要 {mins}分"},
    "sec.brief.confidence": {"ko": "검증자 평균 확신도 {pct}%", "en": "Verifier's average confidence {pct}%", "ja": "検証者の平均確信度 {pct}%"},
    "sec.brief.pending": {"ko": "결재 {n}건이 대표님을 기다립니다.", "en": "{n} decision(s) are waiting for you.", "ja": "決裁{n}件が CEO を待っています。"},
    "sec.brief.integration": {"ko": "연동 대기: {what}", "en": "Needs connection: {what}", "ja": "連携待ち: {what}"},
    "sec.brief.mock": {"ko": "이번 결과는 Mock 으로 만들어졌습니다 — 실제 AI 의 작업이 아닙니다.", "en": "This result was made with Mock — it isn't real AI work.", "ja": "今回の結果は Mock で作られました — 実際の AI の作業ではありません。"},
    "sec.brief.stopped": {"ko": "중단 사유: {why}", "en": "Stopped because: {why}", "ja": "中断理由: {why}"},
    "sec.brief.done": {"ko": "모든 단계를 마쳤습니다. 산출물은 프로젝트 화면에 있습니다.", "en": "Every step is finished. The output is on the project page.", "ja": "すべての段階を終えました。成果物はプロジェクト画面にあります。"},
    "sec.focus.on": {"ko": "집중 모드 — 전원 자리로 복귀합니다. 자율 행동을 멈춥니다.", "en": "Focus mode — everyone back to their desks. Idle wandering stops.", "ja": "集中モード — 全員席に戻ります。自由行動を止めます。"},
    "sec.focus.off": {"ko": "집중 모드를 풀었습니다. 할 일 없는 직원은 쉬어도 됩니다.", "en": "Focus mode is off. Idle staff may take a break.", "ja": "集中モードを解除しました。手の空いた社員は休憩して構いません。"},
    "sec.approve.none": {"ko": "결재할 건이 없습니다.", "en": "Nothing is waiting for approval.", "ja": "決裁する案件はありません。"},
    "sec.approve.many": {"ko": "결재할 건이 {n}건이라 한 번에 넘기지 않습니다 — 어느 건인지 골라주세요.", "en": "There are {n} decisions, so I won't approve them all at once — pick one.", "ja": "決裁が{n}件あるので一度に通しません — どれか選んでください。"},
    "sec.approve.done": {"ko": "결재 처리했습니다 — '{title}'. 바로 이어서 진행합니다.", "en": "Approved — '{title}'. Continuing right away.", "ja": "決裁しました — 「{title}」。すぐに続けます。"},
    "sec.approve.note": {"ko": "다만 지금은 바로 이어가지 못했습니다: {note}", "en": "It couldn't resume right away, though: {note}", "ja": "ただし、すぐには再開できませんでした: {note}"},
    "sec.help": {
        "ko": "이렇게 물어보세요: '현황 보고' · '왜 늦어져?' · '박도현 뭐해?' · '회의 소집' · '지금 브리핑' · '집중 모드' · '승인할게'",
        "en": "Try: 'status report' · 'why so slow?' · 'what is the developer doing?' · 'call a meeting' · 'brief me' · 'focus mode' · 'approve it'",
        "ja": "こう聞いてください: 「現況報告」·「なぜ遅い?」·「開発者は何してる?」·「会議招集」·「今ブリーフィング」·「集中モード」·「承認します」",
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
