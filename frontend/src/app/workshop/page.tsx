"use client";

/**
 * 작업장 — 사무실과 코드 창을 한 화면에 (탭 카드 덱의 두 번째 카드).
 *
 * ## 사무실과 같은 회사, 같은 실행
 *
 * 처음에는 화면 안에서만 도는 대본(따로 정한 GPT · Sonnet · Opus · Higgsfield
 * 팀)이었다. 사무실과 직원 명단이 달라 "누가 진짜 직원이냐"가 흐려졌고, 모델
 * 선택도 설정의 '직원별 모델'과 따로 놀았다. 이제 작업장은 **AUTO 실행을 다른
 * 각도에서 보는 화면**이다:
 *
 * - 자리 = 사무실 직원 다섯. 전략가가 분배(계획 = 설계도)하고, 개발자 · 작가 ·
 *   디자이너가 슬롯을 맡고, 분석가(다른 회사 모델)가 검수대다.
 * - 슬롯 = 계획의 태스크. 맡은 파일 · 먼저 끝나야 할 태스크 · 완료 조건(규격)이
 *   붙어 있다. 같은 직원의 태스크가 여럿이면 엔진이 나란히 돌린다(분신).
 * - 코드 창 = 그 슬롯이 **실제로 쓴 파일**. 쓸 때마다 다시 읽는다.
 * - 검수 = 분석가의 판정 + 실제 pytest. 반려되면 지적이 빨간 줄로 붙는다.
 * - 버전 = 설정의 '직원별 모델'과 같은 값(서버, 고객마다 따로).
 *
 * 키가 없으면 엔진이 Mock 대본으로 돈다 — 그 사실은 접히지 않게 말한다.
 *
 * ## 사무실이 주 화면, 코드 창은 따라가는 창
 *
 * 직원 여럿이 동시에 쓰면 대표는 아무것도 못 읽는다. 코드 창은 **슬롯 하나만**
 * 비춘다 — 대표가 고른 슬롯, 아니면 따라가기 모드에서 방금 움직인 슬롯.
 *
 * ## 폰
 *
 * 사무실 · 슬롯판 · 로그를 쌓고, 직원이나 슬롯을 누르면 코드가 카드 전체로 올라온다.
 *
 * ## 연결은 볼 때만
 *
 * 사무실 카드도 같은 실행에 이벤트 연결을 문다. 브라우저는 오리진당 연결 수가
 * 정해져 있어(useStream 참조), 작업장은 **가운데 카드일 때만** 붙는다.
 */
import Link from "next/link";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ChatLog } from "@/components/ChatLog";
import { Button, ErrorBox, MockBadge } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { highlightLine, langOf } from "@/lib/highlight";
import { type Key, useErrorText, useLang } from "@/lib/i18n";
import { useStack } from "@/lib/stack";
import type { BusEvent, Employee, TaskRow } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { foldState, useStream } from "@/lib/useStream";

const PHONE_MAX = 720;
const PLAN_SLOT = "plan";

/** 단계 — 엔진의 phase 이름을 대표가 읽는 다섯 칸으로 접는다. */
const STEPS = ["plan", "tests", "build", "finalize", "done"] as const;
type Step = (typeof STEPS)[number];
const STEP_OF: Record<string, Step> = {
  PLAN: "plan", REPLAN: "plan", WRITE_TESTS: "tests",
  IMPLEMENT: "build", TEST: "build", REVIEW: "build", FINALIZE: "finalize",
};

type SlotState = "todo" | "writing" | "testing" | "review" | "passed" | "awaiting";
const SLOT_COLOR: Record<SlotState, string> = {
  todo: "var(--dim)",
  writing: "var(--st-working)",
  testing: "var(--st-integration)",
  review: "var(--st-integration)",
  passed: "var(--st-done)",
  awaiting: "var(--st-approval)",
};

