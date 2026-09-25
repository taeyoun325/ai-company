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
import { ApiError, LANG_STORE_KEY, setApiLanguage } from "@/lib/api";
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

// 저장 자리는 `lib/api.ts` 가 먼저 쓴다 — 첫 요청이 effect 보다 빠르다.
const STORE_KEY = LANG_STORE_KEY;

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
  "nav.guide": { ko: "설명", en: "Guide", ja: "説明" },
  "nav.language": { ko: "언어", en: "Language", ja: "言語" },
  "footer.note": {
    ko: "당신은 CEO 입니다. 직원에게 직접 지시하거나 AUTO 로 맡기세요.",
    en: "You are the CEO. Direct an employee yourself, or hand it to AUTO.",
    ja: "あなたが CEO です。社員に直接指示するか、AUTO に任せてください。",
  },
  "lang.partial": {
    ko: "",
    en: "Screens and the activity log are translated. What the employees write follows the language you pick — older projects keep the language they were made in.",
    ja: "画面と作業ログは翻訳済みです。社員が書く文章は選んだ言語に従います — 以前のプロジェクトは作られた時の言語のままです。",
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
  // 누가 잡고 있는지 말한다. "작업 중"만으로는 기다릴지 말지 정할 수 없고,
  // 인스턴스를 넘어 점유를 보게 된 뒤로는 **내가 아닌 사람**일 수도 있다.
  "man.busyWho": { ko: "{who} 작업 중…", en: "{who} is working…", ja: "{who} が作業中…" },
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
  "file.copy": { ko: "복사", en: "Copy", ja: "コピー" },
  "file.download": { ko: "다운로드", en: "Download", ja: "ダウンロード" },

  // ── 요금제 화면 (DAY 22) ──────────────────────────────────────
  "price.myCredits": { ko: "내 크레딧", en: "My credits", ja: "マイクレジット" },
  "price.noPlans": {
    ko: "요금제를 불러오지 못했습니다. 서버의 요금표(pricing.json)를 확인하세요.",
    en: "No plans came back. Check the server's price table (pricing.json).",
    ja: "プランを読み込めませんでした。サーバーの料金表（pricing.json）を確認してください。",
  },
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
  "run.mockWarnClose": {
    ko: "닫기 (이 탭에서는 다시 안 보임)",
    en: "Dismiss (won't show again in this tab)",
    ja: "閉じる（このタブでは再表示されません）",
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
  // 끝난 프로젝트의 로그 칸. "아직 기록이 없습니다" 는 여기서 거짓말이
  // 된다 — 기록은 있었고, 우리가 보관하지 않는다. 그 사실을 말하고,
  // 남아 있는 곳(판본 이력)을 가리킨다.
  "log.past": {
    ko: "실행 중에 흐른 로그는 보관하지 않습니다. 누가 무엇을 왜 고쳤는지는 아래 산출물의 판본 이력에 남아 있습니다.",
    en: "The live log is not kept after a run. Who changed what, and why, is recorded in each deliverable's version trail below.",
    ja: "実行中のログは保存されません。誰が何をなぜ変更したかは、下の成果物の版履歴に残っています。",
  },
  "log.unread": { ko: "새 소식 {n}개 ↓", en: "{n} new ↓", ja: "新着 {n} 件 ↓" },
  "log.stepLines": { ko: "{n}줄", en: "{n} lines", ja: "{n} 行" },
  "log.done": { ko: "완료", en: "Done", ja: "完了" },
  "log.stopped": { ko: "중단", en: "Stopped", ja: "中断" },
  "log.scoreSuffix": { ko: " · 완성도 {n}%", en: " · {n}% complete", ja: " · 完成度 {n}%" },

  // ── 로그를 평범한 말로 (DAY 23) ───────────────────────────────
  "narrate.button": { ko: "쉽게 설명", en: "Explain simply", ja: "やさしく説明" },
  "narrate.buttonAgain": { ko: "다시 설명", en: "Explain again", ja: "もう一度説明" },
  "narrate.loading": { ko: "설명을 만드는 중…", en: "Writing an explanation…", ja: "説明を作成中…" },
  "narrate.hint": {
    ko: "직원 이름·단계 이름 같은 용어를 풀어 쓴 요약입니다. 모델 호출이라 비용이 듭니다.",
    en: "A plain-language summary — internal terms spelled out. This calls a model, so it costs a little.",
    ja: "専門用語をかみ砕いた要約です。モデル呼び出しのため少額の費用がかかります。",
  },

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
  "task.v.notRun": { ko: "미실행", en: "not run", ja: "未実行" },
  "task.v.testsCounts": {
    ko: "{passed}통과·{failed}실패",
    en: "{passed} passed · {failed} failed",
    ja: "{passed} 成功 · {failed} 失敗",
  },
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
  "proj.resume": { ko: "이어서 진행", en: "Resume", ja: "再開" },
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
  "proj.usageNone": {
    ko: "아직 아무도 부르지 않았습니다.",
    en: "No one has been called yet.",
    ja: "まだ誰も呼ばれていません。",
  },
  "proj.calls": { ko: "{n}회", en: "{n} calls", ja: "{n} 回" },
  // 영어에만 단수가 있다. "1 calls" 한 줄이 나머지 번역까지 기계가 쓴 것처럼
  // 보이게 만든다 — 레일의 "1 files" 와 같은 자리다.
  "proj.calls1": { ko: "1회", en: "1 call", ja: "1 回" },
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
  "handoff.recent": { ko: "최근 인계", en: "Recent handoffs", ja: "最近の引き継ぎ" },
  "handoff.system": { ko: "시스템", en: "System", ja: "システム" },
  "handoff.plan": {
    ko: "태스크 {n}개짜리 계획", en: "planned {n} tasks", ja: "タスク{n}件の計画",
  },
  "handoff.writeTests": {
    ko: "인수기준 {n}개 커버하는 테스트 작성",
    en: "wrote tests covering {n} criteria",
    ja: "受入基準{n}件をカバーするテストを作成",
  },
  "handoff.implement": { ko: "구현 완료", en: "implementation done", ja: "実装完了" },
  "handoff.reviewPass": { ko: "검토 통과", en: "review passed", ja: "レビュー合格" },
  "handoff.reviewFail": {
    ko: "지적 {n}건으로 반려", en: "rejected with {n} finding(s)", ja: "指摘{n}件で差し戻し",
  },
  "handoff.finalize": {
    ko: "인수기준 {n}개 충족 확인", en: "confirmed {n} criteria met", ja: "受入基準{n}件の充足を確認",
  },
  "office.hint": {
    ko: "자리를 가리키면 누가 무엇으로 일하는지 보입니다.",
    en: "Point at a seat to see who works there and on what.",
    ja: "席を指すと、誰が何で働いているかが見えます。",
  },
  "office.log": { ko: "작업 로그", en: "Activity log", ja: "作業ログ" },
  "office.logResize": {
    ko: "작업 로그 폭 조절", en: "Resize activity log", ja: "作業ログの幅を調整",
  },
  "rail.resize": {
    ko: "프로젝트 목록 폭 조절",
    en: "Resize project list",
    ja: "プロジェクト一覧の幅を調整",
  },
  "office.projects": { ko: "프로젝트", en: "Projects", ja: "プロジェクト" },
  "office.newProject": { ko: "새 프로젝트", en: "New project", ja: "新規プロジェクト" },
  "office.collapse": { ko: "목록 접기", en: "Collapse list", ja: "一覧を折りたたむ" },
  // 레일의 묶음 제목. 같은 날짜가 줄마다 반복되던 것을 제목 하나로 접었다.
  "rail.running": { ko: "진행 중", en: "Running", ja: "実行中" },
  "rail.today": { ko: "오늘", en: "Today", ja: "今日" },
  "rail.yesterday": { ko: "어제", en: "Yesterday", ja: "昨日" },
  "rail.earlier": { ko: "그 이전", en: "Earlier", ja: "それ以前" },
  "rail.files": { ko: "파일 {n}개", en: "{n} files", ja: "ファイル {n} 件" },
  // 영어에만 단수가 있다. "1 files" 는 기계가 쓴 티가 나는 문장이고,
  // 그런 줄이 하나 있으면 나머지 번역도 기계가 한 것처럼 읽힌다.
  "rail.file1": { ko: "파일 1개", en: "1 file", ja: "ファイル 1 件" },
  "rail.credits": { ko: "{n} 크레딧", en: "{n} cr", ja: "{n} クレジット" },
  // 로그 칸이 비어 있을 때 채우는 "지난 결과". 실행 전에는 이 칸이
  // 700px 짜리 빈 공간이었다.
  "recent.title": { ko: "지난 결과", en: "Recent results", ja: "これまでの結果" },
  "run.made": { ko: "만든 것", en: "Made so far", ja: "作ったもの" },
  "recent.score": { ko: "완성도", en: "Done", ja: "完成度" },
  "recent.none": {
    ko: "끝난 프로젝트가 아직 없습니다.",
    en: "No finished projects yet.",
    ja: "完了したプロジェクトはまだありません。",
  },
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
  // ── 사무실 개편 (DAY 25 · 사규) ────────────────────────────────
  "man.staffCards": {
    ko: "직원 카드 — 이름 · 채용 · 모델",
    en: "Staff cards — names, hiring, models",
    ja: "社員カード — 名前・雇用・モデル",
  },
  "office.floor.alt": {
    ko: "사무실 평면도. 부서마다 자리가 있고 위쪽에 대표실·회의실·비서실, 오른쪽에 휴게실이 있습니다. 직원의 테두리 색이 상태입니다.",
    en: "Office floor plan. Each team has a desk; the CEO room, meeting room and secretary's office are at the top, the lounge on the right. Each ring color is that person's state.",
    ja: "オフィスの平面図。部署ごとに席があり、上に社長室・会議室・秘書室、右に休憩室があります。枠の色が各社員の状態です。",
  },
  "office.ceo": { ko: "대표", en: "CEO", ja: "社長" },
  "office.secretary": { ko: "비서실", en: "Secretary", ja: "秘書室" },
  "office.self": { ko: "자율", en: "idle", ja: "自由" },
  "office.focusOn": { ko: "집중 모드", en: "Focus mode", ja: "集中モード" },
  "office.focusOff": { ko: "집중 모드 끔", en: "Focus off", ja: "集中モードオフ" },
  "office.scenario": { ko: "하루 시나리오", en: "The day's flow", ja: "一日のシナリオ" },
  "office.integrations": {
    ko: "연동 대기 {n}건 — 대표님이 연결해 주셔야 풀립니다",
    en: "{n} connection(s) needed — these unblock only when you connect them",
    ja: "連携待ち{n}件 — 社長が接続すると解消します",
  },
  "office.room.ceo": { ko: "대표실", en: "CEO", ja: "社長室" },
  "office.room.meeting": { ko: "회의실", en: "Meeting room", ja: "会議室" },
  "office.room.secretary": { ko: "비서실", en: "Secretary", ja: "秘書室" },
  "office.room.lounge": { ko: "휴게실", en: "Lounge", ja: "休憩室" },
  "office.room.entrance": { ko: "입구", en: "Entrance", ja: "入口" },
  "office.meeting.approval": {
    ko: "결재 대기 — {title}", en: "Awaiting approval — {title}", ja: "決裁待ち — {title}",
  },
  "office.meeting.call": { ko: "전체 회의 중", en: "All-hands meeting", ja: "全体会議中" },
  "office.meeting.handoff": { ko: "인수인계 중", en: "Handing over", ja: "引き継ぎ中" },
  "office.meeting.empty": { ko: "비어 있음", en: "Empty", ja: "空き" },
  "office.dept.strategy": { ko: "기획실", en: "Strategy", ja: "企画室" },
  "office.dept.dev": { ko: "개발팀", en: "Engineering", ja: "開発チーム" },
  "office.dept.qa": { ko: "검증팀", en: "Verification", ja: "検証チーム" },
  "office.dept.docs": { ko: "문서팀", en: "Docs", ja: "ドキュメント" },
  "office.dept.design": { ko: "디자인팀", en: "Design", ja: "デザイン" },
  "office.dept.etc": { ko: "기타", en: "Other", ja: "その他" },
  "office.dropHere": { ko: "여기로 옮기기", en: "Move here", ja: "ここへ移動" },
  "office.dragHint": {
    ko: "끌어서 다른 팀 칸에 놓으면 팀을 옮깁니다",
    en: "Drag onto another team's area to move them",
    ja: "別のチームの区画にドラッグすると異動します",
  },
  "office.card.team": { ko: "소속 팀", en: "Team", ja: "所属チーム" },
  "office.card.homeTeam": { ko: "처음 팀", en: "original", ja: "元のチーム" },
  "office.card.teamHint": {
    ko: "팀을 옮겨도 권한은 직함을 따릅니다 — 개발자는 문서팀에서도 src/ 에만 씁니다.",
    en: "Moving teams doesn't change permissions — a developer on the Docs team still writes only to src/.",
    ja: "チームを移っても権限は職務に従います — 開発者はドキュメントでも src/ にだけ書きます。",
  },
  "office.moved": {
    ko: "{name} → {team}",
    en: "{name} → {team}",
    ja: "{name} → {team}",
  },
  "office.state.done": { ko: "완료", en: "Done", ja: "完了" },
  "office.state.working": { ko: "진행 중", en: "Working", ja: "作業中" },
  "office.state.approval": { ko: "승인 대기", en: "Needs approval", ja: "承認待ち" },
  "office.state.integration": { ko: "연동 대기", en: "Needs connection", ja: "連携待ち" },
  "office.state.idle": { ko: "대기", en: "Waiting", ja: "待機" },
  "office.bubble.done": { ko: "완료했어요!", en: "All done!", ja: "完了しました!" },
  "office.bubble.working": { ko: "일하는 중…", en: "Working on it…", ja: "作業中…" },
  "office.bubble.approval": { ko: "확인해주세요", en: "Please review", ja: "確認してください" },
  "office.bubble.integration": { ko: "연결 기다려요", en: "Waiting for a connection", ja: "連携を待っています" },
  "office.bubble.idle": { ko: "업무 대기중", en: "Standing by", ja: "業務待機中" },
  "office.bubble.lounge": { ko: "잠깐 쉬는 중", en: "On a short break", ja: "ちょっと休憩中" },
  "office.step.arrive": { ko: "출근", en: "Clock in", ja: "出勤" },
  "office.step.plan": { ko: "기획", en: "Plan", ja: "企画" },
  "office.step.plan_gate": { ko: "계획 승인", en: "Plan approval", ja: "計画承認" },
  "office.step.tests": { ko: "테스트 선작성", en: "Tests first", ja: "テスト先行" },
  "office.step.implement": { ko: "구현", en: "Build", ja: "実装" },
  "office.step.pytest": { ko: "테스트 실행", en: "Run tests", ja: "テスト実行" },
  "office.step.review": { ko: "교차검증", en: "Cross-check", ja: "クロスチェック" },
  "office.step.task_gate": { ko: "결과 승인", en: "Result approval", ja: "成果承認" },
  "office.step.rework": { ko: "재작업", en: "Rework", ja: "やり直し" },
  "office.step.finalize": { ko: "최종 검수", en: "Final review", ja: "最終検収" },
  "office.step.saved": { ko: "결과 저장", en: "Saved", ja: "成果保存" },
  "office.step.brief": { ko: "비서실 브리핑", en: "Briefing", ja: "ブリーフィング" },
  "office.step.off": { ko: "꺼짐", en: "off", ja: "オフ" },
  "office.step.offHint": {
    ko: "이 승인 지점을 켜지 않았습니다 — 멈추지 않고 지나갑니다.",
    en: "This approval step is off — the run passes it without stopping.",
    ja: "この承認ポイントはオフです — 止まらずに通過します。",
  },
  "office.card.close": { ko: "닫기", en: "Close", ja: "閉じる" },
  "office.card.task": { ko: "맡은 일", en: "Task", ja: "担当" },
  "office.card.progress": { ko: "진행률", en: "Progress", ja: "進捗" },
  "office.card.cost": { ko: "쓴 돈", en: "Spent", ja: "費用" },
  "office.card.calls": { ko: "{n}회", en: "{n} calls", ja: "{n}回" },
  "office.card.latency": { ko: "평균 응답", en: "Avg. response", ja: "平均応答" },
  "office.card.fix": { ko: "연결하기", en: "Connect", ja: "接続する" },
  "office.card.catchphrase": { ko: "말버릇", en: "Catchphrases", ja: "口癖" },
  "office.catch.strategist.1": {
    ko: "기계가 판정 못 하는 기준은 기준이 아니에요.",
    en: "If a machine can't judge it, it isn't a criterion.",
    ja: "機械が判定できない基準は基準じゃありません。",
  },
  "office.catch.strategist.2": {
    ko: "태스크는 3~8개로 쪼갤게요.",
    en: "I'll break it into three to eight tasks.",
    ja: "タスクは3〜8個に分けます。",
  },
  "office.catch.developer.1": {
    ko: "tests/ 는 안 봐요. 인수기준을 봐요.",
    en: "I don't look at tests/. I look at the criteria.",
    ja: "tests/ は見ません。受け入れ基準を見ます。",
  },
  "office.catch.developer.2": {
    ko: "파일은 생략 없이 전문으로 냅니다.",
    en: "Files go out whole — no '...omitted...'.",
    ja: "ファイルは省略せず全文で出します。",
  },
  "office.catch.analyst.1": {
    ko: "설명 말고 원문을 볼게요.",
    en: "Skip the explanation — show me the source.",
    ja: "説明より原文を見ます。",
  },
  "office.catch.analyst.2": {
    ko: "근거 없는 반려는 안 해요.",
    en: "No rejection without evidence.",
    ja: "根拠のない差し戻しはしません。",
  },
  "office.catch.writer.1": {
    ko: "없는 기능은 안 써요.",
    en: "I don't write about features that don't exist.",
    ja: "ない機能は書きません。",
  },
  "office.catch.writer.2": {
    ko: "형용사보다 숫자예요.",
    en: "Numbers over adjectives.",
    ja: "形容詞より数字です。",
  },
  "office.catch.designer.1": {
    ko: "색은 이름 말고 값으로 적어요.",
    en: "Colors are values, not names.",
    ja: "色は名前ではなく値で書きます。",
  },
  "office.catch.designer.2": {
    ko: "비었을 때·불러올 때·실패할 때, 셋 다 그려요.",
    en: "Empty, loading, failed — I draw all three.",
    ja: "空・読み込み中・失敗、三つとも描きます。",
  },
  "approval.title": { ko: "대표 결정 필요", en: "Your decision needed", ja: "社長の決定が必要" },
  "approval.gate.plan": { ko: "계획 승인", en: "Plan approval", ja: "計画承認" },
  "approval.gate.task": { ko: "결과 승인", en: "Result approval", ja: "成果承認" },
  "approval.lowConfidence": { ko: "검증자 확신 낮음", en: "low verifier confidence", ja: "検証者の確信が低い" },
  "approval.held": { ko: "보류 중", en: "On hold", ja: "保留中" },
  "approval.prev": { ko: "이전 건", en: "Previous", ja: "前の件" },
  "approval.next": { ko: "다음 건", en: "Next", ja: "次の件" },
  "approval.count": { ko: "{i}/{n}건", en: "{i} of {n}", ja: "{i}/{n}件" },
  "approval.tasks": { ko: "태스크", en: "Tasks", ja: "タスク" },
  "approval.criteria": { ko: "인수기준", en: "Acceptance criteria", ja: "受け入れ基準" },
  "approval.by": { ko: "담당", en: "By", ja: "担当" },
  "approval.confidence": { ko: "검증자 확신도", en: "Verifier confidence", ja: "検証者の確信度" },
  "approval.confidenceHint": {
    ko: "검증자가 이 통과 판정을 얼마나 확신하는지입니다. 통과율과 다른 질문입니다.",
    en: "How sure the verifier is about this pass. A different question from the pass rate.",
    ja: "検証者がこの合格判定をどれだけ確信しているかです。合格率とは別の問いです。",
  },
  "approval.threshold": { ko: "(기준 {n}% 미만)", en: "(below the {n}% bar)", ja: "(基準{n}%未満)" },
  "approval.reworked": { ko: "반려 {n}회 끝에 통과", en: "passed after {n} rejection(s)", ja: "差し戻し{n}回の後に合格" },
  "approval.verifierSays": { ko: "검증자:", en: "Verifier:", ja: "検証者:" },
  "approval.files": { ko: "바뀐 파일", en: "Changed files", ja: "変更ファイル" },
  "approval.approve": { ko: "승인", en: "Approve", ja: "承認" },
  "approval.reject": { ko: "수정 요청", en: "Request changes", ja: "修正依頼" },
  "approval.hold": { ko: "보류", en: "Hold", ja: "保留" },
  "approval.discard": { ko: "폐기", en: "Discard", ja: "破棄" },
  "approval.cancel": { ko: "취소", en: "Cancel", ja: "キャンセル" },
  "approval.confirm.reject": { ko: "이 의견으로 돌려보내기", en: "Send back with this note", ja: "この意見で差し戻す" },
  "approval.confirm.hold": { ko: "보류하기", en: "Put on hold", ja: "保留する" },
  "approval.confirm.discard": { ko: "폐기 확정", en: "Confirm discard", ja: "破棄を確定" },
  "approval.rejectPlaceholder": {
    ko: "무엇을 고쳐야 하나요? 담당자에게 반려 사유로 그대로 전달됩니다.",
    en: "What should change? This goes to the assignee as the rejection reason, word for word.",
    ja: "何を直すべきですか?担当者に差し戻し理由としてそのまま伝わります。",
  },
  "approval.holdPlaceholder": {
    ko: "메모(선택) — 실행은 결정할 때까지 쉽니다.",
    en: "Note (optional) — the run rests until you decide.",
    ja: "メモ(任意) — 決めるまで実行は休みます。",
  },
  "approval.needComment": {
    ko: "무엇을 고칠지 적어주세요. 사유 없는 반려는 같은 결과를 한 번 더 삽니다.",
    en: "Say what to fix. A rejection without a reason buys the same result again.",
    ja: "直す点を書いてください。理由のない差し戻しは同じ結果をもう一度買います。",
  },
  "approval.discardPlanWarn": {
    ko: "계획을 폐기하면 실행이 멈춥니다. 되돌릴 수 없습니다.",
    en: "Discarding the plan stops the run. This can't be undone.",
    ja: "計画を破棄すると実行が止まります。元に戻せません。",
  },
  "approval.discardTaskWarn": {
    ko: "이 태스크가 만든 파일을 시작 전으로 되돌리고 계획에서 뺍니다. 나머지는 계속합니다. 되돌릴 수 없습니다.",
    en: "Reverts the files this task made and drops it from the plan. The rest continues. This can't be undone.",
    ja: "このタスクが作ったファイルを開始前に戻し、計画から外します。残りは続行します。元に戻せません。",
  },
  "approval.heldNote": {
    ko: "보류했습니다. 결정하실 때까지 실행은 쉽니다 — 좌석은 쓰지 않습니다.",
    en: "On hold. The run rests until you decide — it doesn't use a seat.",
    ja: "保留しました。決めるまで実行は休みます — 枠は使いません。",
  },
  "approval.resumed": { ko: "결정했습니다. 바로 이어서 진행합니다.", en: "Decided. Continuing now.", ja: "決定しました。すぐに続けます。" },
  "approval.recorded": {
    ko: "결정을 기록했습니다. 실행이 다음 확인 때 반영합니다.",
    en: "Decision recorded. The run picks it up at its next check.",
    ja: "決定を記録しました。実行は次の確認時に反映します。",
  },
  "approval.notResumed": {
    ko: "결정은 기록했지만 지금 바로 이어가지 못했습니다: {note}",
    en: "Decision recorded, but it couldn't resume right now: {note}",
    ja: "決定は記録しましたが、すぐには再開できませんでした: {note}",
  },
  "cmd.title": { ko: "대표 지시창", en: "Ask the office", ja: "社長の指示窓" },
  "cmd.hint": {
    ko: "기록을 읽어 답합니다 — 모델을 부르지 않아 무료입니다",
    en: "Answers come from the records — no model call, no cost",
    ja: "記録を読んで答えます — モデルを呼ばないので無料です",
  },
  "cmd.empty": {
    ko: "아래 단추를 누르거나 직접 물어보세요.",
    en: "Tap a button below or ask in your own words.",
    ja: "下のボタンを押すか、直接聞いてください。",
  },
  "cmd.thinking": { ko: "기록 확인 중…", en: "Checking the records…", ja: "記録を確認中…" },
  "cmd.placeholder": {
    ko: "예: 왜 늦어져? · 박도현 뭐해? · 승인할게",
    en: "e.g. why so slow? · what is the designer doing? · approve it",
    ja: "例: なぜ遅い? · 開発者は何してる? · 承認します",
  },
  "cmd.send": { ko: "보내기", en: "Send", ja: "送信" },
  "cmd.status": { ko: "현황 보고", en: "Status report", ja: "現況報告" },
  "cmd.why": { ko: "왜 늦어져?", en: "Why so slow?", ja: "なぜ遅い?" },
  "cmd.meeting": { ko: "회의 소집", en: "Call a meeting", ja: "会議招集" },
  "cmd.brief": { ko: "지금 브리핑", en: "Brief me now", ja: "今ブリーフィング" },
  "cmd.focus": { ko: "집중 모드", en: "Focus mode", ja: "集中モード" },
  "cmd.unfocus": { ko: "집중 모드 해제", en: "Focus mode off", ja: "集中モード解除" },
  "cmd.approve": { ko: "승인할게", en: "Approve it", ja: "承認します" },
  "cmd.whois": { ko: "{name} 뭐해?", en: "What is {name} doing?", ja: "{name}は何してる?" },
  "gate.title": { ko: "★ 대표 승인 지점 — 켠 곳에서 멈춰 기다립니다", en: "★ Approval steps — the run stops and waits at the ones you turn on", ja: "★ 社長承認ポイント — オンにした所で止まって待ちます" },
  "gate.liveTitle": {
    ko: "★ 대표 승인 지점 — 바꾸면 다음 지점부터 적용됩니다",
    en: "★ Approval steps — changes apply from the next step",
    ja: "★ 社長承認ポイント — 変更は次のポイントから適用されます",
  },
  "gate.panel": { ko: "대표 승인 지점", en: "Approval steps", ja: "社長承認ポイント" },
  "gate.legend": { ko: "승인 지점", en: "Approval steps", ja: "承認ポイント" },
  "gate.plan": { ko: "계획 승인", en: "Approve the plan", ja: "計画を承認" },
  "gate.planHint": {
    ko: "계획이 서면 테스트를 쓰기 전에 멈춥니다. 방향이 틀리면 돈을 쓰기 전에 고칩니다.",
    en: "Stops after planning, before any tests are written — fix the direction before money is spent.",
    ja: "計画ができたらテスト作成前に止まります。方向が違えばお金を使う前に直せます。",
  },
  "gate.task": { ko: "모든 결과 승인", en: "Approve every result", ja: "全成果を承認" },
  "gate.taskHint": {
    ko: "검증을 통과한 태스크마다 완료로 치기 전에 멈춥니다.",
    en: "Stops on every task that passed review, before it counts as done.",
    ja: "検証を通過したタスクごとに、完了扱いにする前に止まります。",
  },
  "gate.taskDev": { ko: "코드만 승인", en: "Approve code only", ja: "コードのみ承認" },
  "gate.taskDevHint": {
    ko: "개발자의 태스크만 멈춥니다 — 결제·배포 코드처럼 꼭 보고 싶은 것만.",
    en: "Stops only on the developer's tasks — for code you must see, like payments or deploys.",
    ja: "開発者のタスクだけ止まります — 決済やデプロイのように必ず見たいコード向け。",
  },
  "gate.confidence": { ko: "확신 낮을 때만", en: "Only when unsure", ja: "確信が低い時だけ" },
  "gate.confidenceHint": {
    ko: "통과했지만 검증자가 스스로 자신 없다고 한 태스크만 멈춥니다.",
    en: "Stops only on passes the verifier itself wasn't sure about.",
    ja: "合格でも検証者自身が自信がないとしたタスクだけ止まります。",
  },
  "list.awaiting": { ko: "승인 대기", en: "Awaiting approval", ja: "承認待ち" },
  "log.confidence": { ko: "확신도 {n}%", en: "confidence {n}%", ja: "確信度 {n}%" },
  "task.awaiting": { ko: "대표 승인 대기", en: "Awaiting approval", ja: "承認待ち" },
  "task.k.confidence": { ko: "검증 확신도", en: "Verifier confidence", ja: "検証の確信度" },
  "task.confidenceHint": {
    ko: "검증자가 자기 판정을 얼마나 확신했는지의 평균입니다. 통과율과 같이 낮으면 검증 자체가 흔들린다는 뜻입니다.",
    en: "Average of how sure the verifier was of its own verdicts. If this and the pass rate are both low, the review itself is shaky.",
    ja: "検証者が自分の判定をどれだけ確信していたかの平均です。合格率と一緒に低ければ、検証そのものが揺らいでいます。",
  },
  "task.lowConfidence": { ko: "사람 확인 권장", en: "human check advised", ja: "人の確認を推奨" },
  "proj.awaiting": {
    ko: "대표님 결재를 기다리며 쉬고 있습니다. 아래 결재함에서 결정하시면 바로 이어갑니다.",
    en: "Resting until you decide. Decide in the box below and it continues right away.",
    ja: "社長の決裁を待って休んでいます。下の決裁箱で決めるとすぐに続きます。",
  },
  "proj.resumeFrom": {
    ko: "재개하면 끝난 태스크 {n}/{total}개는 다시 하지 않고 이어갑니다.",
    en: "Resuming skips the {n}/{total} task(s) already done.",
    ja: "再開すると、完了済みのタスク{n}/{total}件はやり直さずに続けます。",
  },
  "proj.resumeFromStart": {
    ko: "계획이 서기 전에 멈췄습니다 — 재개하면 같은 프로젝트에서 계획부터 다시 합니다.",
    en: "It stopped before a plan existed — resuming plans again, in this same project.",
    ja: "計画ができる前に止まりました — 再開すると同じプロジェクトで計画からやり直します。",
  },
  "proj.resumeHint": {
    ko: "마지막 체크포인트에서 이어갑니다 (완료 {n}개)",
    en: "Continues from the last checkpoint ({n} done)",
    ja: "最後のチェックポイントから続けます(完了{n}件)",
  },
  "perm.title": { ko: "이 프로젝트의 권한", en: "Permissions for this project", ja: "このプロジェクトの権限" },
  "perm.employee": { ko: "직원", en: "Employee", ja: "社員" },
  "perm.role.strategist": { ko: "전략가", en: "Strategist", ja: "ストラテジスト" },
  "perm.role.developer": { ko: "개발자", en: "Developer", ja: "開発者" },
  "perm.role.analyst": { ko: "분석가", en: "Analyst", ja: "アナリスト" },
  "perm.role.writer": { ko: "작가", en: "Writer", ja: "ライター" },
  "perm.role.designer": { ko: "디자이너", en: "Designer", ja: "デザイナー" },
  "perm.lock.writes": {
    ko: "바꿀 수 없는 칸입니다 — 검증자 외에는 tests/ 에 못 쓰고, 검증자는 tests/ 에만 쓰며, 전략가는 쓰지 않습니다.",
    en: "Locked — only the verifier writes tests/, the verifier writes nothing else, and the strategist writes nothing.",
    ja: "変更できません — tests/ に書けるのは検証者だけ、検証者は tests/ にしか書けず、ストラテジストは書きません。",
  },
  "perm.lock.reads": {
    ko: "바꿀 수 없는 칸입니다 — 검증자의 읽기는 줄일 수 없습니다(못 보는 것을 검증할 수 없습니다).",
    en: "Locked — the verifier's reads can't be reduced (it can't verify what it can't see).",
    ja: "変更できません — 検証者の読み取りは減らせません(見えないものは検証できません)。",
  },
  "perm.riskCell": {
    ko: "켜면 구현자가 테스트를 보고 맞춰 짤 수 있어 교차검증이 약해집니다.",
    en: "Turning this on lets the implementer code to the tests, weakening the cross-check.",
    ja: "オンにすると実装者がテストに合わせて書けるため、クロスチェックが弱まります。",
  },
  "perm.riskActive": {
    ko: "이 프로젝트는 구현자가 tests/ 를 읽을 수 있습니다 — 교차검증이 약해진 상태입니다.",
    en: "In this project an implementer can read tests/ — cross-checking is weakened.",
    ja: "このプロジェクトでは実装者が tests/ を読めます — クロスチェックが弱まっています。",
  },
  "perm.legend": {
    ko: "R 읽기 · W 쓰기 · 흐린 칸은 잠김(제품 규칙) · 노란 칸은 위험 · • 는 기본값에서 바뀜",
    en: "R read · W write · faded = locked (product rule) · amber = risky · • = changed from default",
    ja: "R 読み取り · W 書き込み · 薄い欄はロック(製品ルール) · 黄色は危険 · • は既定から変更",
  },
  "perm.running": {
    ko: "실행이 도는 동안은 바꿀 수 없습니다 — 멈추거나 결재를 기다릴 때 바꾸세요.",
    en: "Can't change while the run is active — change it while stopped or awaiting approval.",
    ja: "実行中は変更できません — 停止中か承認待ちの時に変更してください。",
  },
  "perm.ack": {
    ko: "구현자가 테스트를 보면 교차검증이 약해진다는 것을 알고 켭니다.",
    en: "I understand letting the implementer see the tests weakens the cross-check.",
    ja: "実装者がテストを見るとクロスチェックが弱まることを理解した上でオンにします。",
  },
  "perm.save": { ko: "저장", en: "Save", ja: "保存" },
  "perm.discard": { ko: "되돌리기", en: "Undo changes", ja: "元に戻す" },
  "perm.reset": { ko: "기본값으로", en: "Reset to default", ja: "既定に戻す" },
  "metrics.title": { ko: "왜 느린가 — 시간", en: "Why is it slow — timing", ja: "なぜ遅いか — 時間" },
  "metrics.none": { ko: "아직 모델 호출이 없습니다.", en: "No model calls yet.", ja: "まだモデル呼び出しがありません。" },
  "metrics.wall": { ko: "걸린 시간", en: "Elapsed", ja: "所要時間" },
  "metrics.model": { ko: "모델 시간 합", en: "Model time (sum)", ja: "モデル時間の合計" },
  "metrics.parallel": { ko: "동시에 일한 정도", en: "Parallelism", ja: "並行度" },
  "metrics.parallelHint": {
    ko: "모델 시간 합 ÷ 걸린 시간(결재 대기 제외). 1을 넘으면 여러 직원이 실제로 동시에 일했습니다.",
    en: "Model time ÷ elapsed (minus approval waits). Above 1 means several employees really worked at once.",
    ja: "モデル時間 ÷ 所要時間(決裁待ちを除く)。1を超えると複数の社員が実際に同時に働いています。",
  },
  "metrics.humanWait": { ko: "대표 결재 대기", en: "Waiting on you", ja: "社長の決裁待ち" },
  "metrics.waiting": { ko: "{who} — 응답 대기 중 ({model})", en: "{who} — waiting for the model ({model})", ja: "{who} — 応答待ち ({model})" },
  "metrics.byPhase": { ko: "단계별 시간", en: "Time by step", ja: "段階別の時間" },
  "metrics.phase.PLAN": { ko: "기획", en: "Plan", ja: "企画" },
  "metrics.phase.REPLAN": { ko: "재기획", en: "Re-plan", ja: "再計画" },
  "metrics.phase.WRITE_TESTS": { ko: "테스트 선작성", en: "Tests first", ja: "テスト先行" },
  "metrics.phase.IMPLEMENT": { ko: "구현", en: "Build", ja: "実装" },
  "metrics.phase.TEST": { ko: "pytest", en: "pytest", ja: "pytest" },
  "metrics.phase.REVIEW": { ko: "교차검증", en: "Cross-check", ja: "クロスチェック" },
  "metrics.phase.FINALIZE": { ko: "최종 검수", en: "Final review", ja: "最終検収" },
  "metrics.phase.AWAITING": { ko: "결재 대기", en: "Awaiting you", ja: "決裁待ち" },
  "metrics.who": { ko: "직원", en: "Employee", ja: "社員" },
  "metrics.calls": { ko: "호출", en: "Calls", ja: "呼び出し" },
  "metrics.avg": { ko: "평균", en: "Avg", ja: "平均" },
  "metrics.wait": { ko: "대기", en: "Waited", ja: "待機" },
  "metrics.waitHint": {
    ko: "요청 한도에 걸려 기다리기만 한 시간입니다. 모델이 느린 것과 대응이 다릅니다.",
    en: "Time spent only waiting out rate limits — a different fix from a slow model.",
    ja: "リクエスト上限で待っていただけの時間です。モデルが遅いのとは対処が違います。",
  },
  "metrics.retries": { ko: "재시도", en: "Retries", ja: "再試行" },
  "metrics.slowest": { ko: "가장 오래 걸린 호출", en: "Slowest calls", ja: "最も時間のかかった呼び出し" },
  "metrics.attempts": { ko: "{n}번 시도", en: "{n} attempts", ja: "{n}回試行" },
  // ── 설명 탭 (DAY 26 · app/guide) ──────────────────────────────────
  // 로그인한 사람이 "이 제품이 무엇을 어떻게 하나"를 읽는 곳. 랜딩은 로그인
  // 전에만 보이고(로컬에서는 아예 안 보인다), 사무실은 설명하지 않는다.
  // 역할·상태·승인 지점·지시 문구는 **새로 쓰지 않고** 사무실의 키를 그대로
  // 쓴다 — 설명과 화면의 말이 어긋나면 설명이 거짓말이 된다.
  "guide.badge": { ko: "처음 오셨다면 여기부터", en: "New here? Start here", ja: "初めての方はここから" },
  "guide.title": { ko: "AI COMPANY 는 이렇게 일합니다", en: "How AI COMPANY works", ja: "AI COMPANY の働き方" },
  "guide.lead": {
    ko: "당신은 대표이고, AI 직원 다섯이 한 팀으로 일합니다. 요구사항 한 줄을 맡기면 {strong} 만든 것은 파일로 남고, 누가 몇 번째에 왜 고쳤는지까지 따라갈 수 있습니다.",
    en: "You're the CEO, and five AI employees work as one team. Hand over a one-line requirement and {strong} Everything they make is saved as files, and you can trace who changed what, in which round, and why.",
    ja: "あなたは社長で、AI 社員 5 名が一つのチームとして働きます。要件を一行渡せば{strong}作ったものはファイルとして残り、誰が何回目に、なぜ直したかまで追えます。",
  },
  "guide.lead.strong": {
    ko: "기획 → 테스트 선작성 → 구현 → 교차검증 → 최종 검수까지 끝까지 돕니다.",
    en: "it runs all the way through planning → tests first → building → cross-checking → final review.",
    ja: "企画 → テスト先行 → 実装 → クロス検証 → 最終検収まで最後まで進みます。",
  },
  "guide.toc": { ko: "이 페이지", en: "On this page", ja: "このページ" },
  "guide.tab.intro": { ko: "소개", en: "Intro", ja: "紹介" },
  "guide.tab.flow": { ko: "흐름", en: "Flow", ja: "流れ" },
  "guide.tab.staff": { ko: "직원", en: "Team", ja: "社員" },
  "guide.tab.gates": { ko: "대표 승인", en: "Approvals", ja: "社長承認" },
  "guide.tab.office": { ko: "사무실", en: "Office", ja: "オフィス" },
  "guide.tab.money": { ko: "돈", en: "Money", ja: "お金" },
  "guide.tab.safety": { ko: "안전장치", en: "Safeguards", ja: "安全装置" },
  "guide.tab.honest": { ko: "지금 상태", en: "Status", ja: "現状" },
  "guide.prev": { ko: "이전", en: "Previous", ja: "前へ" },
  "guide.next": { ko: "다음", en: "Next", ja: "次へ" },
  "guide.navHint": {
    ko: "← → 키 · 옆으로 끌기 · 휠로도 넘어갑니다",
    en: "Arrow keys, dragging sideways or the wheel also work",
    ja: "← → キー・横ドラッグ・ホイールでも移動できます",
  },
  "guide.flow.title": { ko: "일이 흘러가는 순서", en: "How a job flows", ja: "仕事の流れ" },
  "guide.flow.lead": {
    ko: "순서는 모델이 아니라 코드가 정합니다. 그래서 '왜 저 직원을 불렀나'에 언제나 답할 수 있고, 끝없이 돌지 않습니다.",
    en: "Code — not a model — decides the order. You can always answer 'why was that employee called?', and it never loops forever.",
    ja: "順序はモデルではなくコードが決めます。だから「なぜその社員を呼んだのか」にいつでも答えられ、終わりなく回ることもありません。",
  },
  "guide.step.1": { ko: "기획", en: "Plan", ja: "企画" },
  "guide.step.1.body": {
    ko: "전략가가 요구사항을 기계가 판정할 수 있는 인수기준과 태스크로 나눕니다. 태스크마다 담당자와 쓸 파일이 정해집니다.",
    en: "The strategist turns the requirement into acceptance criteria a machine can check, and splits the work into tasks — each with an owner and the files it will write.",
    ja: "ストラテジストが要件を機械で判定できる受け入れ基準とタスクに分けます。タスクごとに担当者と書くファイルが決まります。",
  },
  "guide.step.2": { ko: "테스트 먼저", en: "Tests first", ja: "テスト先行" },
  "guide.step.2.body": {
    ko: "분석가가 구현보다 먼저 테스트를 씁니다. 개발자는 이 테스트를 읽을 수 없습니다 — 테스트에 맞춘 코드가 아니라 기준을 만족하는 코드를 쓰게 하려고요.",
    en: "The analyst writes the tests before anything is built. The developer can't read them — so the code meets the criteria instead of just passing the tests.",
    ja: "アナリストが実装より先にテストを書きます。開発者はこのテストを読めません — テストに合わせたコードではなく、基準を満たすコードを書かせるためです。",
  },
  "guide.step.3": { ko: "구현", en: "Build", ja: "実装" },
  "guide.step.3.body": {
    ko: "개발자·작가·디자이너가 맡은 태스크를 합니다. 서로 기대지 않고 쓰는 파일도 겹치지 않는 태스크는 동시에 돕니다.",
    en: "The developer, writer and designer do their tasks. Tasks that don't depend on each other and don't touch the same files run at the same time.",
    ja: "開発者・ライター・デザイナーが担当タスクを行います。互いに依存せず、書くファイルも重ならないタスクは同時に進みます。",
  },
  "guide.step.4": { ko: "테스트 실행", en: "Run the tests", ja: "テスト実行" },
  "guide.step.4.body": {
    ko: "오케스트레이터가 격리된 환경에서 pytest 를 직접 돌립니다. 결과는 직원의 말이 아니라 실행 기록입니다.",
    en: "The orchestrator runs pytest itself in an isolated environment. The result is an execution record, not an employee's claim.",
    ja: "オーケストレーターが隔離環境で pytest を自ら実行します。結果は社員の言葉ではなく実行記録です。",
  },
  "guide.step.5": { ko: "교차검증", en: "Cross-check", ja: "クロス検証" },
  "guide.step.5.body": {
    ko: "구현한 쪽과 다른 회사의 모델이 원문과 기준만 보고 판정합니다. 반려되면 사유와 함께 담당자에게 돌아가고, 세 번 넘게 반려되면 되돌린 뒤 계획을 다시 세웁니다.",
    en: "A model from a different company than the builder judges the work from the source and the criteria alone. A rejection goes back to the owner with reasons; after three, the work is rolled back and re-planned.",
    ja: "実装側とは別の会社のモデルが、原文と基準だけを見て判定します。差し戻しは理由とともに担当者へ戻り、3 回を超えると元に戻して計画し直します。",
  },
  "guide.step.6": { ko: "최종 검수", en: "Final review", ja: "最終検収" },
  "guide.step.6.body": {
    ko: "전략가가 인수기준을 하나씩 대조해 무엇이 충족됐고 무엇이 남았는지 보고합니다.",
    en: "The strategist checks each acceptance criterion and reports what was met and what wasn't.",
    ja: "ストラテジストが受け入れ基準を一つずつ照合し、何が満たされ何が残ったかを報告します。",
  },
  "guide.modes.title": { ko: "일을 맡기는 두 가지 방법", en: "Two ways to hand over work", ja: "仕事の任せ方は二つ" },
  "guide.auto.body": {
    ko: "요구사항 한 줄이면 위 순서를 끝까지 돕니다. 멈춰서 직접 보고 싶은 지점만 켜 두세요.",
    en: "One line and it runs the whole flow above. Just turn on the points where you want it to stop for you.",
    ja: "要件一行で上の流れを最後まで進めます。止めて自分で確認したい所だけオンにしてください。",
  },
  "guide.manual.body": {
    ko: "직원을 골라 한 마디씩 직접 시킵니다. 원할 때 검증을 부탁할 수 있고, 권한 경계는 AUTO 와 같습니다.",
    en: "Pick an employee and give instructions one at a time. Ask for a review whenever you like; the permission limits are the same as in AUTO.",
    ja: "社員を選んで一言ずつ直接指示します。必要な時に検証を頼め、権限の境界は AUTO と同じです。",
  },
  "guide.writes": { ko: "쓰는 곳", en: "Writes to", ja: "書き込み先" },
  "guide.writes.none": { ko: "쓰지 않음 — 계획만", en: "nothing — plans only", ja: "書かない — 計画のみ" },
  "guide.teams": {
    ko: "사무실에서 직원을 끌어 다른 팀 칸에 놓으면 팀을 옮길 수 있습니다.",
    en: "On the office floor you can drag an employee onto another team's area to move them.",
    ja: "オフィスでは社員を別のチームの区画にドラッグすると異動できます。",
  },
  "guide.gates.title": { ko: "대표가 끼어드는 지점", en: "Where the CEO steps in", ja: "社長が介入するポイント" },
  "guide.gates.lead": {
    ko: "켜 둔 지점에서만 멈춥니다. 기다리는 동안 실행은 쉬고 동시 실행 좌석도 쓰지 않으며, 결정하면 멈춘 곳에서 이어갑니다.",
    en: "It stops only at the points you turn on. While it waits, the run rests and doesn't hold a concurrent-run seat; once you decide, it continues from where it stopped.",
    ja: "オンにしたポイントでのみ止まります。待つ間、実行は休み同時実行枠も使いません。決定すると止まった所から続きます。",
  },
  "guide.decide.title": { ko: "결정은 네 가지", en: "Four decisions", ja: "決定は四つ" },
  "guide.decide.approve": { ko: "다음으로 넘어갑니다.", en: "Moves on to the next step.", ja: "次へ進みます。" },
  "guide.decide.reject": {
    ko: "의견을 반려 사유로 담당자에게 돌려줍니다. 의견 없이는 할 수 없습니다.",
    en: "Sends your comment back to the owner as the reason for rework. A comment is required.",
    ja: "意見を差し戻し理由として担当者へ返します。意見なしではできません。",
  },
  "guide.decide.hold": {
    ko: "아무것도 하지 않고 열어 둡니다. 비서실이 따로 챙깁니다.",
    en: "Does nothing and leaves it open. The secretary keeps track of it.",
    ja: "何もせず開いたままにします。秘書室が別途管理します。",
  },
  "guide.decide.discard": {
    ko: "계획이면 실행을 멈추고, 태스크면 그 태스크가 건드린 파일을 되돌리고 뺀 뒤 나머지를 계속합니다.",
    en: "For a plan, stops the run. For a task, rolls back the files it touched, drops it, and carries on with the rest.",
    ja: "計画なら実行を止め、タスクならそのタスクが触ったファイルを戻して外し、残りを続けます。",
  },
  "guide.office.title": { ko: "사무실 읽는 법", en: "Reading the office", ja: "オフィスの見方" },
  "guide.office.lead": {
    ko: "직원마다 상태 하나와 그 이유 한 줄이 붙습니다. 상태는 기록을 보고 서버가 정합니다.",
    en: "Every employee shows one status and a one-line reason. The server decides the status from the records.",
    ja: "社員ごとに状態が一つと理由が一行付きます。状態は記録をもとにサーバーが決めます。",
  },
  "guide.state.done": { ko: "맡은 일을 끝냈습니다.", en: "Finished the assigned work.", ja: "担当の仕事を終えました。" },
  "guide.state.working": {
    ko: "지금 모델이 일하는 중입니다 — 몇 초째인지 보입니다.",
    en: "A model is working right now — you can see for how many seconds.",
    ja: "今モデルが作業中です — 何秒目かが見えます。",
  },
  "guide.state.approval": {
    ko: "대표의 결정을 기다리며 회의실에 있습니다.",
    en: "Waiting in the meeting room for your decision.",
    ja: "社長の決定を待って会議室にいます。",
  },
  "guide.state.integration": {
    ko: "키가 연결되지 않아 Mock 대본이 대신 일합니다.",
    en: "No key is connected, so a Mock script works in its place.",
    ja: "キーが未接続のため Mock の台本が代わりに働きます。",
  },
  "guide.state.idle": {
    ko: "할 일이 없습니다 — 가끔 휴게실에 들릅니다.",
    en: "Nothing to do — sometimes drops by the lounge.",
    ja: "やることがありません — ときどき休憩室に寄ります。",
  },
  "guide.office.commands": {
    ko: "대표 지시창에서 이렇게 물어보세요",
    en: "Ask the office like this",
    ja: "社長の指示窓でこう聞いてみてください",
  },
  "guide.money.title": { ko: "돈은 이렇게 셉니다", en: "How money is counted", ja: "お金の数え方" },
  "guide.money.credits": {
    ko: "모델을 부를 때마다 실제로 쓴 토큰만큼 크레딧이 줄어듭니다. 직원별로 얼마를 썼는지 보입니다.",
    en: "Every model call takes credits for the tokens actually used. You can see how much each employee spent.",
    ja: "モデルを呼ぶたびに実際に使ったトークン分のクレジットが減ります。社員ごとの使用額が見えます。",
  },
  "guide.money.before": {
    ko: "상한은 호출하기 전에 검사합니다 — 다음 호출의 최악 비용까지 더해서 넘으면 부르기 전에 멈춥니다.",
    en: "Limits are checked before each call — if the worst-case cost of the next call would go over, it stops before calling.",
    ja: "上限は呼び出しの前に確認します — 次の呼び出しの最悪コストを足して超えるなら、呼ぶ前に止まります。",
  },
  "guide.money.plans": {
    ko: "요금제를 올리면 차이만큼 크레딧이 더해지고, 내리거나 되돌아가면 더해지지 않습니다.",
    en: "Upgrading your plan adds only the difference in credits; downgrading or switching back adds nothing.",
    ja: "プランを上げると差額分だけクレジットが増え、下げたり戻したりしても増えません。",
  },
  "guide.money.byok": {
    ko: "자체 키(BYOK) 요금제에서는 여러분의 키로 부르고 비용은 제공자가 직접 청구합니다 — 크레딧이 줄지 않습니다.",
    en: "On the bring-your-own-key plan, calls use your key and the provider bills you directly — no credits are spent.",
    ja: "自前キー（BYOK）プランではあなたのキーで呼び出し、費用はプロバイダーが直接請求します — クレジットは減りません。",
  },
  "guide.cta.title": { ko: "시작해 볼까요?", en: "Ready to start?", ja: "始めてみましょうか？" },
  "guide.cta.office": { ko: "사무실로 가기", en: "Go to the office", ja: "オフィスへ" },
  "guide.cta.pricing": { ko: "요금제 보기", en: "See pricing", ja: "料金を見る" },
  "guide.cta.keys": { ko: "API 키 연결하기", en: "Connect API keys", ja: "API キーを接続" },
} satisfies Record<string, Entry>;

export type Key = keyof typeof S;

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key, vars?: Record<string, string | number>) => string;
};

