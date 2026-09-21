"use client";

/**
 * 언어 (DAY 20) — 한국어 · English · 日本語.
 *
 * ## 왜 직접 만드나
 *
 * i18n 라이브러리는 네임스페이스·복수형·지연 로딩을 들고 오는데, 지금
 * 필요한 것은 **문자열 표 하나**다. 라이브러리를 넣으면 번역이 아니라
 * 설정을 먼저 배워야 한다.
 *
 * ## 어디까지 번역됐는지 숨기지 않는다
 *
 * DAY 22 에 **화면은 전부 번역했다** — 랜딩·로그인·사무실·프로젝트
 * 목록과 상세·MANUAL·요금제·설정. 요금제 이름처럼 서버가 가진 값도
 * 서버가 언어에 맞춰 보낸다.
 *
 * 남은 것은 **모델이 쓰는 글**이다. 직원의 대사·요약·산출물은 프롬프트
 * 에서 언어를 정하므로(backend/app/lang.py) 그쪽 언어를 따르지만, 이미
 * 만들어진 프로젝트의 기록은 만들 때의 언어로 남는다. 서버 오류 문장도
 * 자주 쓰이는 것만 번역돼 있다.
 *
 * 반쯤 번역된 제품에서 제일 나쁜 것은 어디까지 번역됐는지 모르는
 * 것이므로, 언어를 고르면 그 사실을 한 줄로 알린다.
 *
 * ## 고른 언어는 그 브라우저에만 남는다
 *
 * 계정에 저장하지 않는다. 서버에 붙이려면 계정 스키마와 API 가 함께
 * 움직여야 하고, 그건 번역 자체보다 큰 일이다. 지금은 `localStorage`
 * 하나로 충분하다 — 다만 **읽기가 실패할 수 있다**(사생활 보호 모드).
 * 실패하면 기본값으로 돌아갈 뿐 화면이 깨지지는 않는다.
 */
import { setApiLanguage } from "@/lib/api";
import {
  createContext, useCallback, useContext, useEffect, useMemo,
  useSyncExternalStore, type ReactNode,
} from "react";

export const LANGS = ["ko", "en", "ja"] as const;
export type Lang = (typeof LANGS)[number];

export const LANG_LABEL: Record<Lang, string> = {
  ko: "한국어",
  en: "English",
  ja: "日本語",
};

const STORE_KEY = "ai-company.lang";

type Entry = Record<Lang, string>;

/**
 * 문자열 표.
 *
 * 영어와 일본어를 옮길 때 **어조를 지켰다.** 이 제품의 한국어는 과장하지
 * 않고 못 하는 것을 그대로 적는다. 그걸 영어 마케팅 문체로 옮기면
 * ("Ship production-ready code in minutes!") 같은 제품이 아니게 된다.
 */
