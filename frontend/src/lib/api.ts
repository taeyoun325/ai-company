/**
 * 백엔드 호출 한 곳 (지시서 §12).
 *
 * ## 왜 모아두나
 *
 * `fetch('/api/...')` 를 컴포넌트마다 쓰면 오류 처리가 제각각이 되고,
 * 어떤 화면은 실패를 조용히 삼킨다. 조용히 삼킨 실패는 "빈 화면"으로
 * 보이고, 사용자는 그것을 "아직 아무것도 없음"으로 읽는다.
 *
 * ## 오류를 문자열로 뭉개지 않는다
 *
 * 백엔드는 HTTP 상태로 의미를 구분한다 — 402 는 예산 상한, 409 는 작업
 * 중, 404 는 없음. 화면이 다르게 반응해야 하므로 상태를 그대로 들고 간다.
 */
import type {
  Approval,
  AskAnswer,
  Decision,
  OfficeSnapshot,
  PermissionsView,
  RunMetrics,
  ByokStatus,
  CreditStatus,
  FileVersion,
  Employee,
  MeResponse,
  PlanRow,
  TopupRow,
  Project,
  ProviderStatus,
  Roster,
  Settings,
  User,
  Verdict,
  BusEvent,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** 예산 상한에 걸렸는가 (§18). 화면이 다르게 말해야 한다. */
  get isBudget() {
    return this.status === 402;
  }
  get isBusy() {
    return this.status === 409 || this.status === 429;
  }

  /** 서버가 거절한 게 아니라 **닿지도 못했다**. 사용자가 할 일이 다르다. */
  get isOffline() {
    return this.status === 0;
  }
}

/**
 * 401 을 한 곳에서 알린다 (DAY 15).
 *
 * 세션은 만료된다. 화면마다 401 을 따로 처리하면 어떤 화면은 빼먹고,
 * 그 화면만 "로그인했는데 빈 화면"이 된다.
 */
type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

export function onUnauthorized(fn: Listener): () => void {
  unauthorizedListeners.add(fn);
  return () => unauthorizedListeners.delete(fn);
}

/**
 * 지금 화면의 언어. 서버가 이걸 보고 오류 문장과 **직원 프롬프트**의
 * 언어를 정한다 (DAY 21 · backend/app/lang.py).
 *
 * 모듈 변수인 이유: `api` 는 훅이 아니라 함수 모음이라 컨텍스트를 읽을 수
 * 없다. i18n 쪽에서 언어가 바뀔 때마다 여기 한 줄을 갱신한다.
 */
/**
 * 고른 언어가 저장되는 자리. **값은 한 곳에만 산다** — `lib/i18n.tsx` 가
 * 이 상수를 가져다 쓴다.
 */
export const LANG_STORE_KEY = "ai-company.lang";

/**
 * 서버에 보낼 언어 (DAY 22).
 *
 * 여기가 `"ko"` 로 시작하고 있었다. 언어는 `LangProvider` 의 effect 에서
 * 들어오는데, **첫 요청들은 그 전에 나간다.** 영어로 쓰는 사람이 새로고침
 * 하면 직원표·오류 문장이 한국어로 한 번 오고, 언어를 다시 고르기 전까지
 * 그대로 남았다. 그래서 저장된 값을 처음 쓸 때 직접 읽는다.
 */
let acceptLanguage = "";

function language(): string {
  if (acceptLanguage) return acceptLanguage;
  try {
    acceptLanguage = window.localStorage.getItem(LANG_STORE_KEY) || "en";
  } catch {
    acceptLanguage = "en";    // 사생활 보호 모드에서는 읽기가 던진다
  }
  return acceptLanguage;
}

