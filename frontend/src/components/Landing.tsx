"use client";

/**
 * 공개 랜딩 — 도메인에 처음 온 사람이 보는 화면 (DAY 18 · DAY 20 개편).
 *
 * ## 이 화면이 유일한 체험 창구다
 *
 * DAY 19 에 무료 요금제를 없앴다. 이제 계정을 만들어도 결제 전에는
 * 아무것도 돌려볼 수 없다. 그 말은 **로그인 이전의 이 화면이 제품을
 * 보여줄 마지막 자리**라는 뜻이다. 여기서 이해시키지 못하면 결제 버튼은
 * 눌리지 않는다.
 *
 * ## 그래서 움직인다. 다만 장식으로 움직이지는 않는다
 *
 * 히어로의 도형은 코드에 실제로 있는 순서를 그린다 — 테스트가 먼저
 * 쓰이고, 다른 회사 모델이 판정하고, 반려되면 되돌아간다. 움직임이
 * 없으면 이 순서는 글로 읽어야 하고, 글로 읽는 사람은 다섯 줄째에서
 * 떠난다.
 *
 * 나머지 움직임은 **등장**뿐이다. 계속 흔들리는 요소를 두지 않는다 —
 * 읽는 중에 움직이는 것은 읽기를 방해한다.
 *
 * ## 과장하지 않는다
 *
 * 이 제품은 아직 실제 모델로 완주해본 적이 없다(STATUS.md). "AI 가
 * 알아서 다 해줍니다"는 우리가 확인하지 않은 주장이다. 할 수 있는 것만
 * 쓰고, 못 하는 것은 아래 '지금 상태' 에 그대로 적는다. 랜딩에서 부풀린
 * 만큼 첫 결제 다음 날 환불로 돌아온다.
 */
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import GuidePage from "@/app/guide/page";
import { StackCtx } from "@/lib/stack";
import { PipelineFigure } from "./PipelineFigure";
import { Icon, iconOfAgent } from "./icons";
import { Button, Filled, Panel } from "./ui";
import { api } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { T, animate, onScroll, revealFrom, scrollParent, stagger, withScope }
  from "@/lib/motion";
import type { PlanRow } from "@/lib/types";

/** 직원 목록. 이름·설명은 표에서 온다 — 사람 이름이 아니라 **직책**이라
 *  번역된다. 모델 회사(Claude·Gemini·GPT)는 고유명사라 그대로 둔다. */
const EMPLOYEES = [
  { id: "strategist", who: "Claude" },
  { id: "developer", who: "Claude" },
  { id: "analyst", who: "Gemini" },
  { id: "writer", who: "GPT" },
  { id: "designer", who: "Gemini" },
] as const;

const PROOFS = ["order", "tests", "cross", "cost"] as const;

