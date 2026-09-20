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

export interface Project {
  slug: string;
  name: string;
  requirement: string;
  owner: string;
  created_at: number;
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
}
