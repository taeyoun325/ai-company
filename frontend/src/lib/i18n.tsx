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
 * 지금 번역된 것은 **로그인 이전 화면과 요금제·사무실**이다. 프로젝트
 * 상세·설정·MANUAL 화면, 그리고 **서버가 보내는 문장(오류·직원 대사)**
 * 은 아직 한국어다. 반쯤 번역된 제품에서 제일 나쁜 것은 어디까지
 * 번역됐는지 모르는 것이므로, 언어를 고르면 그 사실을 한 줄로 알린다.
 * 다 번역되면 그 줄을 지운다.
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
    en: "Some screens (project detail, settings, and messages from the server) are still Korean.",
    ja: "一部の画面（プロジェクト詳細・設定・サーバーからのメッセージ）はまだ韓国語です。",
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
  "plan.starter": { ko: "스타터", en: "Starter", ja: "スターター" },
  "plan.pro": { ko: "프로", en: "Pro", ja: "プロ" },
  "plan.business": { ko: "비즈니스", en: "Business", ja: "ビジネス" },
  "plan.byok": { ko: "자체 키", en: "Bring your own key", ja: "自前キー" },
  "plan.none": { ko: "요금제 없음", en: "No plan", ja: "プランなし" },
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

/** 요금제 키 → 번역된 이름. 표에 없으면 서버가 보낸 이름을 쓴다. */
export function planName(
  t: Ctx["t"], key: string, fallback: string,
): string {
  const id = `plan.${key}` as Key;
  return id in S ? t(id) : fallback;
}
