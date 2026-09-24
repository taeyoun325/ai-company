/**
 * 백엔드가 내려주는 모양 (지시서 §7 §8 §9 §12 §13).
 *
 * 손으로 적은 타입이므로 백엔드와 어긋날 수 있다. 어긋나면 화면이
 * 조용히 빈칸을 그리는 대신 터지게 두는 편이 낫다 — 그래야 고쳐진다.
 * 그래서 옵셔널을 남발하지 않았다.
 */

export type EmployeeId =
  | "strategist"
  | "developer"
  | "analyst"
  | "writer"
  | "designer";

export interface UsageRow {
  input: number;
  output: number;
  cached: number;
  cache_written: number;
  cost: number;
  calls: number;
}

export interface Employee {
  id: string;
  name: string;
  role: string;
  provider: string;
  model: string;
  kind: "plan" | "build" | "verify" | "write" | "design";
  desc: string;
  writes: string[];
  reads: string[];
  tools: string[];
  /** 지금 이 직원이 Mock 으로 일하고 있는가. 화면이 반드시 표시해야 한다. */
  mock: boolean;
  usage: Partial<UsageRow>;
  system?: string;
  worst_case_usd?: number;
  // ── 인사 (DAY 21) ──────────────────────────────────────────────
  /** 우리가 지은 기본 이름. 되돌리기 버튼이 이걸 쓴다. */
  default_name?: string;
  /** 지금 채용되어 있는가. 아니면 자리가 비어 있다. */
  active?: boolean;
  /** 내보낼 수 있는 자리인가. 핵심 세 자리는 비울 수 없다. */
  can_fire?: boolean;
  /** 못 내보내는 이유. 버튼만 막아두면 사용자는 고장인 줄 안다. */
  fire_reason?: string;
}

export interface ProviderRow {
  name: string;
  model: string;
  key: boolean;
  mock: boolean;
  fallbacks: string[];
  models: { id: string; label: string; tier: string }[];
}

export interface ProviderStatus {
  mode: "auto" | "mock" | "real";
  providers: ProviderRow[];
  any_real: boolean;
  all_mock: boolean;
  /** 구현자와 검증자가 서로 다른 회사인가 (§8). 아니면 교차검증이 형식만 남는다. */
  cross_check: boolean;
}

export type EventType =
  | "message"
  | "phase"
  | "state"
  | "done"
  | "projects"
  | "approval"
  | "approval_done";

export interface BusEvent {
  id: number;
  type: EventType;
  ts: number;
  run: string | null;
  /** message */
  agent?: string;
  kind?: "say" | "tool" | "verdict" | "error";
  text?: string;
  /** phase */
  name?: string;
  detail?: string;
  /** phase — 담당자가 바뀔 때만 온다(app/bus.py). 없으면 화면은 `name`·
   *  `detail` 로 예전처럼 그린다. */
  headline?: string | null;
  /** state */
  tasks?: TaskRow[];
  files?: string[];
  score?: number;
  score_detail?: Record<string, string | number | boolean>;
  round?: number;
  usage?: Record<string, UsageRow>;
  totals?: Partial<UsageRow>;
  cache_ok?: boolean | null;
  project?: { slug: string; name: string; requirement: string; mock?: boolean };
  /** done */
  ok?: boolean;
  summary?: string;
  unmet?: string[];
}

export interface TaskRow {
  id: string;
  title: string;
  assignee: string;
  status: "todo" | "doing" | "done";
}

/** 파일 한 판본. 옛 판본에는 경위가 없어서 빈 값으로 온다 (DAY 22). */
export interface FileVersion {
  version: number;
  note: string;
  lines: number;
  author?: string;
  round?: number;
  reason?: string;
  at?: number;
  current?: boolean;
}

