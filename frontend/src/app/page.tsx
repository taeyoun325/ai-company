"use client";

/**
 * 사무실 — 작업 화면 (지시서 §4 · §10 · §11 · DAY 25 전면 개편).
 *
 * ## 사규대로 움직이는 사무실
 *
 * DAY 25 에 화면을 사규(인원 편성 · 직원 상태 · 하루 시나리오 · 대표
 * 지시창)의 모양으로 다시 짰다:
 *
 * 1. **결재함** — 대표 결정이 필요하면 맨 위에 선다. 승인 · 수정 요청 ·
 *    보류 · 폐기. 한 번에 하나씩.
 * 2. **하루 시나리오** — 출근부터 비서실 브리핑까지 12단계 중 지금 어디인가.
 *    ★ 은 대표 승인 지점이다.
 * 3. **평면도** — 부서 자리 · 회의실 · 대표실 · 비서실 · 휴게실. 직원은
 *    상태 다섯 가지(완료 · 진행 중 · 승인 대기 · 연동 대기 · 대기)로
 *    색과 말풍선을 달고, 상태가 바뀐 이유를 한 줄 달고 있다.
 * 4. **대표 지시창** — "현황 보고" · "왜 늦어져?" · "[이름] 뭐해?" ·
 *    "회의 소집" · "지금 브리핑" · "집중 모드" · "승인할게".
 * 5. **일 맡기기** — AUTO · 직접 지시, 그리고 이번 일의 승인 지점.
 *
 * 직원 상태는 서버가 정한다(backend/app/office.py). 여기서 짐작하면 "무엇을
 * 완료로 치나" 같은 규칙이 화면과 서버 두 곳에 살게 된다.
 *
 * ## 로그는 그대로 오른쪽에
 *
 * 사무실은 "지금"을, 로그는 "지금까지"를 보여준다. 둘 다 동시에 필요하다.
 *
 * ## Mock 경고는 접히지 않는다
 *
 * 접히거나 사라지는 경고는 아무도 안 본다. 그 상태에서 나온 산출물을
 * 실제 AI 의 작업 결과로 믿는 순간이 이 제품에서 제일 나쁜 순간이다.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatLog } from "@/components/ChatLog";
import { GateToggles } from "@/components/GateToggles";
import { RecentResults } from "@/components/RecentResults";
import { ProjectRail } from "@/components/ProjectRail";
import { ResizeHandle } from "@/components/ResizeHandle";
import { ScorePanel, TaskBoard } from "@/components/TaskBoard";
import { ApprovalDesk } from "@/components/office/ApprovalDesk";
import { CommandWindow } from "@/components/office/CommandWindow";
import { EmployeeCard, IntegrationList } from "@/components/office/EmployeeCard";
import { type MeetingCall, OfficeFloor } from "@/components/office/OfficeFloor";
import { ScenarioStrip } from "@/components/office/ScenarioStrip";
import { Button, ErrorBox, Panel, Skeleton, Warning, num } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useErrorText, useLang } from "@/lib/i18n";
import { T, animate, stagger, withScope } from "@/lib/motion";
import { useSessionFlag, useSticky, useStickyNumber } from "@/lib/sticky";
import type { AskAnswer, CreditStatus, ProviderStatus } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { useOffice } from "@/lib/useOffice";
import { foldState, useStream } from "@/lib/useStream";

const LOG_WIDTH_KEY = "ai-company.log-width";
const LOG_WIDTH_DEFAULT = 336; // 21rem, 기존 고정폭과 같다
const LOG_WIDTH_MIN = 260;
const LOG_WIDTH_MAX = 560;
// 이보다 넓어야 로그와 최근 결과를 나란히 둔다. 좁으면 위아래로 쌓는다.
const LOG_SPLIT_MIN = 440;

/** 사무실을 다시 읽어야 하는 이벤트 — 사람의 자리나 상태가 바뀌는 것들. */
const PULSE_TYPES = new Set(["phase", "gate", "awaiting", "done", "handoff"]);