const S = {
  // ── 헤더 ──────────────────────────────────────────────────────
  "nav.office": { ko: "사무실", en: "Office", ja: "オフィス" },
  "nav.projects": { ko: "프로젝트", en: "Projects", ja: "プロジェクト" },
  "nav.pricing": { ko: "요금제", en: "Pricing", ja: "料金" },
  "nav.settings": { ko: "설정", en: "Settings", ja: "設定" },
  "nav.language": { ko: "언어", en: "Language", ja: "言語" },
  "footer.note": {
    ko: "당신은 CEO 입니다. 직원에게 직접 지시하거나 AUTO 로 맡기세요.",
    en: "You are the CEO. Direct an employee yourself, or hand it to AUTO.",
    ja: "あなたが CEO です。社員に直接指示するか、AUTO に任せてください。",
  },
  "lang.partial": {
    ko: "",
    en: "Screens are translated. Messages the employees write, and a few server messages, are still Korean.",
    ja: "画面は翻訳済みです。社員が書く文章と一部のサーバーメッセージはまだ韓国語です。",
  },

  // ── 랜딩: 히어로 ──────────────────────────────────────────────
  "hero.badge": {
    ko: "AI 직원 5명 · 제공자 3사 · 교차검증",
    en: "5 AI employees · 3 providers · cross-checked",
    ja: "AI 社員 5 名 · プロバイダ 3 社 · 相互検証",
  },
  "hero.title": {
    ko: "AI 직원들이 실제 회사처럼 협업합니다",
    en: "AI employees that work like a real company",
    ja: "AI 社員が実際の会社のように協働します",
  },
  "hero.body": {
    ko: "당신은 CEO 입니다. 요구사항을 한 줄 적으면 전략가가 일을 쪼개고, 담당자가 만들고, {strong}이 검증합니다. 통과할 때까지 돌고, 상한에 닿으면 멈춥니다.",
    en: "You are the CEO. Write one line of requirements: a strategist breaks it down, the assignee builds it, and {strong} reviews it. It loops until it passes, and stops when it hits a limit.",
    ja: "あなたが CEO です。要件を一行書けば、ストラテジストが分解し、担当者が作り、{strong}が検証します。通るまで回り、上限に達したら止まります。",
  },
  "hero.body.strong": {
    ko: "다른 회사의 모델",
    en: "a model from a different company",
    ja: "別の会社のモデル",
  },
  "hero.figureNote": {
    ko: "이 그림은 코드에 실제로 있는 순서입니다 — 테스트가 먼저 쓰이고, 반려되면 되돌아갑니다.",
    en: "This is the order that actually exists in the code — tests are written first, and rejected work goes back.",
    ja: "この図はコードに実際にある順序です — テストが先に書かれ、差し戻されると戻ります。",
  },
  "hero.cta": { ko: "시작하기", en: "Get started", ja: "はじめる" },

  // ── 랜딩: 흐름 도형 ───────────────────────────────────────────
  "flow.req": { ko: "요구사항", en: "Requirement", ja: "要件" },
  "flow.req.sub": { ko: "CEO 가 한 줄", en: "one line from the CEO", ja: "CEO が一行" },
  "flow.strategist": { ko: "전략가", en: "Strategist", ja: "ストラテジスト" },
  "flow.strategist.sub": {
    ko: "인수기준으로", en: "into acceptance criteria", ja: "受け入れ基準へ",
  },
  "flow.analyst": { ko: "분석가", en: "Analyst", ja: "アナリスト" },
  "flow.analyst.sub": { ko: "테스트를 먼저", en: "tests come first", ja: "テストが先" },
  "flow.developer": { ko: "개발자", en: "Developer", ja: "開発者" },
  "flow.developer.sub": {
    ko: "tests/ 를 못 본다", en: "cannot read tests/", ja: "tests/ を見られない",
  },
  "flow.verifier": { ko: "교차검증", en: "Cross-check", ja: "相互検証" },
  "flow.verifier.sub": {
    ko: "다른 회사 모델", en: "a different company", ja: "別の会社のモデル",
  },
  "flow.out": { ko: "산출물", en: "Deliverable", ja: "成果物" },
  "flow.out.sub": { ko: "파일로 남는다", en: "kept as files", ja: "ファイルとして残る" },
  "flow.chip.test": {
    ko: "테스트가 먼저 쓰인다",
    en: "tests are written first",
    ja: "テストが先に書かれる",
  },
  "flow.chip.reject": { ko: "반려 · 재작업", en: "rejected · rework", ja: "差し戻し · 再作業" },
  "flow.chip.pass": { ko: "통과", en: "passed", ja: "合格" },
  "flow.alt": {
    ko: "요구사항이 전략가를 지나 분석가가 테스트를 먼저 쓰고, 개발자가 구현하고, 다른 회사 모델이 교차검증해 반려되면 되돌아가는 흐름",
    en: "A requirement passes through the strategist, the analyst writes tests first, the developer implements, and a model from a different company cross-checks it; rejected work goes back.",
    ja: "要件がストラテジストを通り、アナリストが先にテストを書き、開発者が実装し、別の会社のモデルが相互検証し、差し戻されると戻る流れ",
  },

  // ── 랜딩: 왜 이렇게 만들었나 ──────────────────────────────────
  "why.title": { ko: "왜 이렇게 만들었나", en: "Why it is built this way", ja: "なぜこう作ったか" },
  "why.order": { ko: "순서는 코드가 정한다", en: "Code decides the order", ja: "順序はコードが決める" },
  "why.order.body": {
    ko: "모델이 고르는 것은 태스크별 담당자 하나뿐이고, 그것도 검사 없이 따르지 않는다",
    en: "The model picks only one thing — the assignee for a task — and even that is checked before it is followed",
    ja: "モデルが選ぶのはタスクごとの担当者ひとつだけで、それも検査なしには従わない",
  },
  "why.tests": { ko: "테스트가 먼저 쓰인다", en: "Tests are written first", ja: "テストが先に書かれる" },
  "why.tests.body": {
    ko: "구현자는 tests/ 를 읽지도 못한다. 읽을 수 있으면 통과시키는 코드를 쓴다",
    en: "The implementer cannot even read tests/. If it could, it would write code that passes them rather than code that meets the criteria",
    ja: "実装者は tests/ を読むことすらできない。読めれば、基準を満たすコードではなくテストを通すコードを書く",
  },
  "why.cross": {
    ko: "검증은 다른 회사 모델", en: "Review comes from another company",
    ja: "検証は別の会社のモデル",
  },
  "why.cross.body": {
    ko: "같은 회사 모델끼리 보면 같은 실수를 함께 놓친다",
    en: "Models from the same company share a training distribution — and miss the same mistakes together",
    ja: "同じ会社のモデル同士で見ると、同じ間違いを一緒に見落とす",
  },
  "why.cost": { ko: "비용은 호출 전에 막는다", en: "Cost is stopped before the call", ja: "コストは呼び出し前に止める" },
  "why.cost.body": {
    ko: "사후 감지는 상한이 아니라 부고다",
    en: "Detecting it afterwards is not a limit — it is an obituary",
    ja: "事後に気づくのは上限ではなく訃報だ",
  },

  // ── 직책 ──────────────────────────────────────────────────────
  // 흐름 도형(flow.*)에는 작가·디자이너가 없다. 직책 이름은 따로 둔다 —
  // 도형의 라벨과 직원 카드의 이름이 같은 키를 쓰면, 도형에 없는 직책이
  // 조용히 키 이름 그대로 화면에 찍힌다.
  "role.strategist": { ko: "전략가", en: "Strategist", ja: "ストラテジスト" },
  "role.developer": { ko: "개발자", en: "Developer", ja: "開発者" },
  "role.analyst": { ko: "분석가", en: "Analyst", ja: "アナリスト" },
  "role.writer": { ko: "작가", en: "Writer", ja: "ライター" },
  "role.designer": { ko: "디자이너", en: "Designer", ja: "デザイナー" },

  // ── 랜딩: 직원 ────────────────────────────────────────────────
  "staff.title": { ko: "직원 다섯", en: "Five employees", ja: "社員 5 名" },
  "staff.note": {
    ko: "구현자와 검증자가 다른 회사의 모델입니다. 대체 사슬도 회사를 건너게 걸었습니다.",
    en: "The implementer and the reviewer are models from different companies. The fallback chain crosses companies too.",
    ja: "実装者と検証者は別の会社のモデルです。フォールバックの連鎖も会社をまたぐようにしています。",
  },
  "staff.strategist": {
    ko: "요구사항을 인수기준과 작업 목록으로 바꾼다",
    en: "Turns requirements into acceptance criteria and a task list",
    ja: "要件を受け入れ基準とタスク一覧に変える",
  },
  "staff.developer": {
    ko: "코드를 쓴다. 테스트는 볼 수 없다",
    en: "Writes code. Cannot see the tests",
    ja: "コードを書く。テストは見られない",
  },
  "staff.analyst": {
    ko: "다른 회사 모델로 교차검증한다",
    en: "Cross-checks with a model from another company",
    ja: "別の会社のモデルで相互検証する",
  },
  "staff.writer": {
    ko: "문서와 카피를 쓴다", en: "Writes docs and copy", ja: "ドキュメントとコピーを書く",
  },
  "staff.designer": {
    ko: "화면과 비주얼을 명세한다", en: "Specifies screens and visuals",
    ja: "画面とビジュアルを仕様化する",
  },

  // ── 랜딩: 요금제 미리보기 ─────────────────────────────────────
  "plans.title": { ko: "요금제", en: "Pricing", ja: "料金プラン" },
  "plans.noFree": {
    ko: "무료 요금제는 없습니다. Mock 으로 만든 산출물을 체험이라고 부르지 않기로 했습니다 — 계정을 만든 분께는 실제 모델만 드립니다.",
    en: "There is no free plan. We decided not to call mock output a trial — if you create an account, you get real models.",
    ja: "無料プランはありません。Mock で作った成果物を体験とは呼ばないことにしました — アカウントを作った方には実際のモデルだけをお渡しします。",
  },
  "plans.byokNote": {
    ko: "자체 키 요금제는 본인 API 키로 돌립니다. 모델 요금을 제공자가 직접 청구하므로 더 쌉니다.",
    en: "The BYOK plan runs on your own API keys. The provider bills you for the model usage directly, so it costs less here.",
    ja: "自前キープランはご自身の API キーで動きます。モデル料金はプロバイダが直接請求するため、こちらは安くなります。",
  },
  "plan.perMonth": { ko: "/ 월", en: "/ mo", ja: "/ 月" },
  "plan.credits": { ko: "월 {n} 크레딧", en: "{n} credits / mo", ja: "月 {n} クレジット" },
  "plan.byokCredits": {
    ko: "모델 요금은 내 API 키로 직접 결제",
    en: "Model usage billed to your own API key",
    ja: "モデル料金は自分の API キーで直接支払い",
  },
  "plan.concurrent": { ko: "동시 실행 {n}건", en: "{n} concurrent runs", ja: "同時実行 {n} 件" },

  // ── 랜딩: 정직한 항목 ─────────────────────────────────────────
  "honest.title": { ko: "지금 상태 — 정직하게", en: "Where this stands — honestly", ja: "現在の状態 — 正直に" },
  "honest.files": {
    ko: "만든 산출물은 파일로 남고, 회차별로 무엇이 바뀌었는지 볼 수 있습니다.",
    en: "Deliverables are kept as files, and you can see what changed in each round.",
    ja: "成果物はファイルとして残り、各ラウンドで何が変わったかを見られます。",
  },
  "honest.injection": {
    ko: "프롬프트 주입을 완전히 막지는 못합니다. 대신 설득당한 직원도 {strong}",
    en: "We cannot fully prevent prompt injection. What we can say is that even a persuaded employee {strong}",
    ja: "プロンプトインジェクションを完全には防げません。ただし説得された社員でも{strong}",
  },
  "honest.injection.strong": {
    ko: "권한 밖 파일은 쓰지 못합니다.",
    en: "cannot write outside its permitted folders.",
    ja: "権限外のファイルには書き込めません。",
  },
  "honest.noRealRun": {
    ko: "아직 실제 모델로 완주한 기록이 없습니다. 키가 없으면 Mock 직원이 대본대로 움직이고, 화면 곳곳에 MOCK 배지가 붙습니다.",
    en: "No end-to-end run on real models has happened yet. Without keys, mock employees follow a script, and a MOCK badge appears throughout the UI.",
    ja: "まだ実際のモデルで完走した記録がありません。キーがなければ Mock 社員が台本どおりに動き、画面の各所に MOCK バッジが付きます。",
  },
  "honest.noBilling": {
    ko: "결제 연동이 아직 없습니다. 크레딧은 실제로 줄고 실제로 막히지만, 충전 버튼은 데모입니다.",
    en: "Payments are not wired up yet. Credits really do decrease and really do block you, but the top-up button is a demo.",
    ja: "決済連携はまだありません。クレジットは実際に減り実際に止めますが、チャージボタンはデモです。",
  },
  "landing.reducedMotion": {
    ko: "움직임을 줄이는 설정(prefers-reduced-motion)을 켜두셨다면 이 화면은 움직이지 않습니다.",
    en: "If you have reduced motion turned on (prefers-reduced-motion), nothing on this page moves.",
    ja: "視差効果を減らす設定（prefers-reduced-motion）が有効なら、この画面は動きません。",
  },

  "mock.badge": {
    ko: "실제 모델이 아니라 Mock 제공자가 만든 결과입니다",
    en: "Produced by the mock provider, not a real model",
    ja: "実際のモデルではなく Mock プロバイダが作った結果です",
  },

  // ── 프로젝트 목록 (DAY 22) ────────────────────────────────────
  "list.running": { ko: "진행 중", en: "Running", ja: "進行中" },
  "list.done": { ko: "완료", en: "Done", ja: "完了" },
  "list.stopped": { ko: "중단", en: "Stopped", ja: "中断" },
  "list.manual": { ko: "직접 지시", en: "Manual", ja: "直接指示" },
  "list.confirmDelete": {
    ko: "{slug} 을(를) 영구히 지웁니다. 되돌릴 수 없습니다.",
    en: "This permanently deletes {slug}. It cannot be undone.",
    ja: "{slug} を完全に削除します。元に戻せません。",
  },
  "list.fromDisk": {
    ko: "색인을 읽지 못해 파일에서 직접 목록을 만들고 있습니다. 산출물은 안전합니다 — 파일이 진실이고 색인은 사본입니다.",
    en: "The index could not be read, so this list is built straight from files. Your deliverables are safe — files are the truth, the index is a copy.",
    ja: "索引を読めなかったため、ファイルから直接一覧を作っています。成果物は安全です — ファイルが真実で、索引は写しです。",
  },
  "list.rebuild": { ko: "색인 다시 만들기", en: "Rebuild index", ja: "索引を作り直す" },
  "list.summary": { ko: "요약", en: "Summary", ja: "サマリー" },
  "list.projects": { ko: "프로젝트", en: "Projects", ja: "プロジェクト" },
  "list.totalCost": { ko: "누적 비용", en: "Total cost", ja: "累計コスト" },
  "list.mockOutput": { ko: "Mock 산출물", en: "Mock output", ja: "Mock 成果物" },
  "list.countOf": { ko: "{total}건 중 {shown}건", en: "{shown} of {total}", ja: "{total} 件中 {shown} 件" },
  "list.search": { ko: "이름이나 요구사항으로 검색", en: "Search by name or requirement", ja: "名前や要件で検索" },
  "list.allStatus": { ko: "전체 상태", en: "All statuses", ja: "すべての状態" },
  "list.sortCreated": { ko: "만든 순", en: "Newest", ja: "作成順" },
  "list.sortUpdated": { ko: "최근 변경 순", en: "Recently updated", ja: "更新順" },
  "list.sortCost": { ko: "비용 순", en: "By cost", ja: "コスト順" },
  "list.sortScore": { ko: "완성도 순", en: "By completeness", ja: "完成度順" },
  "list.noMatch": { ko: "조건에 맞는 프로젝트가 없습니다.", en: "No project matches those filters.", ja: "条件に合うプロジェクトがありません。" },
  "list.none": {
    ko: "아직 만든 것이 없습니다. 사무실에서 일을 맡겨보세요.",
    en: "Nothing here yet. Hand some work to the office.",
    ja: "まだ何もありません。オフィスで仕事を任せてみてください。",
  },
  "list.delete": { ko: "영구 삭제", en: "Delete permanently", ja: "完全に削除" },
  "list.prev": { ko: "이전", en: "Previous", ja: "前へ" },
  "list.next": { ko: "다음", en: "Next", ja: "次へ" },

  // ── MANUAL 화면 (DAY 22) ──────────────────────────────────────
  "man.mock": { ko: "Mock 직원입니다.", en: "These are mock employees.", ja: "Mock 社員です。" },
  "man.mockBody": {
    ko: "지시는 실제로 전달되지만 답은 대본입니다.",
    en: "Your instruction really is delivered, but the answer comes from a script.",
    ja: "指示は実際に伝わりますが、答えは台本です。",
  },
  "man.pick": { ko: "직원을 고르세요", en: "Pick an employee", ja: "社員を選んでください" },
  "man.verifyNow": { ko: "지금 검증하기", en: "Verify now", ja: "今すぐ検証" },
  "man.instructTo": { ko: "{who}에게 지시", en: "Instruct {who}", ja: "{who} に指示" },
  "man.canWrite": { ko: "쓸 수 있는 폴더:", en: "Can write to:", ja: "書き込めるフォルダ:" },
  "man.writesNone": { ko: "없음 (글로만 답합니다)", en: "none (answers in prose only)", ja: "なし（文章のみで答えます）" },
  "man.reads": { ko: "읽기", en: "Reads", ja: "読み取り" },
  "man.placeholder": {
    ko: "예) div 에 0 나눗셈 예외 처리를 넣어주세요",
    en: "e.g. Add divide-by-zero handling to div",
    ja: "例）div に 0 除算の例外処理を入れてください",
  },
  "man.working": { ko: "작업 중…", en: "Working…", ja: "作業中…" },
  "man.instruct": { ko: "지시하기", en: "Send instruction", ja: "指示する" },
  "man.verdict": { ko: "검증 결과", en: "Review result", ja: "検証結果" },
  "man.pass": { ko: "통과", en: "Pass", ja: "合格" },
  "man.reject": { ko: "반려 ({severity})", en: "Rejected ({severity})", ja: "差し戻し（{severity}）" },

  // ── 산출물 보기 (DAY 22) ──────────────────────────────────────
  "file.none": { ko: "산출물이 없습니다.", en: "No deliverables yet.", ja: "成果物がありません。" },
  "file.compare": { ko: "회차 비교:", en: "Compare rounds:", ja: "ラウンド比較:" },
  "file.history": { ko: "이 파일의 경위", en: "How this file got here", ja: "このファイルの経緯" },
  "file.byAuthor": { ko: "{who} 가 고침", en: "changed by {who}", ja: "{who} が修正" },
  "file.atRound": { ko: "{n}라운드", en: "round {n}", ja: "{n} ラウンド" },
  "file.becauseOf": { ko: "반려 사유", en: "rejected for", ja: "差し戻し理由" },
  "file.current": { ko: "현재", en: "current", ja: "現在" },
  "file.noHistory": {
    ko: "한 번 쓰고 고치지 않았습니다.",
    en: "Written once, never revised.",
    ja: "一度書かれ、修正されていません。",
  },
  "file.toCurrent": { ko: "v{n} → 현재", en: "v{n} → current", ja: "v{n} → 現在" },
  "file.raw": { ko: "원문 보기", en: "View raw", ja: "原文を見る" },
  "file.noDiff": { ko: "차이가 없습니다.", en: "No differences.", ja: "差分はありません。" },

  // ── 요금제 화면 (DAY 22) ──────────────────────────────────────
  "price.myCredits": { ko: "내 크레딧", en: "My credits", ja: "マイクレジット" },
  "price.planSuffix": { ko: "요금제", en: "plan", ja: "プラン" },
  "price.pickFirst": {
    ko: "요금제를 고르면 여기에 잔액이 표시됩니다.",
    en: "Pick a plan and your balance appears here.",
    ja: "プランを選ぶと、ここに残高が表示されます。",
  },
  "price.byokSpent": {
    ko: "내 API 키로 나간 금액 · 우리가 청구하지 않습니다",
    en: "Spent on your own API key · we do not bill this",
    ja: "自分の API キーで使った金額 · 当社は請求しません",
  },
  "price.concurrent": { ko: "동시 실행", en: "Concurrent runs", ja: "同時実行" },
  "price.perProject": { ko: "프로젝트당 상한", en: "Cap per project", ja: "プロジェクトごとの上限" },
  "price.left": { ko: "남은 크레딧 · 원가로 {usd}", en: "Credits left · {usd} at cost", ja: "残りクレジット · 原価で {usd}" },
  "price.granted": { ko: "받은 크레딧", en: "Granted", ja: "付与" },
  "price.spent": { ko: "쓴 크레딧", en: "Spent", ja: "使用" },
  "price.noPlan": { ko: "아직 요금제가 없습니다.", en: "You have no plan yet.", ja: "まだプランがありません。" },
  "price.noPlanBody": {
    ko: "무료 요금제는 없습니다 — 아래에서 하나를 고르기 전까지 프로젝트를 시작할 수 없습니다.",
    en: "There is no free plan — you cannot start a project until you pick one below.",
    ja: "無料プランはありません — 下で選ぶまでプロジェクトを開始できません。",
  },
  "price.mockPlan": { ko: "이 요금제는 실제 모델을 부르지 않습니다.", en: "This plan never calls a real model.", ja: "このプランは実際のモデルを呼びません。" },
  "price.mockPlanBody": {
    ko: "산출물은 대본이 만든 것이고 AI 의 작업 결과가 아닙니다. 실제로 돌리려면 유료 요금제로 바꾸거나, 자체 키 요금제에서 본인 API 키를 등록하세요.",
    en: "The output comes from a script, not from a model. To run for real, move to a paid plan or register your own keys on the bring-your-own-key plan.",
    ja: "成果物は台本が作ったもので、AI の作業結果ではありません。実際に動かすには有料プランに変えるか、自前キープランでご自身のキーを登録してください。",
  },
  "price.negative": {
    ko: "잔액이 마이너스입니다. 초과분은 지워지지 않고 그대로 남습니다 — 다음 달에 그만큼 덜 받습니다.",
    en: "Your balance is negative. The overage is not wiped — next month grants that much less.",
    ja: "残高がマイナスです。超過分は消えずに残ります — 翌月はその分だけ少なく付与されます。",
  },
  "price.topup": { ko: "크레딧 충전", en: "Top up credits", ja: "クレジットをチャージ" },
  "price.topupNote": {
    ko: "결제 연동은 없습니다. 잔액이 실제로 줄고 막히는지 확인하기 위한 데모용 버튼입니다. 충전은 크레딧당 단가가 구독보다 비쌉니다 — 많이 쓰면 요금제를 올리는 편이 쌉니다.",
    en: "Payments are not wired up. These buttons exist to show that the balance really drops and really blocks you. Top-ups cost more per credit than a subscription — if you use a lot, moving up a plan is cheaper.",
    ja: "決済連携はありません。残高が実際に減り実際に止まることを確認するためのデモ用ボタンです。チャージはクレジット単価が定期より高くなります — たくさん使うならプランを上げる方が安いです。",
  },
  "price.noTopup": {
    ko: "이 요금제는 크레딧을 쓰지 않습니다 — 충전할 것도 없습니다.",
    en: "This plan does not use credits — there is nothing to top up.",
    ja: "このプランはクレジットを使いません — チャージするものもありません。",
  },
  "price.creditWorth": { ko: "1 크레딧 = 원가 {usd}", en: "1 credit = {usd} at cost", ja: "1 クレジット = 原価 {usd}" },
  "price.verifiedOn": { ko: " · 단가 대조일 {date}", en: " · prices checked {date}", ja: " · 単価照合日 {date}" },
  "price.unverified": { ko: "단가가 검증되지 않았습니다.", en: "Prices are not verified.", ja: "単価が検証されていません。" },
  "price.unverifiedBody": { ko: "잔액과 비용은 추측입니다.", en: "The balance and costs are guesses.", ja: "残高とコストは推測です。" },
  "price.inUse": { ko: "사용 중", en: "in use", ja: "使用中" },
  "price.free": { ko: "무료", en: "Free", ja: "無料" },
  "price.current": { ko: "현재 요금제", en: "Current plan", ja: "現在のプラン" },
  "price.choose": { ko: "이 요금제로", en: "Choose this", ja: "このプランにする" },
  "price.maxPerProject": { ko: "프로젝트당 최대 {usd}", en: "Up to {usd} per project", ja: "プロジェクトごとに最大 {usd}" },
  "price.byokFirst": {
    ko: "바꾸기 전에 설정 화면에서 본인 API 키를 먼저 등록하세요. 키가 없으면 실행이 거부됩니다 — 운영자 키로 대신 부르지 않습니다.",
    en: "Register your own API keys in settings before switching. Without them runs are refused — we never fall back to the operator's keys.",
    ja: "切り替える前に設定でご自身の API キーを登録してください。キーがないと実行は拒否されます — 運営者のキーで代わりに呼ぶことはありません。",
  },
  "price.estimate": { ko: "프로젝트당 크레딧은 추정입니다.", en: "Credits per project are an estimate.", ja: "プロジェクトごとのクレジットは推定です。" },
  "price.measured": {
    ko: "프로젝트당 크레딧은 실제로 끝난 프로젝트 {n}건에서 잰 값입니다.",
    en: "Credits per project are measured from {n} finished projects.",
    ja: "プロジェクトごとのクレジットは、実際に完了した {n} 件から測った値です。",
  },
  "price.measuredBody": {
    ko: "중앙값 {median} · 나쁠 때(상위 10%) {p90}. 쓰는 방식이 달라지면 숫자도 달라집니다.",
    en: "Median {median} · bad case (top 10%) {p90}. The numbers move with how you use it.",
    ja: "中央値 {median} · 悪い場合（上位 10%）{p90}。使い方が変われば数字も変わります。",
  },
  "price.perMonthMeasured": { ko: "월 {a}~{b}건", en: "{a}–{b} projects / mo", ja: "月 {a}〜{b} 件" },
  "price.estimateBody": {
    ko: "아직 실제 모델로 프로젝트를 완주해본 적이 없습니다 — 실측 후 요금제가 조정될 수 있습니다.",
    en: "No project has been run end-to-end on a real model yet — the plans may change once we measure.",
    ja: "まだ実際のモデルでプロジェクトを完走したことがありません — 実測後にプランが調整される可能性があります。",
  },
  "price.noRealCalls": { ko: "실제 모델을 부르지 않습니다", en: "never calls a real model", ja: "実際のモデルを呼びません" },
  "price.byokBilling": { ko: "모델 요금은 {strong} 결제", en: "Model usage billed {strong}", ja: "モデル料金は{strong}決済" },
  "price.byokBilling.strong": { ko: "내 API 키로 직접", en: "to your own API key", ja: "自分の API キーで直接" },
  "price.creditsPerMonth": { ko: "월 {n} 크레딧", en: "{n} credits / mo", ja: "月 {n} クレジット" },
  "price.perMonthEst": { ko: "월 {a}~{b}건 (추정)", en: "about {a}–{b} projects / mo", ja: "月 {a}〜{b} 件（推定）" },
  "price.perMonthMax": { ko: "월 최대 {n}건 (추정)", en: "up to {n} projects / mo", ja: "月 最大 {n} 件（推定）" },
  "price.perMonthAbout": { ko: "월 {n}건 남짓 (추정)", en: "about {n} projects / mo", ja: "月 {n} 件ほど（推定）" },
  "price.lessThanOne": { ko: "프로젝트 1건도 안 될 수 있음", en: "possibly less than one project", ja: "プロジェクト 1 件に満たない可能性" },

  // ── 실행 중 화면 (DAY 22) ─────────────────────────────────────
  "run.mockWarn": { ko: "지금은 Mock 직원이 일합니다.", en: "Mock employees are working right now.", ja: "今は Mock 社員が働いています。" },
  "run.mockWarnBody": {
    ko: "산출물은 실제 AI 의 작업 결과가 아니라 미리 짜인 대본입니다. {link} 하면 실제 직원이 일합니다.",
    en: "The output is a prewritten script, not the work of a real model. {link} and real employees take over.",
    ja: "成果物は実際の AI の作業結果ではなく、あらかじめ書かれた台本です。{link} すると実際の社員が働きます。",
  },
  "run.mockWarnLink": {
    ko: "설정에서 API 키를 등록",
    en: "Register API keys in settings",
    ja: "設定で API キーを登録",
  },
  "run.noCross": { ko: "교차검증이 성립하지 않습니다.", en: "Cross-checking does not hold.", ja: "相互検証が成り立ちません。" },
  "run.noCrossBody": {
    ko: "구현자와 검증자가 같은 회사의 모델이거나, 검증자 쪽 키가 없습니다.",
    en: "The implementer and the reviewer are from the same company, or the reviewer's key is missing.",
    ja: "実装者と検証者が同じ会社のモデルか、検証者側のキーがありません。",
  },
  "run.concurrentNote": {
    ko: "(동시 실행 한도는 비용과 요청 한도를 함께 막습니다)",
    en: "(the concurrency limit guards both cost and rate limits)",
    ja: "（同時実行の上限はコストとレート上限の両方を守ります）",
  },
  "run.routing": { ko: "전략가의 판단", en: "The strategist's call", ja: "ストラテジストの判断" },
  "run.detail": { ko: "프로젝트 상세", en: "Project detail", ja: "プロジェクト詳細" },

  // ── 작업 로그 (DAY 22) ────────────────────────────────────────
  "log.connected": { ko: "연결됨", en: "connected", ja: "接続済み" },
  "log.disconnected": { ko: "연결 끊김 — 재연결 중", en: "disconnected — reconnecting", ja: "切断 — 再接続中" },
  "log.polling": { ko: "· SSE 가 막혀 폴링으로 받는 중", en: "· SSE blocked, falling back to polling", ja: "· SSE が塞がれポーリングで受信中" },
  "log.lines": { ko: "{n}줄", en: "{n} lines", ja: "{n} 行" },
  "log.empty": { ko: "아직 기록이 없습니다.", en: "Nothing here yet.", ja: "まだ記録がありません。" },
  "log.unread": { ko: "새 소식 {n}개 ↓", en: "{n} new ↓", ja: "新着 {n} 件 ↓" },
  "log.done": { ko: "완료", en: "Done", ja: "完了" },
  "log.stopped": { ko: "중단", en: "Stopped", ja: "中断" },
  "log.scoreSuffix": { ko: " · 완성도 {n}%", en: " · {n}% complete", ja: " · 完成度 {n}%" },

  // ── 태스크와 점수 (DAY 22) ────────────────────────────────────
  "task.empty": { ko: "아직 계획이 없습니다.", en: "No plan yet.", ja: "まだ計画がありません。" },
  "task.done": { ko: "완료", en: "done", ja: "完了" },
  "task.running": { ko: "진행 중", en: "in progress", ja: "進行中" },
  "task.waiting": { ko: "대기", en: "waiting", ja: "待機" },
  "task.finalScore": { ko: "인수기준 충족률 (최종)", en: "Acceptance criteria met (final)", ja: "受け入れ基準の達成率（最終）" },
  "task.midScore": { ko: "진행률 (중간 집계)", en: "Progress (interim)", ja: "進捗（中間集計）" },
  "task.cost": { ko: "이번 프로젝트 비용", en: "Cost of this project", ja: "このプロジェクトのコスト" },
  "task.rounds": { ko: "{n}라운드", en: "{n} rounds", ja: "{n} ラウンド" },
  "task.k.tasks": { ko: "태스크", en: "Tasks", ja: "タスク" },
  "task.k.tests": { ko: "테스트", en: "Tests", ja: "テスト" },
  "task.k.coverage": { ko: "기준 커버리지", en: "Criteria covered", ja: "基準カバレッジ" },
  "task.k.criteria": { ko: "인수기준", en: "Criteria", ja: "受け入れ基準" },
  "task.k.reworks": { ko: "반려", en: "Rejections", ja: "差し戻し" },
  "task.k.replans": { ko: "재기획", en: "Replans", ja: "再計画" },

  // ── 프로젝트 상세 (DAY 22) ────────────────────────────────────
  "proj.loading": { ko: "불러오는 중…", en: "Loading…", ja: "読み込み中…" },
  "proj.mockWarn": {
    ko: "이 프로젝트는 Mock 직원이 만들었습니다.",
    en: "This project was produced by mock employees.",
    ja: "このプロジェクトは Mock 社員が作りました。",
  },
  "proj.mockWarnBody": {
    ko: "산출물은 실제 AI 의 작업 결과가 아닙니다.",
    en: "The deliverables are not the output of a real model.",
    ja: "成果物は実際の AI の作業結果ではありません。",
  },
  "proj.stop": { ko: "정지", en: "Stop", ja: "停止" },
  "proj.stopped": { ko: "중단", en: "Stopped", ja: "中断" },
  "proj.unmet": {
    ko: "충족되지 않은 인수기준",
    en: "Unmet acceptance criteria",
    ja: "満たされていない受け入れ基準",
  },
  "proj.files": { ko: "산출물", en: "Deliverables", ja: "成果物" },
  "proj.state": { ko: "상태", en: "Status", ja: "状態" },
  "proj.completeness": { ko: "완성도", en: "Completeness", ja: "完成度" },
  "proj.fileCount": { ko: "파일", en: "Files", ja: "ファイル" },
  "proj.score": { ko: "완성도와 비용", en: "Completeness and cost", ja: "完成度とコスト" },
  "proj.tasks": { ko: "태스크", en: "Tasks", ja: "タスク" },
  "proj.criteria": { ko: "인수기준", en: "Acceptance criteria", ja: "受け入れ基準" },
  "proj.usage": { ko: "직원별 사용량", en: "Usage by employee", ja: "社員ごとの使用量" },
  "proj.calls": { ko: "{n}회", en: "{n} calls", ja: "{n} 回" },
  "proj.back": { ko: "사무실로", en: "To the office", ja: "オフィスへ" },

  // ── 내 API 키 (BYOK · DAY 22) ─────────────────────────────────
  "byok.title": {
    ko: "내 API 키 (자체 키 요금제)",
    en: "My API keys (bring-your-own-key plan)",
    ja: "自分の API キー（自前キープラン）",
  },
  "byok.inUse": { ko: "사용 중", en: "in use", ja: "使用中" },
  "byok.short": { ko: "키가 모자랍니다", en: "keys missing", ja: "キーが足りません" },
  "byok.warn": {
    ko: "자체 키 요금제인데 키가 모자랍니다 — 실행이 거부됩니다. 운영자 키로 대신 호출하지 않습니다.",
    en: "You are on the bring-your-own-key plan but keys are missing — runs will be refused. We never fall back to the operator's keys.",
    ja: "自前キープランですがキーが足りません — 実行は拒否されます。運営者のキーで代わりに呼び出すことはありません。",
  },
  "byok.body": {
    ko: "여기 넣은 키로 내 프로젝트가 돌아가고, {strong} 크레딧은 차감되지 않습니다. 키는 암호화해서 보관하고 화면에는 마스킹된 형태만 돌아옵니다.",
    en: "Your projects run on the keys you enter here, and {strong} No credits are deducted. Keys are stored encrypted, and only masked values come back to the screen.",
    ja: "ここに入れたキーで自分のプロジェクトが動き、{strong} クレジットは差し引かれません。キーは暗号化して保管し、画面にはマスクされた形だけが返ります。",
  },
  "byok.body.strong": {
    ko: "모델 요금은 내 계정으로 직접 청구됩니다.",
    en: "model usage is billed to your own account.",
    ja: "モデル料金はご自身のアカウントに直接請求されます。",
  },
  "byok.kekWarn": {
    ko: "이 서버는 키 암호화 키(KEK)를 파일에 두고 있습니다. 서버 디스크를 가져간 사람은 여기 넣은 키도 가져갑니다 — 운영자는 BYOK_SECRET 을 환경변수로 넣어야 합니다.",
    en: "This server keeps the key-encryption key (KEK) in a file. Anyone who takes the server disk takes these keys too — the operator should pass BYOK_SECRET through the environment.",
    ja: "このサーバーは鍵暗号化キー（KEK）をファイルに置いています。サーバーのディスクを持ち出した人はここのキーも持ち出せます — 運営者は BYOK_SECRET を環境変数で渡すべきです。",
  },
  "byok.clear": { ko: "지우기", en: "Clear", ja: "削除" },
  "byok.crossNote": {
    ko: "구현자와 검증자는 {strong} — Anthropic 과 Google 키가 둘 다 있어야 교차검증이 성립합니다.",
    en: "The implementer and the reviewer must be {strong} — cross-checking only holds with both an Anthropic and a Google key.",
    ja: "実装者と検証者は{strong} — Anthropic と Google のキーが両方あって初めて相互検証が成り立ちます。",
  },
  "byok.crossNote.strong": {
    ko: "서로 다른 회사여야 합니다",
    en: "from different companies",
    ja: "別の会社でなければなりません",
  },
  "set.fallback": { ko: "대체", en: "fallback", ja: "代替" },

  // ── 설정 (DAY 22) ─────────────────────────────────────────────
  "set.allMock": {
    ko: "모든 직원이 Mock 으로 일하고 있습니다. 아래에서 키를 등록하세요.",
    en: "Every employee is running on mock. Register keys below.",
    ja: "全社員が Mock で動いています。下でキーを登録してください。",
  },
  "set.noCross": {
    ko: "교차검증이 성립하지 않습니다 — 구현자(Claude)와 검증자(Gemini) 양쪽 키가 모두 있어야 합니다. 같은 모델은 같은 실수를 함께 놓칩니다.",
    en: "Cross-checking does not hold — you need keys for both the implementer (Claude) and the reviewer (Gemini). The same model misses the same mistakes.",
    ja: "相互検証が成り立ちません — 実装者（Claude）と検証者（Gemini）の両方のキーが必要です。同じモデルは同じ間違いを一緒に見落とします。",
  },
  "set.operatorKeys": { ko: "운영자 API 키", en: "Operator API keys", ja: "運営者の API キー" },
  "set.operatorLocked": {
    ko: "서버 배포에서는 운영자 키를 화면에서 바꿀 수 없습니다 — 환경변수로만 들어옵니다. 본인 키를 쓰시려면 위의 '내 API 키'에 등록하세요.",
    en: "On a server deployment the operator keys cannot be changed from the UI — they come only from the environment. To use your own keys, register them above under 'My API keys'.",
    ja: "サーバー配備では運営者キーを画面から変更できません — 環境変数からのみ入ります。ご自身のキーを使うには上の「自分の API キー」に登録してください。",
  },
  "set.operatorHint": {
    ko: "키는 저장하지 않으면 서버 메모리에만 남고, 환경변수로 넣은 키는 기동 즉시 환경에서 지워집니다. 화면에는 마스킹된 형태만 돌아옵니다.",
    en: "Unless you save them, keys live only in server memory; keys passed through the environment are removed from it at startup. Only masked values come back to the screen.",
    ja: "保存しなければキーはサーバーのメモリにだけ残り、環境変数で渡したキーは起動直後に環境から消されます。画面にはマスクされた形だけが返ります。",
  },
  "set.registeredEnv": { ko: "등록됨 (환경변수)", en: "registered (from env)", ja: "登録済み（環境変数）" },
  "set.notRegistered": { ko: "등록되지 않음", en: "not registered", ja: "未登録" },
  "set.check": { ko: "확인", en: "Check", ja: "確認" },
  "set.save": { ko: "저장", en: "Save", ja: "保存" },
  "set.persist": {
    ko: "디스크에 저장 (.secrets.json, 소유자만 읽기)",
    en: "Save to disk (.secrets.json, owner-readable only)",
    ja: "ディスクに保存（.secrets.json、所有者のみ読み取り）",
  },
  "set.forget": { ko: "저장된 키 지우기", en: "Forget stored keys", ja: "保存したキーを削除" },
  "set.providers": { ko: "제공자", en: "Providers", ja: "プロバイダ" },
  "set.real": { ko: "실제", en: "live", ja: "実際" },
  "set.keyYes": { ko: "키 있음", en: "key present", ja: "キーあり" },
  "set.keyNo": { ko: "키 없음", en: "no key", ja: "キーなし" },
  "set.models": { ko: "직원별 모델", en: "Model per employee", ja: "社員ごとのモデル" },
  "set.modelsHint": {
    ko: "단가표에 없는 모델은 거부됩니다. 단가를 모르면 비용이 0 으로 잡히고, 0 은 공짜가 아니라 모른다는 뜻이라 예산 상한이 걸리지 않습니다.",
    en: "Models missing from the price table are rejected. Without a price the cost reads as 0, and 0 means 'unknown', not 'free' — so the budget limit would never trigger.",
    ja: "単価表にないモデルは拒否されます。単価が分からないとコストが 0 になり、0 は無料ではなく「不明」という意味なので、予算上限が効かなくなります。",
  },

  // ── 로그인 (DAY 22) ───────────────────────────────────────────
  "auth.loading": { ko: "불러오는 중…", en: "Loading…", ja: "読み込み中…" },
  "auth.noBackend": {
    ko: "백엔드에 닿지 못했습니다. 서버가 떠 있는지 확인하세요.",
    en: "Could not reach the backend. Check that the server is running.",
    ja: "バックエンドに接続できませんでした。サーバーが起動しているか確認してください。",
  },
  "auth.firstAccount": {
    ko: "이 서버의 첫 계정입니다.",
    en: "This is the first account on this server.",
    ja: "このサーバーの最初のアカウントです。",
  },
  "auth.firstAccountBody": {
    ko: "지금 만드는 계정이 첫 사용자가 됩니다. 이 문구가 낯선 서버에서 보인다면 뭔가 잘못된 것입니다.",
    en: "The account you create now becomes the first user. If you see this on a server you do not own, something is wrong.",
    ja: "今作るアカウントが最初のユーザーになります。見覚えのないサーバーでこの文が出るなら、何かがおかしいということです。",
  },
  "auth.login": { ko: "로그인", en: "Log in", ja: "ログイン" },
  "auth.signup": { ko: "가입", en: "Sign up", ja: "登録" },
  "auth.email": { ko: "이메일", en: "Email", ja: "メール" },
  "auth.displayName": { ko: "표시 이름", en: "Display name", ja: "表示名" },
  "auth.displayNameHint": {
    ko: "비워두면 이메일 앞부분을 씁니다.",
    en: "Left empty, we use the part before the @.",
    ja: "空のままなら、メールの @ より前を使います。",
  },
  "auth.password": { ko: "비밀번호", en: "Password", ja: "パスワード" },
  "auth.passwordHint": { ko: "10자 이상.", en: "10 characters or more.", ja: "10 文字以上。" },
  "auth.working": { ko: "확인 중…", en: "Checking…", ja: "確認中…" },
  "auth.signupCta": { ko: "가입하고 시작", en: "Sign up and start", ja: "登録して始める" },
  "auth.noGoogle": {
    ko: "구글 로그인은 아직 없습니다. 계정 구조는 나중에 끼울 수 있게 만들어져 있습니다.",
    en: "Google sign-in is not here yet. The account model is built so it can be added later without a migration.",
    ja: "Google ログインはまだありません。アカウント構造は後から差し込めるように作ってあります。",
  },
  "auth.localUser": { ko: "로컬 사용자", en: "Local user", ja: "ローカルユーザー" },
  "auth.localHint": {
    ko: "DEPLOY_MODE=local — 로그인 없이 동작합니다",
    en: "DEPLOY_MODE=local — runs without login",
    ja: "DEPLOY_MODE=local — ログインなしで動作します",
  },
  "auth.logout": { ko: "로그아웃", en: "Log out", ja: "ログアウト" },

  // ── 비밀번호 재설정 · 이메일 확인 (DAY 22) ────────────────────
  "reset.forgot": { ko: "비밀번호를 잊으셨나요?", en: "Forgot your password?", ja: "パスワードをお忘れですか？" },
  "reset.title": { ko: "비밀번호 재설정", en: "Reset password", ja: "パスワードの再設定" },
  "reset.askEmail": {
    ko: "가입한 이메일 주소를 적으면 재설정 링크를 보냅니다.",
    en: "Enter the email you signed up with and we will send a reset link.",
    ja: "登録したメールアドレスを入力すると、再設定リンクを送ります。",
  },
  "reset.send": { ko: "링크 보내기", en: "Send link", ja: "リンクを送る" },
  "reset.sentAnyway": {
    ko: "그 주소로 계정이 있다면 링크를 보냈습니다. 계정이 있는지 여부는 알려드리지 않습니다 — 아무나 주소를 넣어보며 가입 여부를 확인할 수 있게 되기 때문입니다.",
    en: "If an account exists for that address, a link is on its way. We do not say whether it exists — otherwise anyone could check who is signed up.",
    ja: "そのアドレスのアカウントがあればリンクを送りました。アカウントの有無はお伝えしません — 誰でも登録の有無を確認できてしまうからです。",
  },
  "reset.notDelivered": {
    ko: "다만 이 서버는 메일을 보내도록 설정되지 않았습니다. 링크는 서버 로그에만 남았습니다 — 운영자에게 문의하세요.",
    en: "That said, this server is not configured to send mail. The link only went to the server log — ask the operator.",
    ja: "ただしこのサーバーはメール送信が設定されていません。リンクはサーバーのログにのみ残りました — 運営者にお問い合わせください。",
  },
  "reset.newPassword": { ko: "새 비밀번호", en: "New password", ja: "新しいパスワード" },
  "reset.apply": { ko: "비밀번호 바꾸기", en: "Change password", ja: "パスワードを変更" },
  "reset.done": {
    ko: "비밀번호를 바꿨습니다. 다른 기기의 로그인은 전부 끊었습니다 — 되찾는 이유는 대개 누가 들어와 있기 때문입니다.",
    en: "Password changed. Every other session was signed out — you usually reset because someone else is in.",
    ja: "パスワードを変更しました。他の端末のログインはすべて切りました — 再設定する理由は、たいてい誰かが入っているからです。",
  },
  "reset.noToken": {
    ko: "링크가 올바르지 않습니다. 메일의 주소를 그대로 열어주세요.",
    en: "That link is not valid. Open the address from the email as-is.",
    ja: "リンクが正しくありません。メールのアドレスをそのまま開いてください。",
  },
  "reset.toOffice": { ko: "사무실로 가기", en: "Go to the office", ja: "オフィスへ" },
  "verify.title": { ko: "이메일 확인", en: "Verify email", ja: "メールの確認" },
  "verify.working": { ko: "확인하는 중…", en: "Verifying…", ja: "確認中…" },
  "verify.done": { ko: "이메일 주소를 확인했습니다.", en: "Your email address is verified.", ja: "メールアドレスを確認しました。" },
  "verify.notice": {
    ko: "이메일이 아직 확인되지 않았습니다.",
    en: "Your email address is not verified yet.",
    ja: "メールアドレスがまだ確認されていません。",
  },
  "verify.send": { ko: "확인 메일 보내기", en: "Send verification email", ja: "確認メールを送る" },
  "verify.sent": { ko: "확인 메일을 보냈습니다.", en: "Verification email sent.", ja: "確認メールを送りました。" },

  // ── 인사 (DAY 21) ─────────────────────────────────────────────
  "staff.rename": { ko: "이름 바꾸기", en: "Rename", ja: "名前を変更" },
  "staff.save": { ko: "저장", en: "Save", ja: "保存" },
  "staff.reset": { ko: "기본 이름", en: "Default", ja: "既定の名前" },
  "staff.hire": { ko: "채용하기", en: "Hire", ja: "採用する" },
  "staff.fire": { ko: "내보내기", en: "Let go", ja: "退職させる" },
  "staff.empty": { ko: "빈 자리", en: "empty seat", ja: "空席" },
  "staff.locked": {
    ko: "이 자리는 비울 수 없습니다 — 없으면 회사가 돌지 않습니다.",
    en: "This seat cannot be emptied — the company does not run without it.",
    ja: "この席は空にできません — なければ会社が回りません。",
  },

  // ── 사무실 ────────────────────────────────────────────────────
  "office.alt": {
    ko: "위에서 내려다본 도트 사무실. 자리마다 직원이 앉아 있고, 머리 자리에는 그 직원을 돌리는 AI 제공자의 표식이 있습니다.",
    en: "A top-down pixel office. Each seat holds an employee, and the head shows the mark of the AI provider that runs them.",
    ja: "上から見たドットのオフィス。各席に社員が座り、頭の位置にはその社員を動かす AI プロバイダの印があります。",
  },
  "office.title": { ko: "사무실", en: "Office", ja: "オフィス" },
  "office.hint": {
    ko: "자리를 가리키면 누가 무엇으로 일하는지 보입니다.",
    en: "Point at a seat to see who works there and on what.",
    ja: "席を指すと、誰が何で働いているかが見えます。",
  },
  "office.log": { ko: "작업 로그", en: "Activity log", ja: "作業ログ" },
  "office.projects": { ko: "프로젝트", en: "Projects", ja: "プロジェクト" },
  "office.newProject": { ko: "새 프로젝트", en: "New project", ja: "新規プロジェクト" },
  "office.collapse": { ko: "목록 접기", en: "Collapse list", ja: "一覧を折りたたむ" },
  "office.ask": {
    ko: "무엇을 만들까요?",
    en: "What should we build?",
    ja: "何を作りましょうか？",
  },
  "office.placeholder": {
    ko: "예) 사칙연산을 하는 계산기 모듈과 사용법 문서를 만들어주세요",
    en: "e.g. Build a calculator module with the four basic operations, plus usage docs",
    ja: "例）四則演算ができる電卓モジュールと使い方ドキュメントを作ってください",
  },
  "office.auto": { ko: "AUTO 로 맡기기", en: "Hand it to AUTO", ja: "AUTO に任せる" },
  "office.manual": { ko: "직접 지시하기", en: "Direct it myself", ja: "自分で指示する" },
  "office.whoFirst": { ko: "누가 맡을지 먼저 보기", en: "See who would take it", ja: "誰が担当するか先に見る" },
  "office.empty": {
    ko: "아직 프로젝트가 없습니다. 위에 한 줄 적어 시작하세요.",
    en: "No projects yet. Write one line above to start.",
    ja: "まだプロジェクトがありません。上に一行書いて始めてください。",
  },
  "office.logEmpty": {
    ko: "작업이 시작되면 여기에 직원들의 대화가 흐릅니다.",
    en: "Once work starts, the team's messages flow here.",
    ja: "作業が始まると、ここにチームのやり取りが流れます。",
  },
  "office.model": { ko: "모델", en: "Model", ja: "モデル" },
  "office.calls": { ko: "호출", en: "Calls", ja: "呼び出し" },
  "office.cost": { ko: "비용", en: "Cost", ja: "コスト" },
  "office.writes": { ko: "쓰기", en: "Writes", ja: "書き込み" },
  "office.reads": { ko: "읽기", en: "Reads", ja: "読み取り" },
  "office.none": { ko: "없음", en: "none", ja: "なし" },
  "office.working": { ko: "작업 중", en: "Working", ja: "作業中" },
  "office.idle": { ko: "대기", en: "Idle", ja: "待機" },
} satisfies Record<string, Entry>;