export interface Project {
  slug: string;
  name: string;
  requirement: string;
  owner: string;
  created_at: number;
  /** 마지막으로 움직인 시각. created_at 과 빼면 걸린 시간이다. */
  updated_at?: number;
  status: "running" | "done" | "stopped" | "manual";
  score: number;
  score_detail?: Record<string, string | number | boolean>;
  tasks: TaskRow[];
  usage: Record<string, UsageRow>;
  cost: number;
  credits?: number;
  /** Mock 으로 만든 산출물인가. 목록에서 구분되어야 한다. */
  mock: boolean;
  file_count?: number;
  files?: string[];
  criteria?: { id: string; text: string }[];
  stopped_reason?: string;
  report?: {
    summary: string;
    met_criteria: string[];
    unmet_criteria: string[];
  };
  running?: boolean;
  events?: BusEvent[];
  mode?: string;
  last_verdict?: Verdict;
}

export interface Verdict {
  message_to_team: string;
  verdict: "pass" | "fail";
  severity: "none" | "minor" | "major" | "blocker";
  findings: { file: string; issue: string; why: string }[];
  required_fixes: string[];
}

export interface Roster {
  [agentId: string]: { name: string; icon: string };
}

export interface Settings {
  keys: Record<string, { label: string; set: boolean; masked: string | null }>;
  models: Record<string, string>;
  catalog: Record<
    string,
    { default: string; models: { id: string; label: string; tier: string }[] }
  >;
  stored: boolean;
  missing: string[];
  ready: boolean;
  /** 운영자 키를 화면에서 바꿀 수 있는가. SaaS 배포에서는 false —
   *  운영자 키는 환경변수로만 들어온다 (DAY 19). */
  operator_settings: boolean;
}

/** 고객 자신의 키 (BYOK, DAY 19). 운영자 키와 **저장소부터 다르다.** */
export interface ByokStatus {
  keys: Record<string, { set: boolean; masked: string | null }>;
  ready: boolean;
  missing: string[];
  /** 운영자가 KEK 를 환경변수로 넣었는가. false 면 서버 디스크를 가져간
   *  사람이 고객 키도 가져간다 — 화면이 그 사실을 말해야 한다. */
  kek_from_env: boolean;
  plan: string;
  source: "platform" | "byok" | "mock" | "none";
  charge_credits: boolean;
  byok_ready: boolean | null;
}

export interface CreditStatus {
  owner: string;
  plan: string;
  plan_label: string;
  balance: number;
  granted: number;
  spent: number;
  topped_up: number;
  credit_usd: number;
  balance_usd: number;
  max_concurrent: number;
  max_project_cost: number;
  /** 고객이 **자기 키로** 쓴 금액. 우리가 청구하는 돈이 아니다 (DAY 19). */
  byok_usd: number;
  /** 이 요금제가 누구의 키로 도는가. */
  source: "platform" | "byok" | "mock" | "none";
  /** 크레딧을 깎는 요금제인가. 우리 키로 나간 비용만 깎는다. */
  charges_credits: boolean;
  /** 단가가 공식 문서와 대조됐는가. 아니면 이 숫자들은 추측이다 (§14). */
  prices_verified: boolean;
  prices_verified_on: string;
}

export interface PlanRow {
  label: string;
  price_usd: number;
  credits: number;
  max_concurrent: number;
  max_project_cost: number;
  source?: "platform" | "byok" | "mock" | "none";
  /** 고객에게 보이는 한 줄. 우리끼리의 근거(`_why`)는 화면에 오지 않는다. */
  blurb?: string;
}

export interface TopupRow {
  label: string;
  credits: number;
  price_usd: number;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: number;
  /** 이메일이 확인됐는가 (DAY 22). 확인 전이라고 막지는 않는다 —
   *  막으면 메일이 안 나가는 서버에서 아무도 못 쓴다. 대신 말한다. */
  email_verified?: boolean;
}

export interface MeResponse {
  user: User | null;
  authenticated: boolean;
  /** saas 배포라 로그인이 반드시 필요한가. local 이면 false. */
  required: boolean;
  /** 이 서버에 계정이 하나도 없는가. */
  first_user: boolean;
  identities: { provider: string; subject: string; created_at: number }[];
}
