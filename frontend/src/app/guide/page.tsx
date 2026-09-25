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
 * ## 말은 사무실과 같아야 한다
 *
 * 역할 이름 · 직원 상태 · 승인 지점 · 결정 네 가지 · 지시창 문구는 **새로
 * 쓰지 않고 사무실이 쓰는 번역 키를 그대로** 쓴다. 설명이 "모든 결과 승인"
 * 이라고 하는데 버튼이 "결과 승인"이면, 읽은 사람은 둘이 같은 것인지부터
 * 의심한다. 사무실 문구를 바꾸면 여기도 따라 바뀐다.
 *
 * ## 움직임 — 손에 대답한다 (DAY 26)
 *
 * - **스크롤** (motion.dev): 맨 위 진행 막대가 읽은 만큼 차고, 카드 묶음이
 *   스크롤하는 **속도만큼** 살짝 기울었다가 스프링으로 돌아온다. 멈추면 반듯하다.
 * - **등장** (anime.js): 제목 낱말이 하나씩 튀어 오르고, 아래 절들은 그 자리에
 *   왔을 때 차례로 올라온다.
 * - **끌기** (motion.dev + anime.js): 카드·낱말·상태 칩을 끌 수 있다. 끄는
 *   방향으로 기울고, 옆 카드는 물러서고, 놓으면 튕겨 돌아가며 그 자리에서
 *   점이 튄다(`components/Fling.tsx`).
 *
 * 움직임을 줄인 사람에게는 전부 멈춘다 — 막대만 남는다(정보이기 때문이다).
 * 터치 화면에서는 끌기를 끈다(카드를 누르면 페이지가 스크롤돼야 한다).
 *
 * ## 과장하지 않는다
 *
 * 랜딩과 같은 원칙이다. 할 수 있는 것만 쓰고, 못 하는 것은 맨 아래
 * "지금 상태"에 그대로 적는다(`honest.*` — 랜딩과 같은 문장).
 */
import {
  motion, useReducedMotion, useScroll, useSpring, useTransform, useVelocity,
  type MotionValue,
} from "motion/react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { Fling, FlingArea, FlingWords, useCanFling } from "@/components/Fling";
import { PipelineFigure } from "@/components/PipelineFigure";
import { Icon, iconOfAgent } from "@/components/icons";
import { STATE_COLOR } from "@/components/office/OfficeFloor";
import { Filled, Panel } from "@/components/ui";
import { type Key, useLang } from "@/lib/i18n";
import { T, animate, revealFrom, stagger, utils, withScope } from "@/lib/motion";
import type { OfficeEmployee } from "@/lib/types";

/** 직원 다섯 — 이름이 아니라 **자리**다. `writes` 는 코드가 강제하는 쓰기
 *  구역(backend/app/agents/roles.py)과 같아야 한다. */
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

const SECTIONS = [
  ["flow", "guide.flow.title"],
  ["modes", "guide.modes.title"],
  ["staff", "staff.title"],
  ["gates", "guide.gates.title"],
  ["office", "guide.office.title"],
  ["money", "guide.money.title"],
  ["safety", "why.title"],
  ["honest", "honest.title"],
] as const;