export type Key = keyof typeof S;

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key, vars?: Record<string, string | number>) => string;
};

const LangContext = createContext<Ctx | null>(null);

/** 브라우저가 선호하는 언어. 모르는 언어면 영어로 떨어뜨린다. */
function detect(): Lang {
  if (typeof navigator === "undefined") return "ko";
  for (const raw of navigator.languages ?? [navigator.language]) {
    const code = (raw ?? "").slice(0, 2).toLowerCase();
    if ((LANGS as readonly string[]).includes(code)) return code as Lang;
  }
  return "en";
}

function read(): Lang | null {
  try {
    const v = window.localStorage.getItem(STORE_KEY);
    return (LANGS as readonly string[]).includes(v ?? "") ? (v as Lang) : null;
  } catch {
    return null;              // 사생활 보호 모드에서는 읽기가 던진다
  }
}

/**
 * 고른 언어는 리액트 **밖에** 둔다.
 *
 * 처음에는 effect 안에서 `setState` 로 언어를 정했는데, 그러면 그림을
 * 한 번 그린 뒤 다시 그리게 된다(리액트가 경고한다). 서버는 언어를 알 수
 * 없고 브라우저만 아는 값이므로, 이건 상태가 아니라 **바깥 저장소**다.
 * `useSyncExternalStore` 는 서버용 값과 브라우저용 값을 따로 받으므로
 * 하이드레이션도 깨지지 않는다.
 */