export function setApiLanguage(lang: string) {
  acceptLanguage = lang;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "Accept-Language": language(),
        ...init?.headers,
      },
    });
  } catch (e) {
    // 네트워크 자체가 끊긴 경우. 서버 오류와 구분해서 말해야 한다 —
    // "서버가 거절했다"와 "서버에 닿지 못했다"는 사용자의 대응이 다르다.
    //
    // 여기서 문장을 만들지 않는다. 이 파일은 React 밖이라 사용자가 고른
    // 언어를 모르고, 여기서 쓴 한국어는 **어떤 언어로 보든 그대로** 화면에
    // 나온다. 상태 0 만 남기고 문장은 화면이 고른다(`useErrorText`).
    throw new ApiError(0, String(e));
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* 본문이 JSON 이 아닐 수 있다 */
    }
    if (res.status === 401) {
      // 로그인 자체를 시도하다 실패한 것은 "세션 만료"가 아니다.
      // 그때까지 로그인 화면으로 보내면 방금 뜬 오류 문구가 사라진다.
      if (!path.startsWith("/api/auth/")) {
        unauthorizedListeners.forEach((fn) => fn());
      }
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/**
 * 경로에 들어가는 slug 를 감싼다.
 *
 * 프로젝트 slug 에는 한글과 공백이 들어갈 수 있다. 감싸지 않으면 브라우저가
 * 알아서 인코딩해 주기는 하지만, `?` 나 `#` 이 섞이면 경로가 잘린다.
 */
const seg = (s: string) => encodeURIComponent(s);

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

const del = <T>(path: string) => call<T>(path, { method: "DELETE" });

const put = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined });

/** 새 실행에 함께 보낼 것 (DAY 25). */
export interface StartOptions {
  /** 대표가 멈춰 서서 보겠다는 지점 — "plan" · "task" · "task:<직원>" · "confidence" */
  gates?: string[];
  permissions?: Record<string, { writes?: string[]; reads?: string[] }>;
  acknowledge_risk?: boolean;
}