/** 이벤트에서 작업장이 쓰는 것만 접는다 — 줄(태스크)마다의 단계 · 쓴 파일 · 판정. */
function foldLanes(events: BusEvent[]) {
  const lane = new Map<string, string>();               // task → IMPLEMENT | TEST | REVIEW
  const wrote = new Map<string, { files: string[]; n: number }>();
  const verdict = new Map<string, BusEvent>();
  const rejects = new Map<string, number>();              // task → 반려 횟수
  let plan: BusEvent | null = null;
  let step: Step | null = null;
  let top = "";                                          // 줄 없는 마지막 단계
  let spot: string | null = null;
  let awaiting = false;                                  // 대표 승인을 기다리는 중
  for (const e of events) {
    if (e.type === "awaiting") awaiting = true;
    else if (e.type === "approval_done" || e.type === "phase") awaiting = false;
    if (e.type === "phase" && e.name) {
      const s = STEP_OF[e.name];
      if (s && (step === null || STEPS.indexOf(s) > STEPS.indexOf(step))) step = s;
      if (e.lane) {
        lane.set(e.lane, e.name);
        spot = e.lane;
      } else {
        top = e.name;
        if (e.name === "PLAN" || e.name === "REPLAN") spot = PLAN_SLOT;
      }
    } else if (e.type === "handoff" && e.phase === "PLAN") {
      plan = e;
    } else if (e.type === "handoff" && e.task_id) {
      if (e.phase === "IMPLEMENT") {
        const prev = wrote.get(e.task_id);
        const files = e.files ?? [];
        wrote.set(e.task_id, {
          files: [...new Set([...(prev?.files ?? []), ...files])],
          n: (prev?.n ?? 0) + 1,
        });
      } else if (e.phase === "REVIEW") {
        verdict.set(e.task_id, e);
        if (e.verdict === "fail") rejects.set(e.task_id, (rejects.get(e.task_id) ?? 0) + 1);
      }
      spot = e.task_id;
    } else if (e.type === "done") {
      step = "done";
    }
  }
  return { lane, wrote, verdict, rejects, plan, step, top, spot, awaiting };
}