export default function GuidePage() {
  const { t } = useLang();
  const scroller = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const canFling = useCanFling();

  // ── motion.dev: 스크롤에 묶인 두 가지 ─────────────────────────
  const { scrollY, scrollYProgress } = useScroll({ container: scroller });
  const progress = useSpring(scrollYProgress, { stiffness: 140, damping: 24, mass: 0.3 });
  // 빠르게 내리면 카드 묶음이 아래로, 올리면 위로 살짝 기운다. 멈추면 0.
  const velocity = useVelocity(scrollY);
  const tilt = useSpring(useTransform(velocity, [-2400, 0, 2400], [-3.5, 0, 3.5]),
                         { stiffness: 260, damping: 28, mass: 0.4 });

  // ── anime.js: 등장 ──────────────────────────────────────────
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    return withScope(el, () => {
      // 제목 낱말이 하나씩 — 저마다 조금 다른 각도에서 튀어 오른다.
      animate(el.querySelectorAll(".guide-word"), {
        opacity: [0, 1],
        translateY: [34, 0],
        rotate: () => [utils.random(-14, 14), 0],
        scale: [0.7, 1],
        duration: T.slow,
        delay: stagger(80, { start: 120 }),
        ease: "out(4)",
        onComplete: () => el.querySelectorAll(".guide-word")
          .forEach((w) => w.removeAttribute("data-reveal")),
      });
      revealFrom(el.querySelectorAll(".guide-head[data-reveal]"),
                 { y: 16, delay: stagger(120, { start: 420 }) });
      // 아래 절은 그 자리에 왔을 때 차례로.
      el.querySelectorAll<HTMLElement>("[data-reveal-group]").forEach((g) => {
        revealFrom(g.querySelectorAll("[data-reveal]"),
                   { y: 22, delay: stagger(T.step), scrollRoot: g });
      });
    });
  }, []);

  return (
    <div ref={scroller} className="h-full overflow-y-auto">
      {/* 읽은 만큼 차는 막대 — 이 페이지는 길다. */}
      <motion.div aria-hidden
        className="sticky top-0 z-30 h-0.5 origin-left"
        style={{ scaleX: progress, background: "var(--accent)" }} />
      <FlingArea>
      <article className="mx-auto max-w-3xl px-4 pb-16 pt-5">
        {/* ── 머리 ─────────────────────────────────────────────── */}
        <header className="pt-4 text-center">
          <p className="inline-flex items-center gap-2 rounded-full border border-line
            bg-panel px-3 py-1 text-[11px] text-muted">
            <span className="size-1.5 rounded-full" style={{ background: "var(--ok)" }} />
            {t("guide.badge")}
          </p>
          <h1 className="mt-4 text-2xl font-bold leading-tight tracking-tight sm:text-4xl">
            <FlingWords text={t("guide.title")} />
          </h1>
          <p className="guide-head mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-muted
            sm:text-base" data-reveal>
            <Filled text={t("guide.lead")} strong={t("guide.lead.strong")} />
          </p>
          {canFling && (
            <p className="guide-head mt-3 text-[11px] text-dim" data-reveal>
              {t("guide.dragHint")}
            </p>
          )}
        </header>

        {/* ── 차례 ─────────────────────────────────────────────── */}
        <nav aria-label={t("guide.toc")} className="mt-6 flex flex-wrap justify-center gap-1.5">
          {SECTIONS.map(([id, key]) => (
            <a key={id} href={`#${id}`}
              className="rounded-full border border-line bg-panel px-2.5 py-1 text-[11px]
                text-muted transition hover:border-accent hover:text-fg">
              {t(key)}
            </a>
          ))}
        </nav>

        {/* ── 흐름 ─────────────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="flow" title={t("guide.flow.title")} lead={t("guide.flow.lead")}>
          <div className="rounded-2xl border border-line bg-panel p-4 sm:p-6" data-reveal>
            <PipelineFigure />
          </div>
          <ol className="mt-4 grid gap-2 sm:grid-cols-2">
            {STEPS.map((n) => (
              <Fling key={n} as="li"
                className="flex gap-3 rounded-xl border border-line bg-panel p-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full
                  text-[11px] font-bold text-white grad-accent">{n}</span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">
                    {t(`guide.step.${n}` as Key)}
                  </span>
                  <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                    {t(`guide.step.${n}.body` as Key)}
                  </span>
                </span>
              </Fling>
            ))}
          </ol>
        </Section>

        {/* ── AUTO · MANUAL ────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="modes" title={t("guide.modes.title")}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Fling><Card title={t("office.auto")} icon="play">{t("guide.auto.body")}</Card></Fling>
            <Fling><Card title={t("office.manual")} icon="person">
              {t("guide.manual.body")}
            </Card></Fling>
          </div>
        </Section>

        {/* ── 직원 ─────────────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="staff" title={t("staff.title")} lead={t("staff.note")}>
          <ul className="grid gap-2 sm:grid-cols-2">
            {STAFF.map((e) => (
              <Fling key={e.id} as="li" color={`var(--${e.id})`}
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
              </Fling>
            ))}
          </ul>
          <p className="mt-3 text-xs leading-relaxed text-muted" data-reveal>
            {t("guide.teams")} {t("office.card.teamHint")}
          </p>
        </Section>

        {/* ── 승인 지점 ────────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="gates" title={t("guide.gates.title")} lead={t("guide.gates.lead")}>
          <ul className="grid gap-2 sm:grid-cols-2">
            {GATES.map(([name, hint]) => (
              <Fling key={name} as="li" color="var(--st-approval)"
                className="rounded-xl border border-line bg-panel p-3">
                <p className="text-sm font-semibold" style={{ color: "var(--st-approval)" }}>
                  ★ {t(name)}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-muted">{t(hint)}</p>
              </Fling>
            ))}
          </ul>
          <h3 className="mt-5 text-sm font-semibold" data-reveal>{t("guide.decide.title")}</h3>
          <dl className="mt-2 divide-y divide-line rounded-xl border border-line bg-panel"
            data-reveal>
            {DECISIONS.map((d) => (
              <div key={d} className="flex gap-3 px-3 py-2 text-xs">
                <dt className="w-20 shrink-0 font-semibold">{t(`approval.${d}` as Key)}</dt>
                <dd className="text-muted">{t(`guide.decide.${d}` as Key)}</dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* ── 사무실 ───────────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="office" title={t("guide.office.title")} lead={t("guide.office.lead")}>
          <ul className="space-y-1.5">
            {STATES.map((s) => (
              <Fling key={s} as="li" color={STATE_COLOR[s]}
                className="flex items-center gap-3 rounded-xl border border-line
                bg-panel px-3 py-2 text-xs">
                <span className="size-3 shrink-0 rounded-full border-[3px]" aria-hidden
                  style={{ borderColor: STATE_COLOR[s] }} />
                <span className="w-20 shrink-0 font-semibold" style={{ color: STATE_COLOR[s] }}>
                  {t(`office.state.${s}` as Key)}
                </span>
                <span className="text-muted">{t(`guide.state.${s}` as Key)}</span>
              </Fling>
            ))}
          </ul>
          <h3 className="mt-5 text-sm font-semibold" data-reveal>{t("guide.office.commands")}</h3>
          <p className="mt-1 text-[11px] text-dim" data-reveal>{t("cmd.hint")}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {COMMANDS.map((k) => (
              <Fling key={k} className="rounded-full border border-line bg-panel px-2.5 py-1
                text-[11px]">
                {t(k)}
              </Fling>
            ))}
          </div>
        </Section>

        {/* ── 돈 ───────────────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="money" title={t("guide.money.title")}>
          <ul className="space-y-2 text-sm leading-relaxed text-muted">
            {(["credits", "before", "plans", "byok"] as const).map((k) => (
              <li key={k} className="flex gap-2" data-reveal>
                <span className="mt-2 size-1.5 shrink-0 rounded-full"
                  style={{ background: "var(--accent)" }} aria-hidden />
                <span>{t(`guide.money.${k}` as Key)}</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* ── 안전장치 ─────────────────────────────────────────── */}
        <Section tilt={reduced ? undefined : tilt} id="safety" title={t("why.title")}>
          <div className="grid gap-3 sm:grid-cols-2">
            {PROOFS.map((k) => (
              <Fling key={k} className="rounded-xl border border-line bg-panel p-4">
                <p className="text-sm font-semibold">{t(`why.${k}` as Key)}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">
                  {t(`why.${k}.body` as Key)}
                </p>
              </Fling>
            ))}
          </div>
        </Section>

        {/* ── 지금 상태 ────────────────────────────────────────── */}
        <section id="honest" className="mt-12 scroll-mt-4" data-reveal-group>
          <Panel title={t("honest.title")} data-reveal>
            <ul className="space-y-1.5 text-xs leading-relaxed text-muted">
              <li>· {t("honest.files")}</li>
              <li>
                · <Filled text={t("honest.injection")} strong={t("honest.injection.strong")} />
              </li>
              <li style={{ color: "var(--warn)" }}>· {t("honest.noRealRun")}</li>
              <li style={{ color: "var(--warn)" }}>· {t("honest.noBilling")}</li>
            </ul>
          </Panel>
        </section>

        {/* ── 시작 ─────────────────────────────────────────────── */}
        <section className="mt-12 text-center">
          <h2 className="text-lg font-semibold">{t("guide.cta.title")}</h2>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            <CtaLink href="/" primary>{t("guide.cta.office")}</CtaLink>
            <CtaLink href="/pricing">{t("guide.cta.pricing")}</CtaLink>
            <CtaLink href="/settings">{t("guide.cta.keys")}</CtaLink>
          </div>
        </section>
      </article>
      </FlingArea>
    </div>
  );
}

function Section({ id, title, lead, children, tilt }: {
  id: string; title: string; lead?: string; children: React.ReactNode;
  /** 스크롤 속도만큼의 기울기(도). 움직임을 줄였으면 없다. */
  tilt?: MotionValue<number>;
}) {
  return (
    <section id={id} className="mt-12 scroll-mt-4" aria-labelledby={`${id}-title`}
      data-reveal-group>
      <h2 id={`${id}-title`} className="text-lg font-semibold tracking-tight" data-reveal>
        {title}
      </h2>
      {lead && <p className="mt-1 text-sm leading-relaxed text-muted" data-reveal>{lead}</p>}
      <motion.div className="mt-4" style={tilt ? { skewY: tilt } : undefined}>
        {children}
      </motion.div>
    </section>
  );
}

function Card({ title, icon, children }: {
  title: string; icon: "play" | "person"; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <Icon name={icon} size={16} className="text-accent" />
        {title}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">{children}</p>
    </div>
  );
}

function CtaLink({ href, primary = false, children }: {
  href: string; primary?: boolean; children: React.ReactNode;
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
