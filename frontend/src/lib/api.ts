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
  Employee,
  Project,
  ProviderStatus,
  Roster,
  Settings,
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
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (e) {
    // 네트워크 자체가 끊긴 경우. 서버 오류와 구분해서 말해야 한다 —
    // "서버가 거절했다"와 "서버에 닿지 못했다"는 사용자의 대응이 다르다.
    throw new ApiError(0, `백엔드에 닿지 못했습니다 (${String(e)})`);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* 본문이 JSON 이 아닐 수 있다 */
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

export const api = {
  /**
   * `run` 을 주면 그 실행의 직원별 사용량이 함께 온다. 안 주면 0 이다 —
   * 사용량은 실행별로 묶여 있고 이 요청은 다른 스레드가 처리한다(§14).
   */
  state: (run?: string) =>
    call<{
      employees: Employee[];
      providers: ProviderStatus;
      keys_ready: boolean;
    }>(`/api/state${run ? `?run=${encodeURIComponent(run)}` : ""}`),

  employees: () =>
    call<{ employees: Employee[]; assignable: string[]; planner: string; verifier: string }>(
      "/api/employees",
    ),
  employee: (id: string) => call<Employee>(`/api/employees/${seg(id)}`),
  setEmployeeModel: (id: string, model: string) =>
    post<{ ok: boolean }>(`/api/employees/${seg(id)}/model`, { model }),

  providers: () => call<ProviderStatus>("/api/providers"),
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

  // ── AUTO (§10) ──────────────────────────────────────────────────
  startRun: (requirement: string) =>
    post<{ slug: string; running: boolean; mock: boolean }>("/api/runs", {
      requirement,
    }),
  runs: () => call<{ running: string[]; projects: Project[] }>("/api/runs"),
  run: (slug: string) => call<Project>(`/api/runs/${seg(slug)}`),
  cancelRun: (slug: string) => post<{ ok: boolean }>(`/api/runs/${seg(slug)}/cancel`),
  route: (requirement: string) =>
    post<{ employee: string; why: string }>("/api/route", { requirement }),

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
  projects: () => call<{ projects: Project[] }>("/api/projects"),
  projectFiles: (slug: string) => call<{ files: string[] }>(`/api/projects/${seg(slug)}/files`),
  projectFile: (slug: string, path: string) =>
    call<{
      path: string;
      content: string;
      versions: { version: number; note: string; lines: number }[];
    }>(`/api/projects/${seg(slug)}/file?path=${encodeURIComponent(path)}`),
  projectDiff: (slug: string, path: string, a: number, b = 0) =>
    call<{ diff: { kind: string; text: string }[] }>(
      `/api/projects/${seg(slug)}/diff?path=${encodeURIComponent(path)}&a=${a}&b=${b}`,
    ),
  deleteProject: (slug: string) =>
    call<{ ok: boolean }>(`/api/projects/${seg(slug)}`, { method: "DELETE" }),

  // ── 로그 (§13) ──────────────────────────────────────────────────
  events: (run?: string, after = 0) =>
    call<{ events: BusEvent[]; last_id: number; roster: Roster }>(
      `/api/events?after=${after}${run ? `&run=${encodeURIComponent(run)}` : ""}`,
    ),
};