let current: Lang | null = null;
const listeners = new Set<() => void>();

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function snapshot(): Lang {
  if (current === null) current = read() ?? detect();
  return current;
}

// 서버에는 브라우저 설정도 저장소도 없다. 항상 한국어로 그린다.
function serverSnapshot(): Lang {
  return "ko";
}

function store(l: Lang) {
  current = l;
  try {
    window.localStorage.setItem(STORE_KEY, l);
  } catch {
    // 저장이 안 돼도 이번 방문에는 바뀐 언어로 쓴다. 다음에 다시 고르면 된다.
  }
  listeners.forEach((fn) => fn());
}

export function LangProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, snapshot, serverSnapshot);

  useEffect(() => {
    // 화면 밖에서도 언어는 읽힌다 — 스크린리더와 검색엔진이 이 속성을 본다.
    document.documentElement.lang = lang;
    // 서버도 알아야 한다. 오류 문장과 **직원이 쓰는 글**의 언어가 여기서
    // 정해진다 (DAY 21).
    setApiLanguage(lang);
  }, [lang]);

  const setLang = useCallback((l: Lang) => store(l), []);

  const t = useCallback(
    (key: Key, vars?: Record<string, string | number>) => {
      const entry = S[key] as Entry | undefined;
      // 표에 없는 키는 **키를 그대로** 보여준다. 빈 문자열로 두면 화면이
      // 조용히 비고, 누가 언제 빠뜨렸는지 아무도 모른다.
      let out = entry ? entry[lang] || entry.ko : String(key);
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          out = out.replaceAll(`{${k}}`, String(v));
        }
      }
      return out;
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): Ctx {
  const ctx = useContext(LangContext);
  if (!ctx) {
    // 제공자 밖에서도 화면이 죽지 않게 한국어로 답한다. 번역이 빠진 것은
    // 불편이지만, 여기서 던지면 그 화면 전체가 사라진다.
    return {
      lang: "ko",
      setLang: () => {},
      t: (key) => (S[key] as Entry | undefined)?.ko ?? String(key),
    };
  }
  return ctx;
}

// 요금제 이름은 **서버가 언어에 맞춰 보낸다**(backend/app/usage/credits.py
// 의 `localized()`). 화면에도 같은 표를 두면 값이 두 곳에 살게 되고,
// 요금제를 하나 추가할 때 두 곳을 고쳐야 한다. 여기에는 두지 않는다.
