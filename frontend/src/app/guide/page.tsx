"use client";

/**
 * 설명 탭 — 이 제품이 무엇을 어떻게 하나 (DAY 26).
 *
 * ## 왜 따로 있나
 *
 * 제품을 설명하는 화면은 랜딩뿐이었다. 그런데 랜딩은 **로그인 전에만**
 * 보이고(SaaS), 로컬에서는 아예 안 보인다. 사무실은 일하는 곳이지 설명하는
 * 곳이 아니다 — 처음 들어온 사람은 "테스트를 먼저 쓴다"거나 "승인 지점에서
 * 멈춘다"는 것을 화면에서 짐작해야 했다.
 *
 * ## 한 화면 — 스크롤하지 않는다
 *
 * 긴 문서를 내려 읽는 대신, **한 화면 안에서 장(章)을 넘긴다.** 화면은 움직이지
 * 않고 내용만 바뀐다. 한 장이 한 화면에 들어가도록 장마다 내용을 나눴다.
 *
 * - 넘기는 법: 위의 탭 · 아래 이전/다음 · ←/→ 키 · 옆으로 끌기(손가락도 된다) ·
 *   마우스 휠. 지금 장은 주소(#staff 등)에 남아 링크로 보낼 수 있다.
 * - **motion.dev** 가 장 사이를 맡는다: 끄는 대로 따라오며 기울고, 넘기면 옆에서
 *   살짝 돌아 들어온다(3D 슬라이드). 탭 밑줄이 스프링으로 따라간다.
 * - **anime.js** 가 장 안을 맡는다: 새 장이 서면 그 안의 조각이 차례로 올라온다.
 *   흐름 그림은 제 타임라인대로 순서를 그린다.
 * - 움직임을 줄인 사람에게는 넘기기만 되고 아무것도 날아다니지 않는다.
 *
 * ## 말은 사무실과 같아야 한다
 *
 * 역할 이름 · 직원 상태 · 승인 지점 · 결정 네 가지 · 지시창 문구는 **새로
 * 쓰지 않고 사무실이 쓰는 번역 키를 그대로** 쓴다. 설명이 "모든 결과 승인"
 * 이라고 하는데 버튼이 "결과 승인"이면, 읽은 사람은 둘이 같은 것인지부터
 * 의심한다. 사무실 문구를 바꾸면 여기도 따라 바뀐다.
 *
 * ## 과장하지 않는다
 *
 * 랜딩과 같은 원칙이다. 할 수 있는 것만 쓰고, 못 하는 것은 마지막 장
 * "지금 상태"에 그대로 적는다(`honest.*` — 랜딩과 같은 문장).
 */
import {
  AnimatePresence, motion, useMotionValue, useReducedMotion, useTransform,
  type PanInfo,
} from "motion/react";
import Link from "next/link";
import {
  useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode,
  type WheelEvent,
} from "react";

import { PipelineFigure } from "@/components/PipelineFigure";
import { Icon, iconOfAgent } from "@/components/icons";
import { STATE_COLOR } from "@/components/office/OfficeFloor";
import { Filled } from "@/components/ui";
import { type Key, useLang } from "@/lib/i18n";
import { T, animate, stagger, utils, withScope } from "@/lib/motion";
import type { OfficeEmployee } from "@/lib/types";

/** 직원 다섯 — 이름이 아니라 **자리**다. `writes` 는 코드가 강제하는 쓰기
 *  구역(backend/app/agents/roles.py)과 같아야 한다(test_repo_files 가 본다). */
const STAFF = [
  { id: "strategist", who: "Claude", writes: null },
  { id: "analyst", who: "Gemini", writes: "tests/" },
  { id: "developer", who: "Claude", writes: "src/" },
  { id: "writer", who: "GPT", writes: "docs/" },
  { id: "designer", who: "Gemini", writes: "design/" },
] as const;

const STEPS = [1, 2, 3, 4, 5, 6] as const;

const GATES = [
  ["gate.plan", "gate.planHint"],
  ["gate.task", "gate.taskHint"],
  ["gate.taskDev", "gate.taskDevHint"],
  ["gate.confidence", "gate.confidenceHint"],
] as const;