export default function OfficePage() {
  const router = useRouter();
  const { t, lang } = useLang();
  const errText = useErrorText();
  const [slug, setSlug] = useState<string | null>(null);
  const { data: state, error: loadError } = useLoader(
    "state", () => api.state(),
  );
  const providers: ProviderStatus | null = state?.providers ?? null;
  const wallet: CreditStatus | null = state?.credits ?? null;
  const [requirement, setRequirement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [routing, setRouting] = useState<{ employee: string; why: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [gates, setGates] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [meetingCall, setMeetingCall] = useState<MeetingCall | null>(null);
  const [arrivalKey, setArrivalKey] = useState<string | null>(null);
  const [focus, setFocus] = useSticky("ai-company.focus", false);
  const root = useRef<HTMLDivElement>(null);
  const work = useRef<HTMLElement>(null);

  const stream = useStream(slug ?? undefined);
  const folded = foldState(stream.events);

  // 사무실은 로그가 **자리를 바꾸는 사건**을 낼 때만 바로 다시 읽는다.
  const pulse = useMemo(() => {
    for (let i = stream.events.length - 1; i >= 0; i--) {
      const e = stream.events[i];
      if (PULSE_TYPES.has(e.type) || (e.type === "state" && e.active)) return e.id;
    }
    return 0;
  }, [stream.events]);
  const office = useOffice(slug, pulse);
  const snap = office.data;
  const run = snap?.run ?? null;
  const running = run?.status === "running";

  // 들어왔을 때 돌고 있거나 결재를 기다리는 실행이 있으면 그 사무실을 연다.
  // 새로고침했다고 일하던 사무실이 빈 방이 되면, 대표는 일이 멈춘 줄 안다.
  useEffect(() => {
    let live = true;
    const fromUrl = new URLSearchParams(window.location.search).get("run");
    if (fromUrl) {
      // 주소창은 렌더 밖의 값이다 — 첫 그림(서버)에는 없으므로 하이드레이션
      // 뒤에 한 번 읽는다. 초기값으로 읽으면 서버와 브라우저의 첫 그림이
      // 달라진다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSlug(fromUrl);
      return;
    }
    api.runs().then((r) => {
      if (!live) return;
      const awaiting = r.projects.find((p) => p.status === "awaiting");
      const pick = r.running[0] ?? awaiting?.slug ?? null;
      if (pick) setSlug((cur) => cur ?? pick);
    }).catch(() => { /* 사무실은 빈 방으로 뜬다 */ });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    return withScope(el, () => {
      animate(el.querySelectorAll("[data-enter]"), {
        opacity: [0, 1], translateY: [10, 0], duration: T.base,
        ease: T.ease, delay: stagger(T.step),
      });
    });
  }, []);

  const start = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setRouting(null);
    stream.clear();
    try {
      const r = await api.startRun(text, { gates });
      setSlug(r.slug);
      setArrivalKey(r.slug);          // ① 전원 출근
      window.history.replaceState(null, "", `/?run=${encodeURIComponent(r.slug)}`);
      work.current?.scrollTo({ top: 0 });
    } catch (e) {
      setError(
        e instanceof ApiError && e.isBudget
          ? e.message
          : e instanceof ApiError && e.isBusy
            ? `${e.message} ${t("run.concurrentNote")}`
            : errText(e),
      );
    } finally {
      setBusy(false);
    }
  };

  const askRouting = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      setRouting(await api.route(text));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const openManual = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const r = await api.openManual(text);
      router.push(`/manual/${r.slug}`);
    } catch (e) {
      setError(errText(e));
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!slug) return;
    try {
      await api.cancelRun(slug);
      void office.reload();
    } catch (e) {
      setError(errText(e));
    }
  };

  const updateGates = async (next: string[]) => {
    if (!slug || !run || run.status === "done") {
      setGates(next);
      return;
    }
    try {
      await api.setGates(slug, next);
      void office.reload();
    } catch (e) {
      setError(errText(e));
    }
  };

  // 지시창의 답이 사무실을 움직인다 — 회의 소집 · 집중 모드 · 결재.
  const onAction = (a: AskAnswer) => {
    if (a.action?.focus !== undefined) setFocus(a.action.focus);
    if (a.action?.meeting) {
      setMeetingCall({ who: a.action.meeting, lines: a.lines, startedAt: Date.now() });
    }
    if (a.action?.decided) void office.reload();
  };

  const [logWidthStored, setLogWidthStored] = useStickyNumber(
    LOG_WIDTH_KEY, LOG_WIDTH_DEFAULT,
  );
  const [logWidthDrag, setLogWidthDrag] = useState<number | null>(null);
  const logWidth = logWidthDrag ?? logWidthStored;
  const commitLogWidth = (w: number) => {
    setLogWidthDrag(null);
    setLogWidthStored(w);
  };

  const allMock = providers?.all_mock ?? false;
  const [mockDismissed, dismissMockWarn] = useSessionFlag("mock-warn-dismissed");
  const picked = snap?.employees.find((e) => e.id === selected) ?? null;

  // 팀 배치 (DAY 26) — 평면도에서 끌어다 놓거나 직원 카드에서 고른다.
  // 실패하면(없는 팀 · 연결 끊김) 다시 읽어 원래 자리로 돌린다.
  const moveTeam = async (id: string, team: string) => {
    setError(null);
    try {
      await api.updateEmployee(id, { team });
    } catch (e) {
      setError(errText(e));
    } finally {
      await office.reload();
    }
  };
  const liveGates = run && run.status !== "done" ? snap?.gates ?? [] : gates;

  return (
    <div ref={root} className="flex h-full">
      <ProjectRail
        activeSlug={slug}
        phase={folded.phase}
        refreshKey={slug ? `${slug}-${folded.done}-${folded.phase ?? ""}-${run?.status ?? ""}`
          : "idle"}
        onNew={() => {
          setSlug(null);
          setRequirement("");
          stream.clear();
          window.history.replaceState(null, "", "/");
        }}
      />

      <section ref={work} className="min-w-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto max-w-[920px] space-y-3">
          {allMock && !mockDismissed && (
            <div data-enter>
              <Warning onClose={dismissMockWarn} closeLabel={t("run.mockWarnClose")}>
                <strong>{t("run.mockWarn")}</strong>{" "}
                <Linked text={t("run.mockWarnBody")} label={t("run.mockWarnLink")}
                  href="/settings" />
              </Warning>
            </div>
          )}
          {providers && !allMock && !providers.cross_check && (
            <div data-enter>
              <Warning>
                <strong>{t("run.noCross")}</strong> {t("run.noCrossBody")}
              </Warning>
            </div>
          )}
          {(error || loadError || office.error) && (
            <div data-enter>
              <ErrorBox>{error ?? loadError ?? office.error}</ErrorBox>
            </div>
          )}

          {/* 머리 — 회사 이름 · 지금 프로젝트 · 집중 모드 */}
          <div data-enter className="flex flex-wrap items-center gap-2 px-1">
            <h1 className="text-[13px] font-semibold tracking-tight">{t("office.title")}</h1>
            {run && (
              <span className="min-w-0 truncate text-[12px] text-muted">
                · {run.name}
                <span className="ml-1.5 text-dim">
                  {t(`list.${run.status}` as Parameters<typeof t>[0])}
                  {run.tasks_total > 0 && ` · ${run.tasks_done}/${run.tasks_total}`}
                </span>
              </span>
            )}
            <span className="ml-auto flex items-center gap-2">
              {running && (
                <span className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="size-1.5 animate-pulse rounded-full"
                    style={{ background: "var(--st-working)" }} />
                  {t("list.running")}
                </span>
              )}
              <button type="button" onClick={() => setFocus(!focus)}
                aria-pressed={focus}
                className="rounded-full border px-2.5 py-0.5 text-[11px] transition"
                style={{
                  borderColor: focus ? "var(--st-working)" : "var(--line)",
                  color: focus ? "var(--st-working)" : "var(--muted)",
                }}>
                {focus ? t("office.focusOn") : t("office.focusOff")}
              </button>
              {slug && run && (
                <a href={`/projects/${encodeURIComponent(slug)}`}
                  className="text-[11px] text-dim hover:text-fg">
                  {t("run.detail")} →
                </a>
              )}
            </span>
          </div>

          {/* ⑦ 대표 승인 — 결정할 일이 있으면 맨 위 */}
          {slug && snap && snap.approvals.length > 0 && (
            <div data-enter>
              <ApprovalDesk slug={slug} approvals={snap.approvals}
                onDecided={() => void office.reload()} />
            </div>
          )}

          {snap ? (
            <div data-enter className="space-y-2">
              <ScenarioStrip steps={snap.scenario} />
              <OfficeFloor snap={snap} events={stream.events} focus={focus}
                meetingCall={meetingCall} selected={selected} onSelect={setSelected}
                onMove={moveTeam}
                arrivalKey={arrivalKey} />
              {picked && (
                <EmployeeCard e={picked} items={snap.integrations}
                  onMove={(team) => void moveTeam(picked.id, team)}
                  onClose={() => setSelected(null)} />
              )}
              <IntegrationList items={snap.integrations} />
            </div>
          ) : (
            <div className="glass glass-lit p-4"><Skeleton lines={8} /></div>
          )}

          <div data-enter className="grid gap-3 lg:grid-cols-2">
            <CommandWindow run={slug} snap={snap} focus={focus} onAction={onAction} />

            {/* 일 맡기기 */}
            <Panel title={t("office.ask")}
              right={slug && <span className="truncate text-[11px] text-dim">
                <code>{slug}</code></span>}>
              <textarea
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                rows={3}
                // 자리표시 글은 이름이 아니다 — 쓰기 시작하면 사라지고, 화면
                // 낭독기는 "편집 가능한 글"로만 읽는다 (DAY 26 화면 시험에서 찾음).
                aria-label={t("office.ask")}
                placeholder={t("office.placeholder")}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void start();
                }}
                className="w-full resize-y rounded-xl border border-line bg-[color:var(--panel-2)]
                  px-3 py-2 text-sm outline-none backdrop-blur
                  placeholder:text-dim focus:border-accent"
              />
              <p className="mb-1 mt-2 text-[11px] text-dim">
                {run && run.status !== "done" ? t("gate.liveTitle") : t("gate.title")}
              </p>
              <GateToggles value={liveGates} onChange={(g) => void updateGates(g)} />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button tone="primary" onClick={start}
                  disabled={busy || running || run?.status === "awaiting"
                    || !requirement.trim()}>
                  {t("office.auto")}
                </Button>
                <Button onClick={openManual} disabled={busy || !requirement.trim()}>
                  {t("office.manual")}
                </Button>
                <Button tone="ghost" onClick={askRouting}
                  disabled={busy || !requirement.trim()}>
                  {t("office.whoFirst")}
                </Button>
                {(running || run?.status === "awaiting") && (
                  <Button tone="danger" onClick={cancel} className="ml-auto">
                    {t("proj.stop")}
                  </Button>
                )}
              </div>
              {(folded.files?.length ?? 0) > 0 && (
                <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="text-dim">{t("run.made")}</span>
                  {folded.files!.slice(0, 6).map((f) => (
                    <span key={f} className="rounded-md bg-panel2 px-1.5 py-0.5 font-mono">
                      <span className="text-dim">{f.slice(0, f.lastIndexOf("/") + 1)}</span>
                      {f.slice(f.lastIndexOf("/") + 1)}
                    </span>
                  ))}
                  {folded.files!.length > 6 && (
                    <span className="text-dim">+{folded.files!.length - 6}</span>
                  )}
                </p>
              )}
              {routing && (
                <p className="mt-2 text-xs text-muted">
                  {t("run.routing")}:{" "}
                  <strong style={{ color: `var(--${routing.employee}, var(--accent))` }}>
                    {routing.employee}
                  </strong>{" "}
                  — {routing.why}
                </p>
              )}
            </Panel>
          </div>

          {/* 좁은 화면에는 오른쪽 레일이 없다 — 점수·태스크·로그를 여기로 내린다. */}
          {(slug || stream.events.length > 0) && (
            <div data-enter className="space-y-3 lg:hidden">
              <Panel title={t("proj.score")}>
                <ScorePanel score={folded.score} detail={folded.scoreDetail}
                  cost={folded.totals?.cost} round={folded.round} />
              </Panel>
              {(folded.tasks?.length ?? 0) > 0 && (
                <Panel title={t("proj.tasks")}>
                  <TaskBoard tasks={folded.tasks} />
                </Panel>
              )}
              <Panel title={t("office.log")} className="overflow-hidden">
                <div className="-m-4">
                  {stream.events.length === 0 ? (
                    <p className="px-4 py-6 text-center text-xs text-dim">
                      {t("office.logEmpty")}
                    </p>
                  ) : (
                    <ChatLog events={stream.events} roster={stream.roster}
                      connected={stream.connected} polling={stream.polling}
                      slug={slug} className="h-[22rem]" />
                  )}
                </div>
              </Panel>
            </div>
          )}
        </div>
      </section>

      <ResizeHandle
        width={logWidth}
        onChange={setLogWidthDrag}
        onCommit={commitLogWidth}
        min={LOG_WIDTH_MIN}
        max={LOG_WIDTH_MAX}
        side="left"
        label={t("office.logResize")}
        className="hidden lg:block"
      />
      <aside
        style={{ width: logWidth }}
        className="hidden h-full shrink-0 flex-col border-l border-line
          bg-[color:var(--panel)] backdrop-blur-xl lg:flex"
        data-enter
      >
        <div className="flex items-center justify-between px-3 py-3">
          <span className="flex min-w-0 items-center gap-1.5 text-[13px]
            font-semibold tracking-tight">
            {t("office.log")}
            {running && folded.phase && (
              <span className="flex min-w-0 items-center gap-1 rounded-md
                px-1.5 py-0.5 text-[10px] font-medium"
                style={{ background: "var(--panel-2)", color: "var(--accent)" }}>
                <span className="size-1 animate-pulse rounded-full"
                      style={{ background: "var(--accent)" }} aria-hidden />
                <span className="truncate">{folded.phase}</span>
              </span>
            )}
          </span>
          {wallet && (
            <a href="/pricing" className="text-[11px] text-dim hover:text-fg">
              {num(wallet.balance, lang)} · {wallet.plan_label}
            </a>
          )}
        </div>

        {/* 레일이 좁으면 최근 결과를 로그 **아래**로 내린다 (DAY 26). 기본 폭
            336px 를 반씩 나누면 로그 칸이 168px 이 되어 "연결됨"이 한 글자씩
            세로로 줄바꿈됐다 — 화면 시험을 만들며 찾았다. */}
        <div className={`grid min-h-0 flex-1 border-t border-line overflow-hidden ${
          logWidth >= LOG_SPLIT_MIN
            ? "grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] divide-x divide-line"
            : "grid-rows-[minmax(0,1fr)_auto] divide-y divide-line"}`}>
          <div className="min-h-0 overflow-y-auto" data-testid="activity-log">
            {stream.events.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-dim">
                {t("office.logEmpty")}
              </p>
            ) : (
              <ChatLog events={stream.events} roster={stream.roster}
                connected={stream.connected} polling={stream.polling}
                slug={slug} className="h-full" />
            )}
          </div>
          <div className={`min-h-0 overflow-y-auto ${
            logWidth >= LOG_SPLIT_MIN ? "" : "max-h-44"}`}>
            <RecentResults />
          </div>
        </div>

        {(slug || stream.events.length > 0) && (
          <div className="shrink-0 space-y-3 border-t border-line p-3">
            <ScorePanel score={folded.score} detail={folded.scoreDetail}
              cost={folded.totals?.cost} round={folded.round} />
            {(folded.tasks?.length ?? 0) > 0 && <TaskBoard tasks={folded.tasks} />}
            {slug && (folded.files?.length ?? 0) > 0 && (
              <Button className="w-full" onClick={() => router.push(`/projects/${slug}`)}>
                {t("run.detail")} ({folded.files?.length ?? 0})
              </Button>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

/**
 * 문장 안의 한 조각만 링크로 만든다.
 *
 * 번역문마다 링크가 놓이는 **자리가 다르다** — 한국어는 앞, 영어는
 * 가운데다. 문장을 앞뒤로 쪼개 두면 언어마다 어순이 어긋난다.
 */
function Linked({ text, label, href }: {
  text: string; label: string; href: string;
}) {
  const [before, after = ""] = text.split("{link}");
  return (
    <>
      {before}
      <a href={href} className="underline">
        {label}
      </a>
      {after}
    </>
  );
}
