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
  | "approval_done"
  | "handoff"
  /** DAY 25 — 승인 게이트가 열리고(open)·보류되고(held)·닫힐(closed) 때. */
  | "gate"
  /** DAY 25 — 모델 호출 하나의 시작·끝(걸린 시간). 채팅에는 안 그린다. */
  | "call"
  /** DAY 25 — 실행이 결재를 기다리며 쉬러 들어갔다. */
  | "awaiting";

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
  /** handoff — bus.handoff(), app/bus.py. message 의 message_to_team 한
   *  줄로는 안 보이던 구조화된 인계 근거(무엇을 확인했는지, 검증자가
   *  무엇을 지적했는지, 어떤 인수기준이 충족됐는지). 모델을 새로 부르지
   *  않고 이미 받은 답을 그대로 구조로 남긴 것이다. */
  from?: string;
  to?: string;
  /** 이 인계가 일어난 단계. "phase" 이벤트의 `name` 과 같은 값 집합이다. */
  phase?: string;
  task_titles?: string[];
  criteria?: string[];
  covered?: string[];
  uncovered?: string[];
  self_check?: string;
  findings?: { file: string; issue: string; why: string }[];
  required_fixes?: string[];
  verdict?: "pass" | "fail";
  severity?: "none" | "minor" | "major" | "blocker";
  /** 판정 확신도(0~1) — Verdict.confidence 와 같은 값. handoff(REVIEW)와
   *  판정 message(kind=verdict) 둘 다에 실린다 (DAY 25). */
  confidence?: number;
  met?: string[];
  /** handoff — 어느 태스크의 인계인가 (병렬 실행 · DAY 25). */
  task_id?: string;
  /** phase — 병렬로 도는 태스크 중 어느 줄의 단계인가 (DAY 25). */
  lane?: string;
  /** state — 지금 도는 줄들 (DAY 25). */
  active?: { task: string; title: string; assignee: string }[];
  /** gate */
  stage?: "open" | "held" | "closed" | "start" | "end";
  approval?: Approval;
  /** call */
  call_id?: number;
  ms?: number;
  model?: string;
}

export interface TaskRow {
  id: string;
  title: string;
  assignee: string;
  status: "todo" | "doing" | "done" | "awaiting";
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
  status: "running" | "done" | "stopped" | "manual" | "awaiting";
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
  /** 대표가 멈춰 서서 보겠다는 지점 (DAY 25 · HITL). */
  gates?: string[];
  approvals?: Approval[];
  permissions?: { overrides?: Record<string, { writes?: string[]; reads?: string[] }>;
                  risks?: string[] };
  checkpoint?: { stage?: string | null; done?: string[]; rounds?: number };
}

// ── 사무실 · 결재 · 권한 · 지표 (DAY 25) ──────────────────────────
export type Decision = "approve" | "reject" | "hold" | "discard";

export interface Approval {
  id: string;
  gate: "plan" | "task";
  title: string;
  status: "pending" | "approved" | "rejected" | "stopped" | "discarded";
  created_at: number;
  held?: boolean;
  comment?: string;
  decided_at?: number;
  task_id?: string;
  detail: {
    // plan
    tasks?: { id: string; title: string; assignee: string; deps: string[] }[];
    criteria?: { id: string; text: string }[];
    message?: string;
    // task
    assignee?: string;
    reason?: "task" | "confidence";
    confidence?: number;
    threshold?: number;
    files?: string[];
    findings?: { file: string; issue: string; why: string }[];
    rework?: number;
  };
}

/** 사규 §2 의 다섯 상태. 색과 말풍선이 여기에 딸려 있다. */
export type OfficeState = "done" | "working" | "approval" | "integration" | "idle";

export interface OfficeEmployee {
  id: string;
  name: string;
  /** 지금 앉은 팀. 대표가 끌어다 옮길 수 있다 (DAY 26 · agents/staff.py). */
  dept: string;
  /** 처음 팀 — 옮긴 적이 없으면 `dept` 와 같다. */
  home_dept?: string;
  role: string;
  provider: string;
  hired: boolean;
  mock: boolean;
  state: OfficeState;
  /** 상태가 이렇게 된 이유 한 줄 (사규 §2 ②). 비어 있는 일이 없다. */
  reason: string;
  task: { id: string | null; title: string | null } | null;
  progress: { done: number; total: number };
  calls: number;
  cost: number;
  avg_ms: number | null;
  inflight_ms: number | null;
  place: "desk" | "meeting" | "away";
}

export interface IntegrationItem {
  key: string;
  label: string;
  why: string;
  detail?: string;
  affects: string[];
  fix: string | null;
}

export interface ScenarioStep {
  key: string;
  state: "done" | "current" | "todo" | "off" | "skip";
}

export interface OfficeSnapshot {
  now: number;
  run: {
    slug: string;
    name: string;
    requirement: string;
    status: Project["status"];
    running: boolean;
    stopped_reason: string | null;
    created_at: number;
    mock: boolean;
    cost: number;
    score: number | null;
    tasks_done: number;
    tasks_total: number;
    pending: number;
    held: number;
    confidence: number | string | null;
  } | null;
  employees: OfficeEmployee[];
  approvals: Approval[];
  gates: string[];
  meeting: { who: string[]; approval_id: string | null };
  integrations: IntegrationItem[];
  scenario: ScenarioStep[];
  metrics: {
    inflight: { call_id: number; agent: string; model: string | null; elapsed_ms: number }[];
    parallelism: number | null;
    wall_ms: number;
    human_wait_ms: number;
  } | null;
}

export interface AskAnswer {
  intent: string;
  lines: { who: string; text: string }[];
  action?: { focus?: boolean; meeting?: string[]; choose?: string[]; decided?: string };
}

export interface RunMetrics {
  wall_ms: number;
  human_wait_ms: number;
  model_ms: number;
  parallelism: number | null;
  calls: number;
  failed_calls: number;
  retries: number;
  by_agent: Record<string, {
    calls: number; ok: number; failed: number; total_ms: number; wait_ms: number;
    retries: number; output: number; avg_ms: number; p50_ms: number; p95_ms: number;
    max_ms: number; tokens_per_sec: number | null;
  }>;
  by_phase: Record<string, { ms: number; count: number }>;
  slowest: { call_id: number; agent: string; model: string; ms: number; attempts: number;
             ok: boolean; error?: string | null }[];
  inflight: { call_id: number; agent: string; model: string | null; elapsed_ms: number }[];
  finished: boolean;
}

export interface PermissionRow {
  id: string;
  kind: string;
  base: { writes: string[]; reads: string[] };
  effective: { writes: string[]; reads: string[] };
  overridden: boolean;
  locked: { writes: string[]; reads: string[] };
  risky: { reads: string[] };
}

export interface PermissionsView {
  overrides: Record<string, { writes?: string[]; reads?: string[] }>;
  risks: string[];
  acknowledged_at: number | null;
  table: PermissionRow[];
}

export interface Verdict {
  message_to_team: string;
  verdict: "pass" | "fail";
  severity: "none" | "minor" | "major" | "blocker";
  findings: { file: string; issue: string; why: string }[];
  required_fixes: string[];
  /** 이 판정 자체에 대한 확신도(0~1). 통과율이 아니라 근거가 얼마나
   *  단단한가다 — app/agents/schemas.py 의 Verdict.confidence. */
  confidence: number;
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