export function Landing({ children }: { children: ReactNode }) {
  const { t } = useLang();
  const root = useRef<HTMLDivElement>(null);
  const [plans, setPlans] = useState<Record<string, PlanRow> | null>(null);

  // 가격은 서버가 가진 것 하나뿐이다. 랜딩에 숫자를 적어두면 요금제를
  // 바꾼 날 **여기만 옛날 가격**이 남는다. 못 불러오면 요금제 칸을
  // 통째로 비운다 — 틀린 가격보다 없는 가격이 낫다.
  useEffect(() => {
    let alive = true;
    api
      .plans()
      .then((r) => alive && setPlans(r.plans))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    return withScope(el, () => {
      // 히어로는 스크롤을 기다리지 않는다. 이미 보이는 것이다.
      revealFrom(".hero-line", { y: 18, delay: stagger(90) });
      revealFrom(".hero-figure", { y: 26, delay: 320 });
      revealFrom(".hero-cta", { y: 12, delay: 480 });

      // 아래 구역은 그 자리에 왔을 때 나타난다. 한꺼번에 다 움직이면
      // 어디를 봐야 하는지가 사라진다.
      el.querySelectorAll<HTMLElement>("[data-reveal-group]").forEach((g) => {
        revealFrom(g.querySelectorAll("[data-reveal]"), {
          delay: stagger(T.step),
          scrollRoot: g,
        });
      });

      // 스크롤에 **묶인** 움직임 두 가지. 등장과 달리 이건 사용자의 손에
      // 달려 있다 — 스크롤을 멈추면 멈추고, 되돌리면 되돌아간다.
      //
      // 1) 맨 위 진행 막대. 이 화면은 길다. 얼마나 남았는지 모르면
      //    중간에서 "끝이 없나" 싶어 닫는다.
      const bar = el.querySelector(".scroll-bar");
      if (bar) {
        animate(bar, {
          scaleX: [0, 1],
          ease: "linear",
          autoplay: onScroll({ target: el, sync: true, container: scrollParent(el),
                              enter: "top top", leave: "bottom bottom" }),
        });
      }

      // 2) 히어로 도형이 스크롤을 따라 아주 조금 뜬다. 크게 주면 멀미가
      //    나므로 18px 안쪽으로만 — 깊이를 암시하는 정도면 충분하다.
      const figure = el.querySelector(".hero-figure");
      if (figure) {
        animate(figure, {
          translateY: [0, -18],
          ease: "linear",
          autoplay: onScroll({ target: figure, sync: 0.35,
                              container: scrollParent(figure),
                              enter: "top top", leave: "bottom top" }),
        });
      }
    });
  }, [plans]);

  return (
    <div ref={root} className="relative mx-auto max-w-5xl px-4 py-10">
      {/* 읽은 만큼 차는 막대. 헤더 바로 아래에 붙인다. */}
      <div
        className="scroll-bar pointer-events-none fixed inset-x-0 top-0 z-30 h-0.5
          origin-left"
        style={{ background: "var(--accent)", transform: "scaleX(0)" }}
        aria-hidden
      />
      {/* ── 히어로 ─────────────────────────────────────────── */}
      <section className="text-center">
        <p
          className="hero-line inline-flex items-center gap-2 rounded-full border
            border-line bg-panel px-3 py-1 text-[11px] text-muted"
          data-reveal
        >
          <span className="size-1.5 rounded-full" style={{ background: "var(--ok)" }} />
          {t("hero.badge")}
        </p>
        <h1
          className="hero-line mt-4 text-3xl font-bold leading-tight tracking-tight sm:text-5xl"
          data-reveal
        >
          {t("hero.title")}
        </h1>
        <p
          className="hero-line mx-auto mt-4 max-w-2xl text-sm text-muted sm:text-base"
          data-reveal
        >
          <Filled
            text={t("hero.body")}
            strong={t("hero.body.strong")}
          />
        </p>
      </section>

      {/* ── 흐름 도형 ──────────────────────────────────────── */}
      <section className="hero-figure mt-8" data-reveal>
        <div className="rounded-2xl border border-line bg-panel p-4 sm:p-6">
          <PipelineFigure />
          <p className="mt-2 text-center text-[11px] text-dim">
            {t("hero.figureNote")}
          </p>
        </div>
      </section>

      <div className="hero-cta mt-6 text-center" data-reveal>
        <Button
          tone="primary"
          onClick={() =>
            document.getElementById("start")?.scrollIntoView({ behavior: "smooth" })
          }
        >
          {t("hero.cta")}
        </Button>
      </div>

      {/* ── 설명 미리보기 — 로그인 전에도 설명 탭을 그대로 넘겨 본다 ── */}
      <section className="mt-16" data-reveal-group>
        <h2 className="text-lg font-semibold" data-reveal>{t("landing.guide")}</h2>
        <p className="mt-1 text-xs text-dim" data-reveal>{t("landing.guideNote")}</p>
        <GuidePreview closeLabel={t("landing.guideClose")} />
      </section>

      {/* ── 우리가 다르게 하는 것 ──────────────────────────── */}
      <section className="mt-16" data-reveal-group>
        <h2 className="text-lg font-semibold" data-reveal>
          {t("why.title")}
        </h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {PROOFS.map((k) => (
            <div
              key={k}
              className="rounded-xl border border-line bg-panel p-4"
              data-reveal
            >
              <p className="text-sm font-semibold">{t(`why.${k}`)}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">
                {t(`why.${k}.body`)}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 직원 ──────────────────────────────────────────── */}
      <section className="mt-16" data-reveal-group>
        <h2 className="text-lg font-semibold" data-reveal>
          {t("staff.title")}
        </h2>
        <p className="mt-1 text-xs text-dim" data-reveal>
          {t("staff.note")}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EMPLOYEES.map((e) => (
            <div
              key={e.id}
              className="emp-card rounded-xl border border-line bg-panel p-3
                transition-transform duration-200 hover:-translate-y-0.5"
              data-reveal
            >
              <div className="flex items-center gap-2">
                <span
                  className="grid size-8 place-items-center rounded-lg"
                  style={{
                    background: `color-mix(in srgb, var(--${e.id}) 16%, transparent)`,
                    color: `var(--${e.id})`,
                  }}
                  aria-hidden
                >
                  <Icon name={iconOfAgent(e.id)} size={18} />
                </span>
                <span className="text-sm font-semibold">
                  {t(`role.${e.id}`)}
                </span>
                <span className="ml-auto text-[11px] text-dim">{e.who}</span>
              </div>
              <p className="mt-2 text-xs text-muted">{t(`staff.${e.id}`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 요금제 ────────────────────────────────────────── */}
      {plans && (
        <section className="mt-16" data-reveal-group>
          <h2 className="text-lg font-semibold" data-reveal>
            {t("plans.title")}
          </h2>
          <p className="mt-1 text-xs text-dim" data-reveal>
            {t("plans.noFree")}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(plans).map(([name, p]) => (
              <div
                key={name}
                className="flex flex-col rounded-xl border border-line bg-panel p-4"
                data-reveal
              >
                <p className="text-xs text-dim">
                  {p.label}
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  ${p.price_usd}
                  <span className="text-xs font-normal text-dim">
                    {" "}
                    {t("plan.perMonth")}
                  </span>
                </p>
                <p className="mt-2 text-xs text-muted">
                  {p.source === "byok"
                    ? t("plan.byokCredits")
                    : t("plan.credits", { n: p.credits.toLocaleString() })}
                </p>
                <p className="mt-0.5 text-[11px] text-dim">
                  {t("plan.concurrent", { n: p.max_concurrent })}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-dim" data-reveal>
            {t("plans.byokNote")}
          </p>
        </section>
      )}

      {/* ── 가입 ──────────────────────────────────────────── */}
      <section className="mt-16 scroll-mt-8" id="start" data-reveal-group>
        <div className="mx-auto max-w-md" data-reveal>
          {children}
        </div>
      </section>

      {/* ── 정직한 항목 ───────────────────────────────────── */}
      <section className="mt-16" data-reveal-group>
        <div data-reveal>
          <Panel title={t("honest.title")}>
            <ul className="space-y-1.5 text-xs leading-relaxed text-muted">
              <li>· {t("honest.files")}</li>
              <li>
                ·{" "}
                <Filled
                  text={t("honest.injection")}
                  strong={t("honest.injection.strong")}
                />
              </li>
              <li style={{ color: "var(--warn)" }}>· {t("honest.noRealRun")}</li>
              <li style={{ color: "var(--warn)" }}>· {t("honest.noBilling")}</li>
            </ul>
          </Panel>
        </div>
      </section>

      <p className="mt-10 text-center text-[11px] text-dim">
        {t("landing.reducedMotion")}
      </p>
    </div>
  );
}

/**
 * 설명 미리보기 — 내려오다 70% 쯤 보이면 **화면 전체로** 펼친다.
 *
 * 작은 칸 안에서 여덟 장을 넘기면 글자가 작고, 칸 안의 휠이 페이지를 같이
 * 내린다. 펼친 동안에는 휠이 장을 넘기고(설명 탭 그대로), 끝 장에서 더 내리면
 * (또는 첫 장에서 더 올리면) 원래 크기로 돌아가며 페이지가 이어서 움직인다.
 * Esc · 닫기 버튼으로도 돌아간다.
 *
 * 한 번 닫으면 칸이 화면 밖으로 거의 나갔다가 다시 들어올 때까지는 펼치지
 * 않는다 — 닫자마자 또 펼쳐지면 그 자리를 지나갈 수가 없다.
 */
function GuidePreview({ closeLabel }: { closeLabel: string }) {
  const slot = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  const armed = useRef(true);

  useEffect(() => {
    const el = slot.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.intersectionRatio >= 0.7 && armed.current) {
        armed.current = false;
        setFull(true);
      } else if (e.intersectionRatio < 0.2) {
        armed.current = true;
      }
    }, { threshold: [0, 0.2, 0.7, 1] });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const close = useCallback((dir: 0 | 1 | -1 = 0) => {
    setFull(false);
    const el = slot.current;
    if (!el || !dir) return;
    // 넘긴 방향으로 페이지를 이어서 — 칸을 지나가게 한다.
    const scroller = scrollParent(el) as HTMLElement | null;
    const r = el.getBoundingClientRect();
    const by = dir > 0 ? r.bottom - window.innerHeight * 0.25 : r.top - window.innerHeight * 0.75;
    scroller?.scrollBy({ top: by, behavior: "smooth" });
  }, []);

  // 펼친 동안: Esc 로 닫고, 휠이 뒤의 페이지를 굴리지 않게 붙잡는다(React 의 휠은
  // passive 라 막지 못한다 — 네이티브로 건다). 장은 설명 탭이 넘긴다.
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const stop = (e: WheelEvent) => e.preventDefault();
    const el = panel.current;
    window.addEventListener("keydown", onKey);
    el?.addEventListener("wheel", stop, { passive: false });
    return () => {
      window.removeEventListener("keydown", onKey);
      el?.removeEventListener("wheel", stop);
    };
  }, [full, close]);

  return (
    // 등장 움직임(data-reveal)을 걸지 않는다 — 조상에 transform 이 남으면 fixed 가
    // 화면이 아니라 그 조상을 기준으로 펼쳐진다.
    <div ref={slot} className="mt-4 h-[min(680px,78vh)]">
      <motion.div
        ref={panel}
        layout
        transition={{ type: "spring", stiffness: 170, damping: 26 }}
        className={full
          ? "fixed inset-3 z-[70] overflow-hidden rounded-3xl border border-line-strong"
            + " bg-[color:var(--bg)] shadow-[0_40px_120px_rgba(0,0,0,0.7)]"
          : "relative h-full overflow-hidden rounded-2xl border border-line bg-[color:var(--bg)]"}
      >
        <StackCtx.Provider value={{
          inCard: false, active: true, preview: true,
          wheel: full, onEdge: (d) => close(d),
        }}>
          <GuidePage />
        </StackCtx.Provider>
        <AnimatePresence>
          {full && (
            <motion.button
              type="button"
              onClick={() => close()}
              aria-label={closeLabel}
              title={closeLabel}
              className="absolute right-3 top-2.5 z-10 grid size-8 place-items-center
                rounded-full border border-line bg-panel2 text-muted hover:text-fg"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
            >
              ×
            </motion.button>
          )}
        </AnimatePresence>
      </motion.div>
      {/* 펼친 동안 뒤를 어둡게 — 앞에 무엇이 떠 있는지 분명하게. */}
      <AnimatePresence>
        {full && (
          <motion.div
            className="fixed inset-0 z-[65] bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => close()}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