const DECISIONS = ["approve", "reject", "hold", "discard"] as const;

const STATES: OfficeEmployee["state"][] = ["done", "working", "approval", "integration", "idle"];

const COMMANDS = ["cmd.status", "cmd.why", "cmd.meeting", "cmd.brief", "cmd.focus",
                  "cmd.approve"] as const;

const PROOFS = ["order", "tests", "cross", "cost"] as const;

/** 장 순서. id 는 주소(#id)에 남는다. */
const TABS = ["intro", "flow", "staff", "gates", "office", "money", "safety", "honest"] as const;
type Tab = (typeof TABS)[number];

// 넘기기로 칠 끌기 — 이만큼 끌었거나, 이만큼 빠르게 튕겼으면.
const SWIPE_PX = 90;
const SWIPE_V = 450;
// 휠 한 번에 한 장. 트랙패드는 한 번 쓸어도 이벤트가 수십 개 온다.
const WHEEL_LOCK_MS = 650;

/** motion.dev — 장이 옆에서 살짝 돌아 들어오고, 반대쪽으로 돌아 나간다. */
const slide = {
  enter: (dir: number) => ({ x: dir > 0 ? "55%" : "-55%", opacity: 0, scale: 0.92,
                             rotateY: dir > 0 ? -18 : 18 }),
  center: { x: 0, opacity: 1, scale: 1, rotateY: 0,
            transition: { type: "spring" as const, stiffness: 240, damping: 28 } },
  exit: (dir: number) => ({ x: dir > 0 ? "-40%" : "40%", opacity: 0, scale: 0.92,
                            rotateY: dir > 0 ? 18 : -18,
                            transition: { duration: 0.28, ease: "easeIn" as const } }),
};

function tabFromHash(): Tab {
  if (typeof window === "undefined") return "intro";
  const h = window.location.hash.replace("#", "");
  return (TABS as readonly string[]).includes(h) ? (h as Tab) : "intro";
}