export default function WorkshopPage() {
  const { t } = useLang();
  const errText = useErrorText();
  const { active } = useStack();
  const [slug, setSlug] = useState<string | null>(null);
  const [order, setOrder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);
  const [phone, setPhone] = useState(false);
  const [sheet, setSheet] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  const { data: state, reload: reloadState } = useLoader("state", () => api.state());
  const { data: settings } = useLoader("settings-catalog", () => api.settings());
  const stream = useStream(active && slug ? slug : undefined);
  // 이 실행의 사건만 — 흐름에는 앞 실행의 사건이 섞여 올 수 있다. 섞이면 슬롯 id
  // (t1 · t2 …)가 실행마다 같아서 반려 횟수가 실행 수만큼 쌓였다(화면 시험이 찾았다).
  const events = useMemo(
    () => stream.events.filter((e) => !e.run || e.run === slug), [stream.events, slug]);
  const folded = foldState(events);
  const lanes = useMemo(() => foldLanes(events), [events]);
  // 결재를 기다리는 실행은 돌지 않는다 — 새 오더를 막지도, '멈추기'를 띄우지도
  // 않는다(승인은 사무실 결재함에서). 그걸 '도는 중'으로 읽어서 시작 단추가 사라졌다.
  const running = !!slug && events.length > 0 && !folded.done && !lanes.awaiting;

  // 가운데로 올 때마다 지금 도는 실행을 찾는다 — 사무실에서 맡긴 일도 여기서 보인다.
  useEffect(() => {
    if (!active) return;
    let live = true;
    api.runs().then((r) => {
      if (!live) return;
      const awaiting = r.projects.find((p) => p.status === "awaiting");
      const pick = r.running[0] ?? awaiting?.slug ?? null;
      if (pick) setSlug((cur) => (cur && r.running.includes(cur) ? cur : pick));
    }).catch(() => { /* 빈 작업장으로 뜬다 */ });
    return () => {
      live = false;
    };
  }, [active]);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const check = () => setPhone(el.offsetWidth < PHONE_MAX);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const employees: Employee[] = (state?.employees ?? []).filter((e) => e.active !== false);
  const byId = new Map(employees.map((e) => [e.id, e]));
  const nameOf = (id: string) => byId.get(id)?.name ?? id;
  const catalog = settings?.catalog ?? {};
  const modelLabel = (e: Employee) =>
    catalog[e.provider]?.models.find((m) => m.id === e.model)?.label ?? e.model;
  const allMock = state?.providers?.all_mock ?? false;

  const tasks: TaskRow[] = folded.tasks ?? [];
  const slotState = (r: TaskRow): SlotState => {
    if (r.status === "done") return "passed";
    if (r.status === "awaiting") return "awaiting";
    if (r.status === "todo") return "todo";
    const ph = lanes.lane.get(r.id);
    return ph === "TEST" ? "testing" : ph === "REVIEW" ? "review" : "writing";
  };
  const planState: SlotState = tasks.length > 0 ? "passed"
    : lanes.step === "plan" ? "writing" : "todo";

  const shownId = follow ? lanes.spot : picked;
  const shownTask = tasks.find((r) => r.id === shownId) ?? null;
  const showPlan = shownId === PLAN_SLOT;

  const pick = (id: string | null) => {
    if (!id) return;
    setPicked(id);
    setFollow(false);
    if (phone) setSheet(true);
  };
  const pickDesk = (id: string) => {
    if (id === "strategist") return pick(PLAN_SLOT);
    const mine = id === "analyst"
      ? tasks.filter((r) => lanes.lane.get(r.id) === "REVIEW")
      : tasks.filter((r) => r.assignee === id);
    const live = mine.find((r) => r.status === "doing") ?? mine[mine.length - 1];
    pick(live?.id ?? null);
  };

  const start = async () => {
    const text = order.trim() || t("ws.defaultOrder");
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      stream.clear();
      // 작업장은 멈춤 없이 끝까지 — 승인 지점은 사무실의 지시창에서 고른다.
      const r = await api.startRun(text, { gates: [] });
      setOrder(text);
      setSlug(r.slug);
      setPicked(null);
      setFollow(true);
    } catch (e) {
      setError(e instanceof ApiError && (e.isBudget || e.isBusy) ? e.message : errText(e));
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    if (!slug) return;
    try {
      await api.cancelRun(slug);
    } catch (e) {
      setError(errText(e));
    }
  };
  const setModel = async (id: string, model: string) => {
    setError(null);
    try {
      await api.setEmployeeModel(id, model);
      await reloadState();
    } catch (e) {
      setError(errText(e));
    }
  };

  const top = (
    <header className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-[13px] font-semibold tracking-tight">{t("ws.title")}</h1>
        {allMock && (
          <>
            <MockBadge title={t("ws.mockNote")} />
            <span className="text-[11px] text-dim">{t("ws.mockNote")}</span>
          </>
        )}
        {folded.project && (
          <span data-record className="min-w-0 truncate text-[12px] text-muted">
            · {folded.project.name}</span>
        )}
        <span className="ml-auto">
          <button type="button" onClick={() => setFollow(!follow)} aria-pressed={follow}
            className="rounded-full border px-2.5 py-0.5 text-[11px] transition"
            style={{
              borderColor: follow ? "var(--st-working)" : "var(--line)",
              color: follow ? "var(--st-working)" : "var(--muted)",
            }}>
            {follow ? t("ws.followOn") : t("ws.followOff")}
          </button>
        </span>
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void start(); }}>
        <input value={order} onChange={(e) => setOrder(e.target.value)}
          aria-label={t("ws.orderLabel")} placeholder={t("ws.defaultOrder")}
          disabled={running || busy}
          className="min-w-0 flex-1 rounded-xl border border-line bg-panel2 px-3 py-1.5
            text-sm outline-none focus:border-[color:var(--accent)] disabled:opacity-60" />
        {running ? (
          <Button tone="danger" onClick={() => void stop()}>{t("ws.stop")}</Button>
        ) : (
          <Button tone="primary" type="submit" disabled={busy}>{t("ws.start")}</Button>
        )}
      </form>
      {error && <ErrorBox>{error}</ErrorBox>}
      {lanes.awaiting && !folded.done && (
        <p className="text-[11px]" style={{ color: "var(--st-approval)" }}>
          {t("ws.awaiting")} <Link href="/" className="underline">{t("ws.toOffice")}</Link>
        </p>
      )}
      <Steps step={lanes.step} />
    </header>
  );

  const office = (
    <Office employees={employees} tasks={tasks} lanes={lanes} spotTask={shownId}
      running={running} onPick={pickDesk} modelLabel={modelLabel}
      catalog={catalog} onModel={(id, m) => void setModel(id, m)} />
  );
  const board = (
    <Board tasks={tasks} slotState={slotState} planState={planState} shown={shownId}
      onPick={pick} nameOf={nameOf} done={!!folded.done} rejects={lanes.rejects} />
  );
  const log = (
    <section className="glass flex h-full flex-col overflow-hidden" aria-label={t("ws.log")}>
      <h2 className="border-b border-line px-3 py-2 text-[12px] font-semibold tracking-tight
        text-muted">{t("ws.log")}</h2>
      <div className="min-h-0 flex-1" data-testid="ws-log">
        {events.length === 0 ? (
          <p className="py-3 text-center text-[12px] text-dim">{t("ws.logEmpty")}</p>
        ) : (
          <ChatLog events={events} roster={stream.roster}
            connected={stream.connected} polling={stream.polling}
            slug={slug} className="h-full" />
        )}
      </div>
    </section>
  );
  const code = (
    <CodePane slug={slug} task={shownTask} plan={showPlan ? lanes.plan : null}
      planTasks={tasks} state={shownTask ? slotState(shownTask) : planState}
      wrote={shownTask ? lanes.wrote.get(shownTask.id) : undefined}
      verdict={shownTask ? lanes.verdict.get(shownTask.id) : undefined}
      follow={follow} nameOf={nameOf}
      onClose={phone ? () => setSheet(false) : undefined} />
  );

  return (
    <div ref={root} className="relative h-full">
      {phone ? (
        <div className="h-full space-y-3 overflow-y-auto px-3 py-3">
          {top}
          {office}
          {board}
          <div className="h-80">{log}</div>
          {sheet && (shownTask || showPlan) && (
            <div className="absolute inset-0 z-20 p-2"
              style={{ background: "var(--bg)" }}>{code}</div>
          )}
        </div>
      ) : (
        <div className="flex h-full flex-col gap-3 p-4">
          {top}
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-3">
            <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
              {office}
              {board}
            </div>
            <div className="min-h-0">{code}</div>
          </div>
          <div className="h-48 shrink-0">{log}</div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────── */

function Steps({ step }: { step: Step | null }) {
  const { t } = useLang();
  const at = step ? STEPS.indexOf(step) : -1;
  return (
    <ol className="flex flex-wrap items-center gap-1 text-[11px]">
      {STEPS.map((p, i) => {
        const done = at > i || step === "done";
        const now = at === i && step !== "done";
        return (
          <li key={p} className="flex items-center gap-1">
            {i > 0 && <span className="text-dim" aria-hidden>→</span>}
            <span className="flex items-center gap-1 rounded-md px-1.5 py-0.5"
              style={{
                background: now ? "var(--panel-2)" : undefined,
                color: done ? "var(--st-done)" : now ? "var(--st-working)" : "var(--dim)",
              }}
              aria-current={now ? "step" : undefined}>
              {now && <span className="size-1 animate-pulse rounded-full"
                style={{ background: "var(--st-working)" }} aria-hidden />}
              {done && <span aria-hidden>✓</span>}
              {t(`ws.step.${p}` as Key)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

type Lanes = ReturnType<typeof foldLanes>;
type DeskState = "idle" | "working" | "checking" | "done";
const DESK_COLOR: Record<DeskState, string> = {
  idle: "var(--st-idle-ring)",
  working: "var(--st-working)",
  checking: "var(--st-integration)",
  done: "var(--st-done)",
};

/** 사무실 — 직원 다섯의 자리. 분석가 자리가 곧 검수대다. 자리 아래가 버전 선택. */
function Office({
  employees, tasks, lanes, spotTask, running, onPick, modelLabel, catalog, onModel,
}: {
  employees: Employee[]; tasks: TaskRow[]; lanes: Lanes; spotTask: string | null;
  running: boolean; onPick: (id: string) => void; modelLabel: (e: Employee) => string;
  catalog: Record<string, { default: string; models: { id: string; label: string;
    tier: string }[] }>;
  onModel: (id: string, model: string) => void;
}) {
  const { t } = useLang();
  const desk = (e: Employee): { st: DeskState; note: string } => {
    if (lanes.step === "done") return { st: "done", note: "" };
    if (e.id === "strategist") {
      return lanes.step === "plan" && running
        ? { st: "working", note: t("ws.desk.planning") } : { st: "idle", note: "" };
    }
    if (e.id === "analyst") {
      const reviewing = tasks.filter((r) => r.status === "doing"
        && lanes.lane.get(r.id) === "REVIEW");
      if (reviewing.length) return { st: "checking", note: reviewing.map((r) => r.id).join(", ") };
      if (lanes.step === "tests" && running) return { st: "working", note: t("ws.desk.tests") };
      return { st: "idle", note: "" };
    }
    const mine = tasks.filter((r) => r.assignee === e.id && r.status === "doing");
    if (mine.length > 1) return { st: "working", note: t("ws.desk.clones", { n: mine.length }) };
    if (mine.length === 1) return { st: "working", note: mine[0].id };
    return { st: "idle", note: "" };
  };
  return (
    <section className="glass glass-lit p-3" aria-label={t("ws.office")}>
      <h2 className="mb-2 px-1 text-[12px] font-semibold tracking-tight text-muted">
        {t("ws.office")}
      </h2>
      {employees.length === 0 ? (
        <p className="px-1 py-3 text-[12px] text-dim">…</p>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          {employees.map((e) => {
            const d = desk(e);
            const color = `var(--${e.id}, var(--accent))`;
            const lit = (e.id === "strategist" && spotTask === PLAN_SLOT)
              || tasks.some((r) => r.id === spotTask && r.assignee === e.id);
            const options = catalog[e.provider]?.models ?? [];
            return (
              <div key={e.id} className="flex flex-col gap-1.5 rounded-xl border p-2.5"
                style={{ borderColor: lit ? color : "var(--line)",
                  boxShadow: lit ? `0 0 0 1px ${color}` : undefined }}
                data-testid={`ws-desk-${e.id}`}>
                <button type="button" onClick={() => onPick(e.id)}
                  className="flex flex-col items-start gap-1 rounded-lg text-left
                    transition hover:opacity-85">
                  <span className="flex w-full items-center gap-2">
                    <span className="relative grid size-8 shrink-0 place-items-center
                      rounded-full text-[12px] font-bold text-black"
                      style={{ background: color }}>
                      {e.name.slice(0, 1)}
                      <span className={`absolute -right-0.5 -top-0.5 size-2.5 rounded-full
                        border-2 ${d.st === "working" || d.st === "checking"
                          ? "animate-pulse" : ""}`}
                        style={{ background: DESK_COLOR[d.st], borderColor: "var(--bg)" }} />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[12px] font-semibold">{e.name}</span>
                      <span className="block truncate text-[10px] text-dim">
                        {t(`ws.seat.${e.id}` as Key)}
                      </span>
                    </span>
                  </span>
                  <span className="w-full truncate text-[11px]"
                    style={{ color: DESK_COLOR[d.st] }}>
                    {t(`ws.desk.${d.st}` as Key)}
                    {d.note && <span className="text-muted"> · {d.note}</span>}
                  </span>
                </button>
                {options.length > 0 ? (
                  <select value={e.model} disabled={running}
                    onChange={(ev) => onModel(e.id, ev.target.value)}
                    aria-label={t("ws.version", { who: e.name })}
                    title={running ? t("ws.versionLocked") : t("ws.versionHint")}
                    className="w-full min-w-0 rounded-md border border-line bg-panel2 px-1.5
                      py-1 text-[11px] outline-none focus:border-[color:var(--accent)]
                      disabled:opacity-55">
                    {!options.some((o) => o.id === e.model) && (
                      <option value={e.model}>{modelLabel(e)}</option>
                    )}
                    {options.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}{TIERS.has(o.tier) ? ` · ${t(`ws.tier.${o.tier}` as Key)}` : ""}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="truncate text-[11px] text-dim">{modelLabel(e)}</span>
                )}
                {e.mock && <span className="text-[10px]" style={{ color: "var(--mock)" }}>
                  {t("ws.mockSeat")}</span>}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
const TIERS = new Set(["fast", "balanced", "max"]);

/** 플레이스 — 계획이 깐 슬롯들. 누르면 코드 창이 그 슬롯을 비춘다. */
function Board({
  tasks, slotState, planState, shown, onPick, nameOf, done, rejects,
}: {
  tasks: TaskRow[]; slotState: (r: TaskRow) => SlotState; planState: SlotState;
  shown: string | null; onPick: (id: string) => void; nameOf: (id: string) => string;
  done: boolean; rejects: Map<string, number>;
}) {
  const { t } = useLang();
  const passed = tasks.filter((r) => r.status === "done").length;
  const rows: { id: string; label: string; file: string; spec: string; owner: string;
    st: SlotState; rework: number }[] = [
    { id: PLAN_SLOT, label: t("ws.slot.plan"), file: t("ws.slot.planFile"),
      spec: t("ws.slot.planSpec"), owner: "strategist", st: planState, rework: 0 },
    ...tasks.map((r) => ({
      id: r.id, label: r.id, file: r.files?.[0] ?? "—",
      spec: r.done_when ?? r.title, owner: r.assignee, st: slotState(r),
      rework: rejects.get(r.id) ?? 0,
    })),
  ];
  return (
    <section className="glass glass-lit p-3" aria-label={t("ws.board")}>
      <h2 className="mb-2 flex items-center gap-2 px-1 text-[12px] font-semibold
        tracking-tight text-muted">
        {t("ws.board")}
        {tasks.length > 0 && (
          <span className="font-normal tabular-nums text-dim">{passed}/{tasks.length}</span>
        )}
        {done && (
          <span className="ml-auto font-normal" style={{ color: "var(--st-done)" }}>
            ✓ {t("ws.merged")}
          </span>
        )}
      </h2>
      {tasks.length === 0 && planState === "todo" ? (
        <p className="px-1 py-4 text-center text-[12px] text-dim">{t("ws.boardEmpty")}</p>
      ) : (
        <ul className="space-y-1" data-testid="ws-board">
          {rows.map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => onPick(s.id)}
                aria-current={s.id === shown ? "true" : undefined}
                className="grid w-full grid-cols-[3.6rem_minmax(0,1fr)_auto] items-center gap-2
                  rounded-lg px-2 py-1.5 text-left text-[12px] transition hover:bg-panel2"
                style={{ background: s.id === shown ? "var(--panel-2)" : undefined }}>
                <span className="flex items-center gap-1.5 font-semibold">
                  <span className={`size-2 shrink-0 rounded-full ${
                    s.st === "writing" ? "animate-pulse" : ""}`}
                    style={{ background: SLOT_COLOR[s.st] }} aria-hidden />
                  <span className="truncate">{s.label}</span>
                </span>
                <span className="min-w-0" data-record={s.id === PLAN_SLOT ? undefined : ""}>
                  <span className="block truncate font-mono text-[11px]">{s.file}</span>
                  <span className="block truncate text-[10px] text-dim">{s.spec}</span>
                </span>
                <span className="flex flex-col items-end text-[10px]">
                  <span style={{ color: `var(--${s.owner}, var(--muted))` }}>{nameOf(s.owner)}</span>
                  <span style={{ color: SLOT_COLOR[s.st] }}>
                    {t(`ws.slot.${s.st}` as Key)}
                    {s.rework > 0 && ` · ${t("ws.rework", { n: s.rework })}`}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** 코드 창 — 슬롯 하나가 실제로 쓴 파일. 쓸 때마다 다시 읽는다. */
function CodePane({
  slug, task, plan, planTasks, state, wrote, verdict, follow, nameOf, onClose,
}: {
  slug: string | null; task: TaskRow | null; plan: BusEvent | null; planTasks: TaskRow[];
  state: SlotState; wrote?: { files: string[]; n: number }; verdict?: BusEvent;
  follow: boolean; nameOf: (id: string) => string; onClose?: () => void;
}) {
  const { t } = useLang();
  const files = useMemo(() => [...new Set([...(task?.files ?? []), ...(wrote?.files ?? [])])],
    [task?.files, wrote?.files]);
  const [tab, setTab] = useState<string | null>(null);
  const path = tab && files.includes(tab) ? tab : files[0] ?? null;
  const [content, setContent] = useState<{ path: string; text: string } | null>(null);
  const [missing, setMissing] = useState(false);

  // 쓸 때마다(wrote.n 이 바뀔 때마다) 다시 읽는다.
  useEffect(() => {
    if (!slug || !path) return;
    let live = true;
    api.projectFile(slug, path).then((r) => {
      if (!live) return;
      setContent({ path, text: r.content });
      setMissing(false);
    }).catch(() => {
      if (live) setMissing(true);
    });
    return () => {
      live = false;
    };
  }, [slug, path, wrote?.n]);

  const edge = SLOT_COLOR[state];
  const failed = verdict?.verdict === "fail" && state !== "passed";
  const lang = path ? langOf(path) : null;
  const text = content && content.path === path ? content.text : "";
  const lines = text ? text.split("\n") : [];

  return (
    <section className="glass flex h-full flex-col overflow-hidden"
      style={{ borderColor: task || plan ? edge : undefined }}
      aria-label={t("ws.code")} data-testid="ws-code">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2 text-[12px]">
        {task ? (
          <>
            <span className="font-semibold">{task.id}</span>
            <span data-record className="min-w-0 truncate text-muted">{task.title}</span>
            <span className="ml-auto shrink-0"
              style={{ color: `var(--${task.assignee}, var(--muted))` }}>
              {nameOf(task.assignee)}
            </span>
            <span className="shrink-0 text-[11px]" style={{ color: edge }}>
              {t(`ws.slot.${state}` as Key)}
            </span>
          </>
        ) : plan ? (
          <>
            <span className="font-semibold">{t("ws.slot.plan")}</span>
            <span className="ml-auto shrink-0" style={{ color: "var(--strategist)" }}>
              {nameOf("strategist")}
            </span>
          </>
        ) : (
          <span className="text-muted">{t("ws.code")}</span>
        )}
        {follow && (task || plan) && (
          <span className="shrink-0 rounded px-1 text-[10px]"
            style={{ color: "var(--st-working)", background: "var(--panel-2)" }}>
            {t("ws.following")}
          </span>
        )}
        {onClose && (
          <button type="button" onClick={onClose}
            className="ml-1 shrink-0 rounded-md border border-line px-2 py-0.5 text-[11px]">
            {t("ws.close")}
          </button>
        )}
      </header>
      {task && files.length > 1 && (
        <div className="flex gap-1 overflow-x-auto border-b border-line px-2 py-1" role="tablist">
          {files.map((f) => (
            <button key={f} type="button" role="tab" aria-selected={f === path}
              onClick={() => setTab(f)}
              className="shrink-0 rounded-md px-2 py-0.5 font-mono text-[11px]"
              style={{ background: f === path ? "var(--panel-2)" : undefined,
                color: f === path ? "var(--fg)" : "var(--muted)" }}>
              {f}
            </button>
          ))}
        </div>
      )}
      {task && (
        <p className="border-b border-line px-3 py-1.5 text-[11px] text-dim">
          <span className="text-muted">{t("ws.spec")}</span>{" "}
          <span data-record>{task.done_when ?? task.title}</span>
          {task.deps && task.deps.length > 0 && <> · {t("ws.after", { deps: task.deps.join(", ") })}</>}
        </p>
      )}
      {failed && (
        <div className="border-b px-3 py-1.5 text-[11px]" data-testid="ws-reject" data-record
          style={{ color: "var(--bad)", borderColor: "var(--bad)",
            background: "color-mix(in srgb, var(--bad) 10%, transparent)" }}>
          <p className="font-semibold">✕ {t("ws.rejected", { who: nameOf(verdict?.from ?? "analyst") })}</p>
          {(verdict?.findings ?? []).slice(0, 3).map((f, i) => (
            <p key={i} className="font-mono">{f.file}: {f.issue}</p>
          ))}
          {!verdict?.findings?.length && (verdict?.required_fixes ?? []).slice(0, 2).map((f, i) => (
            <p key={i}>{f}</p>
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto" data-record>
        {plan ? (
          <PlanView plan={plan} tasks={planTasks} nameOf={nameOf} />
        ) : !task ? (
          <p className="grid h-full place-items-center px-6 text-center text-[12px] text-dim">
            {t("ws.codeEmpty")}
          </p>
        ) : !text ? (
          <p className="px-4 py-6 text-[12px] text-dim">
            {missing || !wrote ? t("ws.notWritten") : "…"}
          </p>
        ) : (
          <pre className="py-2 font-mono text-[11.5px] leading-[1.55]"
            style={{ color: "var(--code-fg)" }}>
            {lines.map((ln, i) => (
              <div key={i} className="flex">
                <span className="w-10 shrink-0 select-none pr-3 text-right text-dim">{i + 1}</span>
                <code className="whitespace-pre pr-4">{highlightLine(ln, lang)}</code>
              </div>
            ))}
          </pre>
        )}
      </div>
    </section>
  );
}

/** 계획 = 설계도. 인수기준과 슬롯(태스크) 목록. */
function PlanView({ plan, tasks, nameOf }: {
  plan: BusEvent; tasks: TaskRow[]; nameOf: (id: string) => string;
}) {
  const { t } = useLang();
  return (
    <div className="space-y-3 p-4 text-[12px]">
      {(plan.criteria?.length ?? 0) > 0 && (
        <div>
          <p className="mb-1 font-semibold text-muted">{t("ws.criteria")}</p>
          <ul className="space-y-0.5">
            {plan.criteria!.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}
      <div>
        <p className="mb-1 font-semibold text-muted">{t("ws.slots")}</p>
        <ul className="space-y-1">
          {tasks.map((r) => (
            <li key={r.id} className="grid grid-cols-[2.5rem_minmax(0,1fr)_auto] gap-2">
              <span className="font-semibold">{r.id}</span>
              <span className="min-w-0">
                <span className="block truncate">{r.title}</span>
                <span className="block truncate font-mono text-[11px] text-dim">
                  {(r.files ?? []).join(", ")}
                </span>
              </span>
              <span style={{ color: `var(--${r.assignee}, var(--muted))` }}>{nameOf(r.assignee)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