export const api = {
  // ── 인증 (DAY 15) ───────────────────────────────────────────────
  me: () => call<MeResponse>("/api/auth/me"),
  signUp: (email: string, password: string, display_name = "") =>
    post<{ user: User }>("/api/auth/signup", { email, password, display_name }),
  logIn: (email: string, password: string) =>
    post<{ user: User }>("/api/auth/login", { email, password }),
  logOut: () => post<{ ok: boolean }>("/api/auth/logout"),
  changePassword: (current: string, next: string) =>
    post<{ ok: boolean }>("/api/auth/password", { current, new: next }),
  revokeSessions: () => post<{ revoked: number }>("/api/auth/sessions/revoke"),
  deploy: () =>
    call<{
      mode: string;
      sandboxed: boolean;
      local_tools: boolean;
      code_execution: boolean;
    }>("/api/deploy"),

  /**
   * `run` 을 주면 그 실행의 직원별 사용량이 함께 온다. 안 주면 0 이다 —
   * 사용량은 실행별로 묶여 있고 이 요청은 다른 스레드가 처리한다(§14).
   */
  state: (run?: string) =>
    call<{
      employees: Employee[];
      providers: ProviderStatus;
      credits: CreditStatus;
      keys_ready: boolean;
    }>(`/api/state${run ? `?run=${encodeURIComponent(run)}` : ""}`),

  employees: () =>
    call<{ employees: Employee[]; assignable: string[]; planner: string; verifier: string }>(
      "/api/employees",
    ),
  employee: (id: string) => call<Employee>(`/api/employees/${seg(id)}`),
  setEmployeeModel: (id: string, model: string) =>
    post<{ ok: boolean }>(`/api/employees/${seg(id)}/model`, { model }),

  // ── 비밀번호 재설정 · 이메일 확인 (DAY 22) ──────────────────────
  // `delivered` 를 그대로 화면에 올린다. 서버가 메일을 못 보냈는데
  // "보냈습니다"라고 적으면, 사용자는 오지 않는 메일을 기다린다.
  forgot: (email: string) =>
    post<{ ok: boolean; delivered: boolean; how: string; detail: string }>(
      "/api/auth/forgot", { email },
    ),
  resetPassword: (token: string, password: string) =>
    post<{ ok: boolean; user: User }>("/api/auth/reset", { token, password }),
  sendVerification: () =>
    post<{ ok: boolean; delivered: boolean; how: string; detail: string }>(
      "/api/auth/verify/send",
    ),
  verifyEmail: (token: string) =>
    post<{ ok: boolean; user: User }>("/api/auth/verify", { token }),

  providers: () => call<ProviderStatus>("/api/providers"),

  // ── 인사 (DAY 21) ───────────────────────────────────────────────
  updateEmployee: (id: string, patch: { name?: string; active?: boolean }) =>
    call<{ ok: boolean; employees: Employee[] }>(
      `/api/employees/${seg(id)}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  settings: () => call<Settings>("/api/settings"),
  setKeys: (keys: Record<string, string>, remember: boolean) =>
    post<Settings & { providers: ProviderStatus }>("/api/settings/keys", {
      ...keys,
      remember,
    }),
  verifyKey: (provider: string) =>
    post<{ ok: boolean; detail: string; models?: string[] }>(
      `/api/settings/verify/${seg(provider)}`,
    ),
  forgetKeys: () => post<{ ok: boolean }>("/api/settings/forget"),

  // ── 내 API 키 (BYOK · DAY 19) ───────────────────────────────────
  // 운영자 키(`/api/settings`)와 라우트를 나눈다. 한 라우트에서 둘을 같이
  // 다루면 언젠가 한쪽 코드가 다른 쪽 저장소를 건드리고, 그때 사고는
  // "내 키가 남에게 갔다"가 된다.
  byok: () => call<ByokStatus>("/api/byok"),
  setByok: (keys: Record<string, string>) =>
    post<ByokStatus & { ok: boolean }>("/api/byok", keys),
  clearByok: (provider?: string) =>
    del<ByokStatus & { ok: boolean }>(
      provider ? `/api/byok?provider=${seg(provider)}` : "/api/byok",
    ),
  verifyByok: (provider: string) =>
    post<{ ok: boolean; detail: string }>(
      `/api/byok/verify/${seg(provider)}`,
    ),

  // ── AUTO (§10) ──────────────────────────────────────────────────
  startRun: (requirement: string, opts: StartOptions = {}) =>
    post<{ slug: string; running: boolean; mock: boolean }>("/api/runs", {
      requirement,
      ...opts,
    }),
  runs: () => call<{ running: string[]; projects: Project[] }>("/api/runs"),
  run: (slug: string) => call<Project>(`/api/runs/${seg(slug)}`),
  cancelRun: (slug: string) => post<{ ok: boolean }>(`/api/runs/${seg(slug)}/cancel`),
  resumeRun: (slug: string) =>
    post<{ slug: string; running: boolean; mock: boolean }>(
      `/api/runs/${seg(slug)}/resume`,
    ),
  route: (requirement: string) =>
    post<{ employee: string; why: string }>("/api/route", { requirement }),

  // ── 결재 · 게이트 (DAY 25 · HITL) ───────────────────────────────
  approvals: (slug: string) =>
    call<{ gates: string[]; approvals: Approval[]; confidence_gate: number;
           status: string }>(`/api/runs/${seg(slug)}/approvals`),
  /** `resumed` — 쉬던 실행을 지금 깨웠는가. `note` — 못 깨운 이유(좌석·잔액). */
  decide: (slug: string, id: string, decision: Decision, comment = "") =>
    post<{ approval: Approval; resumed: boolean; note: string | null }>(
      `/api/runs/${seg(slug)}/approvals/${seg(id)}`, { decision, comment },
    ),
  setGates: (slug: string, gates: string[]) =>
    put<{ gates: string[] }>(`/api/runs/${seg(slug)}/gates`, { gates }),

  // ── 사무실 · 대표 지시창 (DAY 25) ───────────────────────────────
  office: (run?: string | null) =>
    call<OfficeSnapshot>(`/api/office${run ? `?run=${encodeURIComponent(run)}` : ""}`),
  ask: (text: string, run?: string | null) =>
    post<AskAnswer>("/api/office/ask", {
      text, run: run ?? null, tz_offset: new Date().getTimezoneOffset(),
    }),

  // ── 관측성 · 권한 (DAY 25) ──────────────────────────────────────
  metrics: (slug: string) => call<RunMetrics>(`/api/runs/${seg(slug)}/metrics`),
  permissions: (slug: string) =>
    call<PermissionsView>(`/api/projects/${seg(slug)}/permissions`),
  setPermissions: (
    slug: string,
    overrides: Record<string, { writes?: string[]; reads?: string[] }>,
    acknowledge_risk = false,
  ) => put<PermissionsView>(`/api/projects/${seg(slug)}/permissions`,
                           { overrides, acknowledge_risk }),

  // ── MANUAL (§11) ────────────────────────────────────────────────
  openManual: (requirement: string) =>
    post<{ slug: string; mode: string }>("/api/manual", { requirement }),
  instruct: (slug: string, employee: string, message: string) =>
    post<{
      employee: string;
      text: string;
      summary?: string;
      self_check?: string;
      files: string[];
    }>(`/api/manual/${seg(slug)}/instruct`, { employee, message }),
  verifyManual: (slug: string) =>
    post<{ verdict: Verdict; report: Record<string, unknown> }>(
      `/api/manual/${seg(slug)}/verify`,
    ),
  manualState: (slug: string) =>
    call<{
      slug: string;
      busy: string | null;
      employees: Employee[];
      files: string[];
      history: Record<string, { role: string; content: string }[]>;
    }>(`/api/manual/${seg(slug)}`),

  // ── 프로젝트 (§12) ──────────────────────────────────────────────
  /**
   * `source` 가 "disk" 면 색인이 깨져 파일에서 읽은 것이다. 화면이
   * 그 사실을 감추면, 왜 느린지 아무도 모른다.
   */
  projects: (opts: {
    q?: string;
    status?: string;
    sort?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(opts)) {
      if (v !== undefined && v !== "") p.set(k, String(v));
    }
    return call<{
      projects: Project[];
      total: number;
      limit: number;
      offset: number;
      source: "index" | "disk";
    }>(`/api/projects?${p.toString()}`);
  },
  projectStats: () =>
    call<{
      projects: number;
      cost: number;
      credits: number;
      avg_score: number;
      done: number;
      stopped: number;
      mock: number;
    }>("/api/projects/stats"),
  reindex: () => post<{ indexed: number }>("/api/projects/reindex"),
  projectFiles: (slug: string) => call<{ files: string[] }>(`/api/projects/${seg(slug)}/files`),
  projectFile: (slug: string, path: string) =>
    call<{
      path: string;
      content: string;
      /** 판본마다 **누가·몇 라운드에·왜** 고쳤는지 (DAY 22). */
      versions: FileVersion[];
    }>(`/api/projects/${seg(slug)}/file?path=${encodeURIComponent(path)}`),
  projectDiff: (slug: string, path: string, a: number, b = 0) =>
    call<{ diff: { kind: string; text: string }[] }>(
      `/api/projects/${seg(slug)}/diff?path=${encodeURIComponent(path)}&a=${a}&b=${b}`,
    ),
  deleteProject: (slug: string) =>
    call<{ ok: boolean }>(`/api/projects/${seg(slug)}`, { method: "DELETE" }),

  // ── 로그를 평범한 말로 (DAY 23) ─────────────────────────────────
  // 검증(§11)과 같은 규칙으로 CEO 가 누를 때만 돈다. `force` 는 캐시를
  // 무시하고 다시 부른다 — 비용이 또 나간다는 뜻이라 버튼을 따로 둔다.
  narrate: (slug: string, force = false) =>
    post<{ text: string; cached: boolean }>(
      `/api/projects/${seg(slug)}/narrate${force ? "?force=true" : ""}`,
    ),

  // ── 크레딧 · 요금제 (§15 §16) ───────────────────────────────────
  credits: () => call<CreditStatus>("/api/credits"),
  plans: () =>
    call<{
      plans: Record<string, PlanRow>;
      topups: Record<string, TopupRow>;
      credit_usd: number;
      /** 끝난 프로젝트에서 **실제로 잰** 비용. `measured` 가 false 면
       *  아직 셀 만큼 돌지 않았다는 뜻이고, 화면은 추정값을 쓴다. */
      per_project: {
        samples: number;
        measured: boolean;
        median_usd: number;
        p90_usd: number;
        max_usd: number;
        min_samples: number;
      };
    }>("/api/plans"),
  changePlan: (plan: string) => post<CreditStatus>("/api/credits/plan", { plan }),
  topUp: (amount: number) =>
    post<CreditStatus>("/api/credits/topup", { credits: amount }),

  // ── 로그 (§13) ──────────────────────────────────────────────────
  events: (run?: string, after = 0) =>
    call<{ events: BusEvent[]; last_id: number; roster: Roster }>(
      `/api/events?after=${after}${run ? `&run=${encodeURIComponent(run)}` : ""}`,
    ),
};
