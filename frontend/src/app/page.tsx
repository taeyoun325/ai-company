"use client";

/**
 * 사무실 — 작업 화면 (지시서 §4 · §10 · §11 · DAY 22 개편).
 *
 * ## 한 화면에서 끝난다
 *
 * 왼쪽에 프로젝트 목록, 가운데에 사무실과 입력창, 오른쪽에 작업 로그.
 * 셋 다 **동시에 필요한 것**이라 탭으로 나누면 오가느라 맥락을 잃는다.
 * 창 높이에 맞춰 고정하고 각 칸만 따로 스크롤한다 — 로그를 읽는 동안
 * 사무실이 화면 밖으로 나가면 지금 누가 일하는지 볼 수 없다.
 *
 * ## 사무실이 먼저, 입력창이 바로 밑
 *
 * CEO 가 하는 일은 둘뿐이다: 일을 맡기거나(AUTO), 직원을 지목해 직접
 * 시키거나(MANUAL). 그 둘의 입구가 사무실 바로 아래 있어야, 지시하기
 * 전에 **누가 있는지 보고** 지시하게 된다.
 *
 * ## Mock 경고는 접히지 않는다
 *
 * 접히거나 사라지는 경고는 아무도 안 본다. 그 상태에서 나온 산출물을
 * 실제 AI 의 작업 결과로 믿는 순간이 이 제품에서 제일 나쁜 순간이다.
 */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatLog } from "@/components/ChatLog";
import { RecentResults } from "@/components/RecentResults";
import { Office } from "@/components/Office";
import { PixelOffice } from "@/components/PixelOffice";
import { ProjectRail } from "@/components/ProjectRail";
import { ScorePanel, TaskBoard } from "@/components/TaskBoard";
import { Button, ErrorBox, Panel, Skeleton, Warning, num } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useErrorText, useLang } from "@/lib/i18n";
import { T, animate, stagger, withScope } from "@/lib/motion";
import type { CreditStatus, Employee, ProviderStatus } from "@/lib/types";
import { useLoader, useReloadOn } from "@/lib/useLoader";
import { foldState, useStream } from "@/lib/useStream";

/** AUTO 에서 지금 일하는 직원. 단계 이름이 자리를 가리킨다. */
const PHASE_OWNER: Record<string, string[]> = {
  PLAN: ["strategist"],
  REPLAN: ["strategist"],
  FINALIZE: ["strategist"],
  WRITE_TESTS: ["analyst"],
  REVIEW: ["analyst"],
  TEST: [],
  IMPLEMENT: ["developer", "writer", "designer"],
  MANUAL: [],
};