export default function GuidePage() {
  const { t } = useLang();
  const reduced = useReducedMotion();
  const [[tab, dir], setTab] = useState<[Tab, number]>(["intro", 0]);
  const index = TABS.indexOf(tab);
  const wheelLock = useRef(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // 주소의 #장 에서 시작한다 — 링크로 보낸 장이 바로 열리게. 주소는 렌더 밖의
  // 값이라 하이드레이션 뒤에 한 번 읽는다(첫 그림은 서버와 같게 "소개").
  useEffect(() => {
    const first = tabFromHash();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (first !== "intro") setTab([first, 1]);
  }, []);

  const go = useCallback((to: number, focus = false) => {
    const next = Math.max(0, Math.min(TABS.length - 1, to));
    setTab((prev) => {
      const from = TABS.indexOf(prev[0]);
      return next === from ? prev : [TABS[next], next > from ? 1 : -1];
    });
    if (focus) tabRefs.current[next]?.focus();
  }, []);

  // 지금 장을 주소에 남긴다 — **렌더 밖에서.** 상태를 고치는 함수 안에서
  // 주소를 바꾸면 Next 라우터가 렌더 도중에 갱신돼 경고가 난다(DAY 26 에 겪음).
  useEffect(() => {
    if (tab === "intro" && !window.location.hash) return;
    if (window.location.hash !== `#${tab}`) {
      window.history.replaceState(null, "", `#${tab}`);
    }
  }, [tab]);

  // ←/→ 로 넘긴다. 입력칸에 쓰는 중이면 건드리지 않는다.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (el?.getAttribute("role") === "tab") return;       // 탭 목록이 따로 처리한다
      if (e.key === "ArrowRight" || e.key === "PageDown") go(index + 1);
      else if (e.key === "ArrowLeft" || e.key === "PageUp") go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  // 탭 목록의 키보드 — ARIA 탭 패턴(←/→ · Home/End 로 옮기고 바로 연다).
  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const map: Record<string, number> = {
      ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: TABS.length - 1,
    };
    if (e.key in map) {
      e.preventDefault();
      go(map[e.key], true);
    }
  };

  const onWheel = (e: WheelEvent<HTMLDivElement>) => {
    // 좁은 화면에서 장이 넘치면 휠은 그 장을 내린다 — 끝에 닿았을 때만 넘긴다.
    const panel = (e.currentTarget.querySelector("[role=tabpanel]") as HTMLElement | null);
    if (panel && panel.scrollHeight > panel.clientHeight + 2) {
      const atTop = panel.scrollTop <= 0;
      const atEnd = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 2;
      if ((e.deltaY > 0 && !atEnd) || (e.deltaY < 0 && !atTop)) return;
    }
    const d = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    if (Math.abs(d) < 30 || Date.now() < wheelLock.current) return;
    wheelLock.current = Date.now() + WHEEL_LOCK_MS;
    go(index + (d > 0 ? 1 : -1));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ── 장 목록 ─────────────────────────────────────────────── */}
      <div role="tablist" aria-label={t("guide.toc")} onKeyDown={onTabKey}
        className="flex shrink-0 justify-start gap-1 overflow-x-auto border-b border-line
          px-3 py-2 [scrollbar-width:none] sm:justify-center">
        {TABS.map((id, i) => {
          const on = id === tab;
          return (
            <button key={id} type="button" role="tab" id={`tab-${id}`}
              ref={(el) => { tabRefs.current[i] = el; }}
              aria-selected={on} aria-controls={`panel-${id}`} tabIndex={on ? 0 : -1}
              onClick={() => go(i)}
              className={`relative shrink-0 whitespace-nowrap rounded-full px-3 py-1.5
                text-[12px] font-medium transition-colors
                ${on ? "text-fg" : "text-muted hover:text-fg"}`}>
              {on && (
                <motion.span layoutId="guide-tab-pill" aria-hidden
                  className="absolute inset-0 rounded-full border border-line bg-panel2"
                  transition={{ type: "spring", stiffness: 420, damping: 32 }} />
              )}
              <span className="relative">{t(`guide.tab.${id}` as Key)}</span>
            </button>
          );
        })}
      </div>

      {/* ── 무대 — 여기만 바뀐다 ──────────────────────────────────── */}
      <div className="relative min-h-0 flex-1 overflow-hidden" onWheel={onWheel}
        style={{ perspective: 1400 }}>
        <AnimatePresence initial={false} custom={dir} mode="popLayout">
          <Slide key={tab} tab={tab} dir={dir} reduced={!!reduced}
            onSwipe={(d) => go(index + d)}>
            <Chapter tab={tab} go={go} />
          </Slide>
        </AnimatePresence>
      </div>

      {/* ── 아래 — 이전 · 점 · 다음 ─────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-t border-line
        px-4 py-2.5">
        <NavButton onClick={() => go(index - 1)} disabled={index === 0} dir="prev">
          {t("guide.prev")}
        </NavButton>
        <div className="flex min-w-0 items-center gap-3">
          <div className="hidden items-center gap-1.5 sm:flex" aria-hidden>
            {TABS.map((id, i) => (
              <motion.span key={id} className="h-1.5 rounded-full"
                animate={{ width: i === index ? 22 : 6,
                           backgroundColor: i === index ? "var(--accent)" : "var(--line-strong)" }}
                transition={{ type: "spring", stiffness: 380, damping: 30 }} />
            ))}
          </div>
          <span className="text-[11px] tabular-nums text-dim" aria-live="polite">
            {index + 1} / {TABS.length}
          </span>
          <span className="hidden text-[11px] text-dim lg:inline">{t("guide.navHint")}</span>
        </div>
        <NavButton onClick={() => go(index + 1)} disabled={index === TABS.length - 1} dir="next">
          {t("guide.next")}
        </NavButton>
      </div>
    </div>
  );
}

/**
 * 장 하나. 옆으로 끌면 따라오며 기울고(motion.dev), 충분히 끌면 넘어간다.
 * 서면 그 안의 조각(`data-item`)이 차례로 올라온다(anime.js).
 */
function Slide({ tab, dir, reduced, onSwipe, children }: {
  tab: Tab; dir: number; reduced: boolean; onSwipe: (d: number) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const x = useMotionValue(0);
  const tilt = useTransform(x, [-320, 0, 320], [5, 0, -5]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return withScope(el, () => {
      const items = el.querySelectorAll("[data-item]");
      animate(items, {
        opacity: [0, 1],
        translateY: [26, 0],
        scale: [0.94, 1],
        rotate: () => [utils.random(-3, 3), 0],
        duration: T.slow,
        delay: stagger(55, { start: 140 }),
        ease: "out(4)",
        onComplete: () => items.forEach((i) => i.removeAttribute("data-reveal")),
      });
    });
  }, []);

  return (
    <motion.section ref={ref} role="tabpanel" id={`panel-${tab}`}
      aria-labelledby={`tab-${tab}`} tabIndex={-1}
      custom={dir} variants={reduced ? undefined : slide}
      initial={reduced ? false : "enter"} animate="center" exit={reduced ? undefined : "exit"}
      drag="x" dragConstraints={{ left: 0, right: 0 }} dragElastic={0.35}
      dragMomentum={false}
      onDragEnd={(_: unknown, info: PanInfo) => {
        if (info.offset.x < -SWIPE_PX || info.velocity.x < -SWIPE_V) onSwipe(1);
        else if (info.offset.x > SWIPE_PX || info.velocity.x > SWIPE_V) onSwipe(-1);
      }}
      style={{ x, rotateZ: reduced ? 0 : tilt }}
      className="absolute inset-0 cursor-grab overflow-y-auto px-4 py-6 outline-none
        active:cursor-grabbing sm:px-8">
      <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center">
        {children}
      </div>
    </motion.section>
  );
}

function NavButton({ onClick, disabled, dir, children }: {
  onClick: () => void; disabled: boolean; dir: "prev" | "next"; children: ReactNode;
}) {
  return (
    <motion.button type="button" onClick={onClick} disabled={disabled}
      whileHover={disabled ? undefined : { scale: 1.04 }}
      whileTap={disabled ? undefined : { scale: 0.96 }}
      className="flex shrink-0 items-center gap-1 rounded-xl border border-line bg-panel px-3
        py-1.5 text-xs font-medium disabled:opacity-40">
      {dir === "prev" && <span aria-hidden>←</span>}
      {children}
      {dir === "next" && <span aria-hidden>→</span>}
    </motion.button>
  );
}

// ── 장마다의 내용 ─────────────────────────────────────────────────────
// `data-item` + `data-reveal`: 장이 서면 차례로 올라오는 조각. 움직임을 줄였거나
// 애니메이션이 못 돌면 lib/motion 의 안전망이 그대로 드러낸다.

function Chapter({ tab, go }: { tab: Tab; go: (i: number) => void }) {
  const { t } = useLang();
  switch (tab) {
    case "intro":
      return (
        <div className="text-center">
          <p data-item data-reveal className="inline-flex items-center gap-2 rounded-full border
            border-line bg-panel px-3 py-1 text-[11px] text-muted">
            <span className="size-1.5 rounded-full" style={{ background: "var(--ok)" }} />
            {t("guide.badge")}
          </p>
          <h1 data-item data-reveal
            className="mt-4 text-3xl font-bold leading-tight tracking-tight sm:text-5xl">
            {t("guide.title")}
          </h1>
          <p data-item data-reveal
            className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">
            <Filled text={t("guide.lead")} strong={t("guide.lead.strong")} />
          </p>
          <p data-item data-reveal className="mt-8 text-sm font-semibold">
            {t("guide.modes.title")}
          </p>
          <div className="mx-auto mt-3 grid max-w-3xl gap-3 text-left sm:grid-cols-2">
            <Card title={t("office.auto")} icon="play">{t("guide.auto.body")}</Card>
            <Card title={t("office.manual")} icon="person">{t("guide.manual.body")}</Card>
          </div>
          <motion.button data-item data-reveal type="button" onClick={() => go(1)}
            whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.97 }}
            className="mt-8 rounded-xl px-4 py-2 text-sm font-medium text-white grad-accent
              shadow-[0_4px_14px_rgba(109,141,255,0.35)]">
            {t("guide.tab.flow")} →
          </motion.button>
        </div>
      );

    case "flow":
      return (
        <>
          <Heading title={t("guide.flow.title")} lead={t("guide.flow.lead")} />
          <div className="grid items-center gap-4 lg:grid-cols-[1.15fr_1fr]">
            <div data-item data-reveal className="rounded-2xl border border-line bg-panel p-3">
              <PipelineFigure />
            </div>
            <ol className="grid gap-2 sm:grid-cols-2">
              {STEPS.map((n) => (
                <li key={n} data-item data-reveal
                  className="flex gap-2.5 rounded-xl border border-line bg-panel p-2.5">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full
                    text-[10px] font-bold text-white grad-accent">{n}</span>
                  <span className="min-w-0">
                    <span className="block text-[13px] font-semibold">
                      {t(`guide.step.${n}` as Key)}
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                      {t(`guide.step.${n}.body` as Key)}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </>
      );

    case "staff":
      return (
        <>
          <Heading title={t("staff.title")} lead={t("staff.note")} />
          <ul className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {STAFF.map((e) => (
              <li key={e.id} data-item data-reveal
                className="rounded-xl border border-line bg-panel p-3">
                <div className="flex items-center gap-2">
                  <span className="grid size-8 place-items-center rounded-lg" aria-hidden
                    style={{ background: `color-mix(in srgb, var(--${e.id}) 16%, transparent)`,
                             color: `var(--${e.id})` }}>
                    <Icon name={iconOfAgent(e.id)} size={18} />
                  </span>
                  <span className="text-sm font-semibold">{t(`role.${e.id}` as Key)}</span>
                  <span className="ml-auto text-[11px] text-dim">{e.who}</span>
                </div>
                <p className="mt-2 text-xs text-muted">{t(`staff.${e.id}` as Key)}</p>
                <p className="mt-1.5 text-[11px] text-dim">
                  {t("guide.writes")}:{" "}
                  {e.writes
                    ? <code className="rounded bg-panel2 px-1 py-0.5 text-fg">{e.writes}</code>
                    : t("guide.writes.none")}
                </p>
              </li>
            ))}
            <li data-item data-reveal
              className="flex items-center rounded-xl border border-dashed border-line p-3
                text-xs leading-relaxed text-muted">
              {t("guide.teams")} {t("office.card.teamHint")}
            </li>
          </ul>
        </>
      );

    case "gates":
      return (
        <>
          <Heading title={t("guide.gates.title")} lead={t("guide.gates.lead")} />
          <div className="grid gap-4 lg:grid-cols-2">
            <ul className="grid gap-2 sm:grid-cols-2">
              {GATES.map(([name, hint]) => (
                <li key={name} data-item data-reveal
                  className="rounded-xl border border-line bg-panel p-3">
                  <p className="text-sm font-semibold" style={{ color: "var(--st-approval)" }}>
                    ★ {t(name)}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{t(hint)}</p>
                </li>
              ))}
            </ul>
            <div data-item data-reveal>
              <h3 className="text-sm font-semibold">{t("guide.decide.title")}</h3>
              <dl className="mt-2 divide-y divide-line rounded-xl border border-line bg-panel">
                {DECISIONS.map((d) => (
                  <div key={d} className="flex gap-3 px-3 py-2.5 text-xs">
                    <dt className="w-20 shrink-0 font-semibold">{t(`approval.${d}` as Key)}</dt>
                    <dd className="text-muted">{t(`guide.decide.${d}` as Key)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </>
      );

    case "office":
      return (
        <>
          <Heading title={t("guide.office.title")} lead={t("guide.office.lead")} />
          <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
            <ul className="space-y-1.5">
              {STATES.map((s) => (
                <li key={s} data-item data-reveal
                  className="flex items-center gap-3 rounded-xl border border-line bg-panel
                    px-3 py-2.5 text-xs">
                  <span className="size-3 shrink-0 rounded-full border-[3px]" aria-hidden
                    style={{ borderColor: STATE_COLOR[s] }} />
                  <span className="w-20 shrink-0 font-semibold" style={{ color: STATE_COLOR[s] }}>
                    {t(`office.state.${s}` as Key)}
                  </span>
                  <span className="text-muted">{t(`guide.state.${s}` as Key)}</span>
                </li>
              ))}
            </ul>
            <div data-item data-reveal className="rounded-xl border border-line bg-panel p-4">
              <h3 className="text-sm font-semibold">{t("guide.office.commands")}</h3>
              <p className="mt-1 text-[11px] text-dim">{t("cmd.hint")}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {COMMANDS.map((k) => (
                  <span key={k} className="rounded-full border border-line bg-panel2 px-2.5 py-1
                    text-[11px]">
                    {t(k)}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </>
      );

    case "money":
      return (
        <>
          <Heading title={t("guide.money.title")} />
          <ul className="grid gap-2.5 sm:grid-cols-2">
            {(["credits", "before", "plans", "byok"] as const).map((k, i) => (
              <li key={k} data-item data-reveal
                className="flex gap-3 rounded-xl border border-line bg-panel p-4 text-sm
                  leading-relaxed text-muted">
                <span className="grid size-6 shrink-0 place-items-center rounded-full text-[11px]
                  font-bold" style={{ background: "color-mix(in srgb, var(--accent) 18%, transparent)",
                                      color: "var(--accent)" }}>{i + 1}</span>
                <span>{t(`guide.money.${k}` as Key)}</span>
              </li>
            ))}
          </ul>
        </>
      );

    case "safety":
      return (
        <>
          <Heading title={t("why.title")} />
          <div className="grid gap-3 sm:grid-cols-2">
            {PROOFS.map((k) => (
              <div key={k} data-item data-reveal className="rounded-xl border border-line bg-panel p-4">
                <p className="text-sm font-semibold">{t(`why.${k}` as Key)}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">
                  {t(`why.${k}.body` as Key)}
                </p>
              </div>
            ))}
          </div>
        </>
      );

    case "honest":
      return (
        <>
          <Heading title={t("honest.title")} />
          <ul data-item data-reveal className="space-y-2 rounded-2xl border border-line bg-panel
            p-5 text-sm leading-relaxed text-muted">
            <li>· {t("honest.files")}</li>
            <li>· <Filled text={t("honest.injection")} strong={t("honest.injection.strong")} /></li>
            <li style={{ color: "var(--warn)" }}>· {t("honest.noRealRun")}</li>
            <li style={{ color: "var(--warn)" }}>· {t("honest.noBilling")}</li>
          </ul>
          <div data-item data-reveal className="mt-8 text-center">
            <h2 className="text-lg font-semibold">{t("guide.cta.title")}</h2>
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              <CtaLink href="/" primary>{t("guide.cta.office")}</CtaLink>
              <CtaLink href="/pricing">{t("guide.cta.pricing")}</CtaLink>
              <CtaLink href="/settings">{t("guide.cta.keys")}</CtaLink>
            </div>
          </div>
        </>
      );
  }
}

function Heading({ title, lead }: { title: string; lead?: string }) {
  return (
    <header className="mb-5">
      <h2 data-item data-reveal className="text-xl font-semibold tracking-tight sm:text-2xl">
        {title}
      </h2>
      {lead && (
        <p data-item data-reveal className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">
          {lead}
        </p>
      )}
    </header>
  );
}

function Card({ title, icon, children }: {
  title: string; icon: "play" | "person"; children: ReactNode;
}) {
  return (
    <div data-item data-reveal className="rounded-xl border border-line bg-panel p-4">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <Icon name={icon} size={16} className="text-accent" />
        {title}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">{children}</p>
    </div>
  );
}

function CtaLink({ href, primary = false, children }: {
  href: string; primary?: boolean; children: ReactNode;
}) {
  return (
    <Link href={href}
      className={`rounded-xl px-4 py-2 text-sm font-medium transition ${primary
        ? "grad-accent text-white shadow-[0_4px_14px_rgba(109,141,255,0.35)]"
        : "border border-line bg-panel text-fg hover:border-accent"}`}>
      {children}
    </Link>
  );
}