const LangContext = createContext<Ctx | null>(null);

/**
 * 처음 오는 사람에게 보일 언어. 기본은 **영어**다 — 브라우저 언어를
 * 따라가면 한국어 브라우저에서 매번 한국어로 열려서, 정작 "기본은
 * 영어여야 한다"는 요구와 어긋난다. 저장된 선택(localStorage)이 있으면
 * 그게 항상 이긴다 — 이 함수는 그마저 없을 때만 불린다.
 */
function detect(): Lang {
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

// 서버에는 브라우저 설정도 저장소도 없다. 기본 언어(영어)로 그린다.
function serverSnapshot(): Lang {
  return "en";
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
    // 제공자 밖에서도 화면이 죽지 않게 기본 언어로 답한다. 번역이 빠진 것은
    // 불편이지만, 여기서 던지면 그 화면 전체가 사라진다.
    return {
      lang: "en",
      setLang: () => {},
      t: (key) => (S[key] as Entry | undefined)?.en ?? String(key),
    };
  }
  return ctx;
}

/**
 * 잡은 오류를 **화면에 쓸 문장**으로 바꾼다 (DAY 22).
 *
 * 화면 16곳이 `e instanceof Error ? e.message : String(e)` 를 각자 쓰고
 * 있었다. 그 자체는 맞지만, 백엔드에 닿지 못한 경우에 문제가 된다 —
 * 그 문장은 React 밖(`lib/api.ts`)에서 만들어지므로 사용자가 고른 언어를
 * 모른다. 영어로 쓰는 사람에게 한국어 한 줄이 튀어나오던 마지막 자리였다.
 *
 * 그래서 문장은 여기서 고른다. 서버가 보낸 문장은 이미 `Accept-Language`
 * 를 보고 온 것이므로 그대로 쓴다 — 두 번 번역하지 않는다.
 */
export function useErrorText(): (e: unknown) => string {
  const { t } = useLang();
  return useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.isOffline) return t("auth.noBackend");
      return e instanceof Error ? e.message : String(e);
    },
    [t],
  );
}

// 요금제 이름은 **서버가 언어에 맞춰 보낸다**(backend/app/usage/credits.py
// 의 `localized()`). 화면에도 같은 표를 두면 값이 두 곳에 살게 되고,
// 요금제를 하나 추가할 때 두 곳을 고쳐야 한다. 여기에는 두지 않는다.