export default function OfficePage() {
  const router = useRouter();
  const { t, lang } = useLang();
  const errText = useErrorText();
  const [slug, setSlug] = useState<string | null>(null);
  // 실행 slug 를 같이 보낸다. 안 보내면 직원별 사용량이 전부 0 으로 와서,
  // 한창 일하는 중인데 사무실이 "아무도 일하지 않음"으로 보인다.
  const { data: state, error: loadError, loading, reload } = useLoader(
    slug ?? "", () => api.state(slug ?? undefined),
  );
  const employees: Employee[] = state?.employees ?? [];
  const providers: ProviderStatus | null = state?.providers ?? null;
  const wallet: CreditStatus | null = state?.credits ?? null;
  const [requirement, setRequirement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [routing, setRouting] = useState<{ employee: string; why: string } | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  // 가운데 칸(사무실·입력·직원 카드)의 스크롤 상자.
  const work = useRef<HTMLElement>(null);

  const stream = useStream(slug ?? undefined);
  const folded = foldState(stream.events);
  // 진행 중인가는 **계산 결과**다. 따로 상태로 들고 있으면 done 이벤트를
  // 놓쳤을 때 버튼이 영영 잠긴 채로 남는다.
  const running = slug !== null && folded.done === null;

  // 실행 중에는 직원별 사용량이 계속 바뀐다. 단계가 넘어갈 때만 다시
  // 읽는다 — 고정 간격 폴링은 아무 일도 없을 때까지 서버를 두드린다.
  // slug 가 바뀌는 순간은 `useLoader` 가 이미 읽는다(key 가 slug 다).
  // 여기서는 **단계가 넘어갈 때만** 읽는다.
  useReloadOn(slug ? `${folded.phase}-${folded.done}` : null, reload);

  // 화면이 들어올 때 한 번. 작업 중에는 아무것도 움직이지 않는다 —
  // 도구에서 움직임은 소음이고, 소음이 늘면 진짜 신호(맥박)가 묻힌다.
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

  const isWorking = (id: string) => {
    if (!folded.phase) return false;
    const owners = PHASE_OWNER[folded.phase] ?? [];
    if (owners.length > 1 && folded.detail) {
      const e = employees.find((x) => folded.detail!.includes(x.name));
      return e ? e.id === id : owners.includes(id);
    }
    return owners.includes(id);
  };

  const start = async () => {
    const text = requirement.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setRouting(null);
    stream.clear();
    try {
      const r = await api.startRun(text);
      setSlug(r.slug);
      // 시작 버튼은 사무실 **아래**에 있다. 누르는 순간 화면은 입력칸에
      // 맞춰져 있고, 정작 일이 벌어지는 사무실은 위로 밀려 잘려 있다.
      // 일을 맡겼으면 일하는 곳이 보여야 한다.
      // 부드럽게 올리면 실행이 시작되며 일어나는 다시 그리기에 끊긴다
      // (400 → 311 에서 멈췄다). 애니메이션 없이 즉시 올린다.
      work.current?.scrollTo({ top: 0 });
    } catch (e) {
      setError(
        // 402 는 두 가지다 — 요금제를 아직 안 골랐거나, 크레딧이 모자라거나.
        // 서버 문장이 이미 할 일을 말하고 있으면 덧붙이지 않는다.
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
    } catch (e) {
      setError(errText(e));
    }
  };

  const allMock = providers?.all_mock ?? false;

  return (
    <div ref={root} className="flex h-full">
      <ProjectRail
        activeSlug={slug}
        phase={folded.phase}
        // 단계가 바뀔 때마다 목록을 다시 읽는다. 시작할 때만 읽으면
        // 돌고 있는 줄이 목록에 "진행 중"으로 잡히는 창이 너무 짧고,
        // 끝난 뒤의 파일 수·크레딧도 늦게 반영된다.
        //
        // 다만 **실행 중이 아닐 때는 움직이지 않는다.** 새로고침하면
        // 버스가 지난 이벤트를 재생하면서 `folded.phase` 가 채워지는데,
        // 그때마다 키가 바뀌어 목록을 한 번 더 읽고 있었다(프로덕션
        // 빌드에서 `/api/projects` 가 두 번씩 나갔다).
        refreshKey={slug ? `${slug}-${folded.done}-${folded.phase ?? ""}` : "idle"}
        onNew={() => {
          setSlug(null);
          setRequirement("");
          stream.clear();
        }}
      />

      {/* 가운데 — 사무실과 입력창 */}
      <section ref={work} className="min-w-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto max-w-[640px] space-y-3">
          {allMock && (
            <div data-enter>
              <Warning>
                <strong>{t("run.mockWarn")}</strong>{" "}
                <Linked
                  text={t("run.mockWarnBody")}
                  label={t("run.mockWarnLink")}
                  href="/settings"
                />
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
          {(error || loadError) && (
            <div data-enter>
              <ErrorBox>{error ?? loadError}</ErrorBox>
            </div>
          )}

          {/* 사무실 */}
          <div data-enter className="space-y-1.5">
            <div className="flex items-center justify-between px-1">
              <h1 className="text-[13px] font-semibold tracking-tight">
                {t("office.title")}
              </h1>
              {/* 단계는 이제 탁자 가운데에 놓인다(PixelOffice). 여기에도
                  적으면 같은 말이 두 번 보이고, 눈이 어느 쪽을 봐야 하는지
                  모른다. 대신 실행 중이라는 사실만 표시한다. */}
              {running && (
                <span className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="size-1.5 animate-pulse rounded-full"
                        style={{ background: "var(--accent)" }} />
                  {t("list.running")}
                </span>
              )}
            </div>
            {loading && employees.length === 0 ? (
              // 사무실이 비어 보이면 "직원이 아무도 없다"로 읽힌다.
              // 방이 올 자리를 먼저 그려둔다.
              <div className="glass glass-lit p-4">
                <Skeleton lines={6} />
              </div>
            ) : (
            <PixelOffice
              employees={employees}
              working={isWorking}
              onPick={(id) => setPicked((p) => (p === id ? null : id))}
              picked={picked}
              phase={folded.phase}
              detail={folded.detail}
            />
            )}
          </div>

          {/* 입력창 — 사무실 바로 밑. 누가 있는지 보고 나서 지시한다. */}
          <div data-enter>
            <Panel
              title={t("office.ask")}
              right={
                slug && (
                  <span className="truncate text-[11px] text-dim">
                    <code>{slug}</code>
                  </span>
                )
              }
            >
              <textarea
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                rows={3}
                placeholder={t("office.placeholder")}
                onKeyDown={(e) => {
                  // 줄바꿈이 필요한 입력이라 Enter 로 보내지 않는다.
                  // 그래도 손을 옮기지 않고 보낼 길은 있어야 한다.
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void start();
                }}
                className="w-full resize-y rounded-xl border border-line bg-[color:var(--panel-2)]
                  px-3 py-2 text-sm outline-none backdrop-blur
                  placeholder:text-dim focus:border-accent"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button
                  tone="primary"
                  onClick={start}
                  disabled={busy || running || !requirement.trim()}
                >
                  {t("office.auto")}
                </Button>
                <Button onClick={openManual} disabled={busy || !requirement.trim()}>
                  {t("office.manual")}
                </Button>
                <Button
                  tone="ghost"
                  onClick={askRouting}
                  disabled={busy || !requirement.trim()}
                >
                  {t("office.whoFirst")}
                </Button>
                {running && (
                  <Button tone="danger" onClick={cancel} className="ml-auto">
                    {t("proj.stop")}
                  </Button>
                )}
              </div>
              {/* 만들어진 파일은 로그를 읽어야만 알 수 있었다. 오른쪽
                  레일의 버튼은 **개수**만 말한다 — 무엇이 생겼는지는
                  한 줄이면 보여줄 수 있다. */}
              {(folded.files?.length ?? 0) > 0 && (
                <p className="mt-2 flex flex-wrap items-center gap-1.5
                  text-[11px]">
                  <span className="text-dim">{t("run.made")}</span>
                  {folded.files!.slice(0, 6).map((f) => (
                    <span key={f}
                          className="rounded-md bg-panel2 px-1.5 py-0.5 font-mono">
                      <span className="text-dim">
                        {f.slice(0, f.lastIndexOf("/") + 1)}
                      </span>
                      {f.slice(f.lastIndexOf("/") + 1)}
                    </span>
                  ))}
                  {folded.files!.length > 6 && (
                    <span className="text-dim">
                      +{folded.files!.length - 6}
                    </span>
                  )}
                </p>
              )}
              {routing && (
                <p className="mt-2 text-xs text-muted">
                  {t("run.routing")}:{" "}
                  <strong
                    style={{ color: `var(--${routing.employee}, var(--accent))` }}
                  >
                    {routing.employee}
                  </strong>{" "}
                  — {routing.why}
                </p>
              )}
            </Panel>
          </div>

          {/* 좁은 화면에는 오른쪽 레일이 없다. 그때 로그가 통째로 사라지면
              지금 무슨 일이 일어나는지 볼 방법이 없어진다 — 가운데로 내린다. */}
          <div data-enter className="lg:hidden">
            <Panel title={t("office.log")} className="overflow-hidden">
              <div className="-m-4">
                {stream.events.length === 0 ? (
                  <p className="px-4 py-6 text-center text-xs text-dim">
                    {t("office.logEmpty")}
                  </p>
                ) : (
                  <ChatLog
                    events={stream.events}
                    roster={stream.roster}
                    connected={stream.connected}
                    polling={stream.polling}
                    className="h-[22rem]"
                  />
                )}
              </div>
            </Panel>
          </div>

          {/* 직원 카드 — 이름 바꾸기와 채용·해고가 여기 있다 */}
          <div data-enter>
            <Office
              employees={employees}
              phase={folded.phase}
              detail={folded.detail}
              picked={picked}
              onPick={(id) => setPicked((p) => (p === id ? null : id))}
              onStaffChange={reload}
              cardsOnly
            />
          </div>
        </div>
      </section>

      {/* 오른쪽 — 작업 로그와 진행 상황 */}
      <aside
        className="hidden h-full w-[21rem] shrink-0 flex-col border-l border-line
          bg-[color:var(--panel)] backdrop-blur-xl lg:flex"
        data-enter
      >
        <div className="flex items-center justify-between px-3 py-3">
          <span className="flex min-w-0 items-center gap-1.5 text-[13px]
            font-semibold tracking-tight">
            {t("office.log")}
            {/* 단계는 사무실 그림 안에만 있었다. 로그를 읽는 동안에는
                그림이 위로 밀려 안 보이는데, 정작 "지금 어디쯤인가"가
                제일 궁금한 순간이 그때다. */}
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

        <div className="min-h-0 flex-1 overflow-y-auto border-t border-line">
          {stream.events.length === 0 ? (
            <>
              <p className="px-4 py-6 text-center text-xs text-dim">
                {t("office.logEmpty")}
              </p>
              {/* 실행 전에는 이 칸이 통째로 비어 있었다. 지난 결과로
                  채운다 — 왼쪽 레일이 "무엇을 시켰나"를 보여주므로
                  여기는 "어떻게 끝났나"만 보여준다. */}
              <RecentResults />
            </>
          ) : (
            <ChatLog
              events={stream.events}
              roster={stream.roster}
              connected={stream.connected}
              polling={stream.polling}
              className="h-full"
            />
          )}
        </div>

        {/* 실행이 없으면 이 칸은 "—" 두 줄이다. 아무것도 알려주지 않으면서
            자리를 먹고, 그 위의 지난 결과까지 밀어낸다. */}
        {(slug || stream.events.length > 0) && (
        <div className="shrink-0 space-y-3 border-t border-line p-3">
          <ScorePanel
            score={folded.score}
            detail={folded.scoreDetail}
            cost={folded.totals?.cost}
            round={folded.round}
          />
          {(folded.tasks?.length ?? 0) > 0 && <TaskBoard tasks={folded.tasks} />}
          {slug && (folded.files?.length ?? 0) > 0 && (
            <Button
              className="w-full"
              onClick={() => router.push(`/projects/${slug}`)}
            >
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
