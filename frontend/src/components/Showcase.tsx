"use client";

/**
 * 궤도 쇼케이스 — 항목 하나를 가운데 크게, 다음 것을 오른쪽 위에 작게,
 * 지나간 것을 왼쪽 아래에 두고, 넘길 때마다 셋이 **같은 타원 궤도를 따라**
 * 한 칸씩 돈다. 배경이 그 항목의 색으로 바뀐다.
 *
 * 설명 탭의 '직원' 장에서 직원 다섯을 보여준다. 설명 탭 안에 들어가므로
 * (`embedded`) 바깥의 장 넘기기와 싸우지 않게 입력을 제 안에서 끝낸다.
 * 누빈 그림(Puffer)은 탭을 스크롤로 넘길 때(ScrollTabs)도 같이 쓴다.
 *
 * ## 움직임 (motion.dev)
 *
 * - 자리 이동: queued → next → center → prev → gone 다섯 자리를 스프링으로.
 *   떠나는 쪽이 먼저, 들어오는 쪽이 조금 늦게 출발한다.
 * - 배경색 · 뒤의 큰 아이콘 · 이름 글자가 넘긴 방향으로 같이 넘어간다.
 * - 궤도 앞쪽 호를 빛 한 점이 훑는다 — 무엇이 어느 쪽으로 돌았는지.
 * - 가운데 항목은 제자리에서 천천히 뜬다.
 * - 움직임을 줄인 사람에게는 자동 넘김과 떠다니기를 끈다.
 *
 * ## 크기는 화면이 아니라 상자를 따른다
 *
 * 설명 탭 안에서는 창보다 작은 상자에 들어간다. 그래서 글자·그림 크기와
 * 좁은 화면 배치를 컨테이너 쿼리(cq 단위 · `@2xl:`)로 잡았다.
 */
import {
  AnimatePresence, LayoutGroup, MotionConfig, animate, motion,
  useMotionValue, useReducedMotion, useTransform, type PanInfo,
} from "motion/react";
import Link from "next/link";
import {
  useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode,
} from "react";

import { Galaxy } from "./Galaxy";
import { GLYPHS, Icon, type IconName } from "./icons";
import { useLang } from "@/lib/i18n";
import { useStack } from "@/lib/stack";

export type ShowItem = {
  id: string;
  icon: IconName;
  /** 누빈 그림의 바탕 · 밝은 면 · 그림자. 배경은 직원과 상관없이 은하(Galaxy). */
  bg: string;
  hi: string;
  deep: string;
  /** 아이콘을 긋는 마커 색 두 개(시작 → 끝). 쨍하게. */
  ink?: readonly [string, string];
  name: string;
  sub: string;
  body: string;
  cta?: { label: string; href: string };
};

type Props = {
  items: readonly ShowItem[];
  title: string;
  label: string;
  chips?: { label: string; values: readonly string[]; of: (item: ShowItem) => string };
  cta?: { label: string; href: string };
  autoplay?: boolean;
  embedded?: boolean;
};

const AUTOPLAY_MS = 5000;
const WHEEL_LOCK_MS = 750;
/** 마지막 직원에서 붙잡은 뒤, 이 안에 한 번 더 굴리면 넘어간다. 지나면 다시 붙잡는다. */
const EDGE_ARMED_MS = 4000;
/** 굴림이 이만큼 끊겨야 '새로 굴렸다'고 본다 — 그 전은 같은 굴림의 관성이다. */
const GESTURE_GAP_MS = 180;

type Slot = "queued" | "next" | "center" | "prev" | "gone";

/** 궤도 위 다섯 자리. 위치는 무대 기준 % — 상자 크기와 상관없이 같은 모양. */
const SLOTS: Record<Slot, {
  left: string; top: string; scale: number; rotate: number; opacity: number; z: number;
}> = {
  queued: { left: "98%", top: "2%", scale: 0.12, rotate: 34, opacity: 0, z: 10 },
  next: { left: "80%", top: "22%", scale: 0.34, rotate: 14, opacity: 1, z: 20 },
  center: { left: "50%", top: "52%", scale: 1, rotate: 0, opacity: 1, z: 30 },
  prev: { left: "11%", top: "90%", scale: 0.52, rotate: -16, opacity: 1, z: 40 },
  gone: { left: "-14%", top: "118%", scale: 0.4, rotate: -34, opacity: 0, z: 10 },
};

/** 끝에서 처음으로 이어 돌지 않는다 — 스크롤은 위아래가 있어야 한다. */
function slotOf(rel: number): Slot {
  if (rel === 0) return "center";
  if (rel === 1) return "next";
  if (rel >= 2) return "queued";
  if (rel === -1) return "prev";
  return "gone";
}

/** 궤도(타원) — viewBox 1000×240 안의 중심·반지름. 앞쪽 호와 빛 점이 같이 쓴다. */
const ORBIT = { cx: 500, cy: 120, rx: 490, ry: 108 };

export function Showcase({
  items, title, label, chips, cta, autoplay = false, embedded = false,
}: Props) {
  const { t } = useLang();
  const reduce = useReducedMotion();
  const n = items.length;
  const [active, setActive] = useState(0);
  const [dir, setDir] = useState<1 | -1>(1);
  const [paused, setPaused] = useState(false);
  const wheelAt = useRef(0);
  const stage = useRef<HTMLElement>(null);
  const s = items[active];
  const link = s.cta ?? cta;
  // 탭 카드 덱에서 이 화면이 비켜 서 있으면 보는 사람이 없다 — 돌지 않는다.
  const { active: onStage } = useStack();
  const running = autoplay && !paused && !reduce && onStage;

  const goTo = useCallback((i: number) => {
    setActive((a) => {
      const next = Math.max(0, Math.min(n - 1, i));
      if (next !== a) setDir(next > a ? 1 : -1);
      return next;
    });
  }, [n]);
  const go = useCallback((d: number) => setActive((a) => {
    const next = Math.max(0, Math.min(n - 1, a + d));
    if (next !== a) setDir(d > 0 ? 1 : -1);
    return next;
  }), [n]);

  // 자동 넘김. 넘어갈 때마다 타이머를 새로 건다 — 손으로 넘긴 직후 바로
  // 또 넘어가 버리면 방금 고른 것을 읽을 틈이 없다. 끝에 닿으면 처음으로.
  useEffect(() => {
    if (!running) return;
    const id = window.setTimeout(() => goTo(active + 1 < n ? active + 1 : 0), AUTOPLAY_MS);
    return () => window.clearTimeout(id);
  }, [active, running, n, goTo]);

  // 화면 전체를 차지할 때만 창 전체의 키를 듣는다. 설명 탭 안에서는
  // ←/→ 가 장 넘기기이므로, 이 상자에 초점이 있을 때만 받는다(onKeyDown).
  useEffect(() => {
    if (embedded) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el?.closest("input, textarea, select, [contenteditable]")) return;
      if (["ArrowRight", "ArrowDown", "PageDown"].includes(e.key)) go(1);
      else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) go(-1);
      else if (e.key === "Home") goTo(0);
      else if (e.key === "End") goTo(n - 1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [embedded, go, goTo, n]);

  // 설명 탭의 장은 옆으로 끌면 넘어간다. 그 끌기는 **네이티브** pointerdown 을
  // 듣기 때문에 React 쪽에서 막으면 늦다 — 상자에서 직접 끊는다.
  useEffect(() => {
    const el = stage.current;
    if (!embedded || !el) return;
    const stop = (e: PointerEvent) => e.stopPropagation();
    el.addEventListener("pointerdown", stop);
    return () => el.removeEventListener("pointerdown", stop);
  }, [embedded]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (!embedded) return;
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.stopPropagation();
    e.preventDefault();
    go(d);
  };

  // 휠은 **네이티브로, passive 없이** 듣는다. React 의 onWheel 은 passive 라
  // preventDefault 가 안 먹어서, 직원을 넘기는 동안 바깥 페이지(로그인 전 랜딩)와
  // 설명 장의 칸까지 같이 내려갔다. 넘길 수 있는 방향이면 화면을 붙잡는다.
  const wheelState = useRef({ active, n, embedded, go });
  // 마지막 직원에서는 **두 번** 내려야 넘어간다 — 한 번은 붙잡고 "한 번 더"를
  // 보인다. 마지막 사람을 제대로 보기도 전에 장이 넘어가 버리지 않게.
  const edge = useRef<{ index: number; at: number; last: number } | null>(null);
  const [edgeHint, setEdgeHint] = useState(false);
  const hintTimer = useRef(0);
  useEffect(() => {
    wheelState.current = { active, n, embedded, go };
  });
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const onWheel = (e: globalThis.WheelEvent) => {
      const { active: a, n: count, embedded: inside, go: move } = wheelState.current;
      const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      const step = d > 0 ? 1 : -1;
      if (inside && step > 0 && a === count - 1) {
        const now = Date.now();
        const armed = edge.current;
        const fresh = armed && armed.index === a && now - armed.at < EDGE_ARMED_MS;
        // 두 번째 굴림 — 관성이 아니라 **새로** 굴렸을 때만(잠깐 멈춘 뒤) 넘겨준다.
        if (fresh && now - armed.last > GESTURE_GAP_MS && now - armed.at > WHEEL_LOCK_MS / 2) {
          edge.current = null;
          setEdgeHint(false);
          return;
        }
        e.preventDefault();
        e.stopPropagation();
        if (fresh) {
          armed.last = now;
        } else {
          edge.current = { index: a, at: now, last: now };
          setEdgeHint(true);
          window.clearTimeout(hintTimer.current);
          hintTimer.current = window.setTimeout(() => setEdgeHint(false), EDGE_ARMED_MS);
        }
        return;
      }
      // 안에 박혀 있을 때 앞쪽 끝에 닿으면 휠을 바깥(장 넘기기 · 페이지)에 넘긴다.
      if (inside && (a + step < 0 || a + step > count - 1)) return;
      e.preventDefault();
      e.stopPropagation();
      if (Math.abs(d) < 18) return;
      const now = Date.now();
      if (now - wheelAt.current < WHEEL_LOCK_MS) return;
      wheelAt.current = now;
      move(step);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
      window.clearTimeout(hintTimer.current);
    };
  }, []);

  const onPanEnd = (_: unknown, info: PanInfo) => {
    const { x, y } = info.offset;
    if (Math.abs(x) >= 50 && Math.abs(x) > Math.abs(y)) go(x < 0 ? 1 : -1);
  };

  return (
    <MotionConfig reducedMotion="user">
      <motion.section
        ref={stage}
        className={`relative h-full select-none overflow-hidden text-white outline-none
          ${embedded ? "rounded-3xl" : "rounded-[28px]"}
          touch-pan-y
          shadow-[0_30px_80px_-30px_rgba(0,0,0,0.7)]
          focus-visible:ring-2 focus-visible:ring-white/60`}
        style={{ containerType: "size" }}
        onPanEnd={onPanEnd}
        onKeyDown={onKeyDown}
        tabIndex={embedded ? 0 : -1}
        role="region"
        aria-roledescription="carousel"
        aria-label={label}
      >
        <Galaxy />
        <Backdrop s={s} dir={dir} />

        <Orbit layer="back" />
        {items.map((e, i) => {
          const slot = slotOf(i - active);
          return (
            <Figure
              key={e.id}
              s={e}
              slot={slot}
              dir={dir}
              float={!reduce}
              label={e.name}
              onPick={slot === "next" ? () => go(1) : slot === "prev" ? () => go(-1) : undefined}
              onHover={slot === "center" && autoplay ? setPaused : undefined}
            />
          );
        })}
        <Orbit layer="front" active={active} dir={dir} onDrag={go} hint={t("show.drag")} />

        <LayoutGroup id={label}>
          <Header
            items={items}
            active={active}
            onPick={goTo}
            deep={s.deep}
            chips={chips && { label: chips.label, values: chips.values, on: chips.of(s) }}
          />
        </LayoutGroup>

        <Headline text={title} embedded={embedded} />

        {/* ── 아래 줄: 설명 · 이름 · 조작 ───────────────────── */}
        <div className="absolute inset-x-0 bottom-0 z-50 flex items-end gap-4 px-5 pb-5
          @2xl:px-8 @2xl:pb-7">
          <div className="min-w-0 flex-1 @2xl:max-w-[290px]" aria-live="polite">
            <div className="@2xl:hidden">
              <Swap k={s.id} dir={dir} className="text-3xl font-semibold tracking-tight">
                {s.name}
                <span className="mt-1 block text-[11px] font-normal tracking-normal
                  text-white/70">
                  {s.sub}
                </span>
              </Swap>
            </div>
            <Swap
              k={s.id + "-body"}
              dir={dir}
              className="mt-1 text-xs leading-relaxed text-white/90 @2xl:text-[13px]
                [text-shadow:0_1px_12px_rgba(0,0,0,0.45)]"
            >
              {s.body}
            </Swap>
          </div>

          <div className="pointer-events-none absolute bottom-6 left-1/2 hidden -translate-x-1/2
            text-center @2xl:block">
            <Swap k={s.id} dir={dir}
              className="whitespace-nowrap text-[clamp(2rem,4.6cqw,3.6rem)] font-medium
                leading-none tracking-tight">
              {s.name}
            </Swap>
            <Swap k={s.id + "-sub"} dir={dir} className="mt-2 text-xs text-white/70">
              {s.sub}
            </Swap>
          </div>

          <Controls
            active={active}
            n={n}
            go={go}
            running={running}
            autoplay={autoplay}
            prevLabel={t("show.prev")}
            nextLabel={t("show.next")}
            link={link}
            deep={s.deep}
            hint={edgeHint && active === n - 1 ? t("show.oneMore") : null}
          />
        </div>
      </motion.section>
    </MotionConfig>
  );
}

/* ─────────────────────────────────────────────────────────────── */

/** 배경의 빛 번짐 + 뒤에 크게 깔린 아이콘(쇼케이스의 로고 자리). */
export function Backdrop({ s, dir }: { s: Pick<ShowItem, "id" | "icon">; dir: 1 | -1 }) {
  return (
    <>
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(55% 60% at 55% 48%, rgba(255,255,255,0.2), transparent 70%)," +
            "radial-gradient(130% 110% at 50% 50%, transparent 55%, rgba(0,0,0,0.38))",
        }}
        aria-hidden
      />
      <AnimatePresence initial={false} custom={dir}>
        <motion.div
          key={s.id}
          className="pointer-events-none absolute left-[58%] top-[46%] z-0 text-white"
          style={{ x: "-50%", y: "-50%" }}
          custom={dir}
          variants={{
            enter: (d: number) => ({ opacity: 0, scale: 0.6, rotate: 40 * d }),
            show: { opacity: 0.12, scale: 1, rotate: -8 },
            leave: (d: number) => ({ opacity: 0, scale: 1.35, rotate: -40 * d }),
          }}
          initial="enter"
          animate="show"
          exit="leave"
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
          aria-hidden
        >
          <Icon name={s.icon} size={800} strokeWidth={0.9} className="h-[95cqmin] w-[95cqmin]" />
        </motion.div>
      </AnimatePresence>
    </>
  );
}

/** 궤도 위의 항목 하나. 자리만 바뀌고 요소는 그대로라 이어서 움직인다. */
function Figure({
  s, slot, dir, float, label, onPick, onHover,
}: {
  s: ShowItem;
  slot: Slot;
  dir: 1 | -1;
  float: boolean;
  label: string;
  onPick?: () => void;
  onHover?: (v: boolean) => void;
}) {
  const target = SLOTS[slot];
  // 앞으로 넘길 때는 빠지는 쪽(prev)이 먼저, 들어오는 쪽이 조금 늦게 출발한다.
  const order: Slot[] = dir === 1
    ? ["gone", "prev", "center", "next", "queued"]
    : ["queued", "next", "center", "prev", "gone"];
  const delay = order.indexOf(slot) * 0.045;

  // 요소 종류는 바꾸지 않는다 — div 와 button 을 오가면 자리가 바뀔 때마다
  // 새로 태어나서 궤도를 따라 움직이지 못하고 처음 자리에서 다시 날아온다.
  return (
    <motion.div
      role={onPick ? "button" : undefined}
      onClick={onPick}
      onKeyDown={onPick ? (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          onPick();
        }
      } : undefined}
      aria-label={onPick ? label : undefined}
      aria-hidden={slot === "queued" || slot === "gone" ? true : undefined}
      tabIndex={onPick ? 0 : -1}
      className={`absolute block w-[min(62cqw,46cqmin,440px)] ${onPick ? "cursor-pointer" : ""}`}
      style={{ x: "-50%", y: "-50%", zIndex: target.z }}
      initial={{ left: SLOTS.queued.left, top: SLOTS.queued.top, scale: 0.12, rotate: 34,
                 opacity: 0 }}
      animate={{
        left: target.left,
        top: target.top,
        scale: target.scale,
        rotate: target.rotate,
        opacity: target.opacity,
      }}
      whileHover={onPick ? { scale: target.scale * 1.08 } : undefined}
      transition={{ type: "spring", stiffness: 95, damping: 17, mass: 0.9, delay }}
      onHoverStart={onHover ? () => onHover(true) : undefined}
      onHoverEnd={onHover ? () => onHover(false) : undefined}
    >
      {/* 가운데에서만 천천히 뜬다(CSS — globals.css 의 anim-float). */}
      <div className={float && slot === "center" ? "anim-float" : undefined}>
        <Puffer s={s} />
      </div>
    </motion.div>
  );
}

/**
 * 유리 타일 위에 마커로 그린 아이콘 — 인스타그램 로고처럼.
 *
 * 타일은 반투명 유리다(뒤의 은하가 흐리게 비친다). 아이콘은 끝이 둥근 선 **한 획**을
 * 쨍한 두 색 그라디언트(`ink`)로 긋는다. 번짐 · 떨림을 주던 층은 걷었다 — 칠이
 * 선 밖으로 삐져나와 보였다. 선 한가운데에 가는 윤기 한 줄만 둔다.
 */
export function Puffer({ s }: {
  s: Pick<ShowItem, "icon" | "bg" | "hi" | "deep" | "ink">;
}) {
  const id = useId().replace(/:/g, "");
  // 잉크 색이 따로 없으면 밝은 면 → 바탕색. 어두운 색(deep)은 쓰지 않는다 — 탁해진다.
  const ink = s.ink ?? [s.hi, s.bg];
  return (
    <div className="relative aspect-square w-full">
      {/* 바닥 그림자 · 직원 색 빛 */}
      <div className="absolute bottom-[2%] left-1/2 h-[9%] w-[60%] -translate-x-1/2
        rounded-[50%] bg-black/45 blur-2xl" />
      <div className="absolute inset-[14%] rounded-[34%] opacity-60 blur-3xl"
        style={{ background: s.bg }} />
      {/* 유리 타일 */}
      <div
        className="absolute inset-[7%] overflow-hidden rounded-[30%] border border-white/35
          backdrop-blur-xl"
        style={{
          background:
            "linear-gradient(150deg, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0.08) 45%," +
            " rgba(255,255,255,0.04) 70%, rgba(255,255,255,0.14) 100%)",
          boxShadow:
            "inset 0 1.5px 0 rgba(255,255,255,0.55), inset 0 -18px 40px rgba(0,0,0,0.22)," +
            " inset 0 0 0 1px rgba(255,255,255,0.06), 0 40px 70px -26px rgba(0,0,0,0.6)",
        }}
      >
        {/* 윗면 반사 — 유리 모서리를 타고 도는 흰 빛 */}
        <div className="absolute -left-[10%] -top-[30%] h-[70%] w-[120%] rotate-[-12deg]
          rounded-[50%] bg-gradient-to-b from-white/35 to-transparent" />
        <div className="absolute bottom-[6%] right-[8%] h-[18%] w-[40%] rounded-[50%]
          bg-white/10 blur-xl" />
        {/* 마커로 그린 아이콘 — 한 획, 번짐 없이 */}
        <svg viewBox="0 0 24 24" fill="none" aria-hidden shapeRendering="geometricPrecision"
          className="absolute left-1/2 top-1/2 h-[58%] w-[58%] -translate-x-1/2 -translate-y-1/2
            overflow-visible drop-shadow-[0_3px_6px_rgba(0,0,0,0.35)]">
          <defs>
            <linearGradient id={`ink-${id}`} x1="3" y1="21" x2="21" y2="3"
              gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor={ink[0]} />
              <stop offset="1" stopColor={ink[1]} />
            </linearGradient>
          </defs>
          {/* 마커 선 — 선 하나로 끝낸다. 칠이 선 밖으로 나가지 않는다. */}
          <g stroke={`url(#ink-${id})`} strokeWidth={2.2} strokeLinecap="round"
            strokeLinejoin="round">
            {GLYPHS[s.icon]}
          </g>
          {/* 선 한가운데의 가는 윤기 — 선과 같은 길 위에만 있다(어긋나지 않게). */}
          <g stroke="white" strokeWidth={0.45} strokeLinecap="round" strokeLinejoin="round"
            opacity={0.5}>
            {GLYPHS[s.icon]}
          </g>
        </svg>
      </div>
    </div>
  );
}

/** 타원 궤도. 뒤쪽(전체 선)과 앞쪽(아래 호)을 따로 그려서, 가운데 항목이
 *  궤도 **안에** 서 있는 것처럼 보이게 한다. */
export function Orbit({
  layer, active = 0, dir = 1, onDrag, hint, className,
}: {
  layer: "back" | "front";
  /** 자리 · 크기. 없으면 쇼케이스의 자리(가운데 아래). */
  className?: string;
  active?: number;
  dir?: 1 | -1;
  onDrag?: (d: number) => void;
  hint?: string;
}) {
  const { cx, cy, rx, ry } = ORBIT;
  const theta = useMotionValue(90);
  const glow = useMotionValue(0);
  const px = useTransform(theta, (d) => cx + rx * Math.cos((d * Math.PI) / 180));
  const py = useTransform(theta, (d) => cy + ry * Math.sin((d * Math.PI) / 180));
  const first = useRef(true);

  // 넘길 때마다 빛 한 점이 앞쪽 호를 넘긴 방향으로 훑는다.
  useEffect(() => {
    if (layer !== "front") return;
    if (first.current) {
      first.current = false;
      return;
    }
    const [a, b] = dir === 1 ? [0, 180] : [180, 0];
    const c1 = animate(theta, [a, b], { duration: 1.0, ease: [0.45, 0, 0.2, 1] });
    const c2 = animate(glow, [0, 1, 1, 0], { duration: 1.0, times: [0, 0.15, 0.8, 1] });
    return () => {
      c1.stop();
      c2.stop();
    };
  }, [active, dir, layer, theta, glow]);

  const path =
    layer === "back"
      ? `M ${cx - rx} ${cy} A ${rx} ${ry} 0 1 1 ${cx + rx} ${cy} A ${rx} ${ry} 0 1 1 ${cx - rx} ${cy}`
      : `M ${cx - rx} ${cy} A ${rx} ${ry} 0 0 0 ${cx + rx} ${cy}`;

  return (
    <div
      className={`pointer-events-none absolute aspect-[1000/240]
        ${className ?? "left-1/2 top-[68%] w-[94%] @2xl:w-[66%]"}
        ${layer === "back" ? "z-[25]" : "z-[35]"}`}
      style={{ transform: "translate(-50%, -50%) rotate(-5deg)" }}
    >
      <motion.svg
        viewBox="0 0 1000 240"
        className="absolute inset-0 h-full w-full overflow-visible"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.2, delay: 0.3 }}
        aria-hidden
      >
        <motion.path
          d={path}
          fill="none"
          stroke="white"
          strokeOpacity={layer === "back" ? 0.28 : 0.6}
          strokeWidth={1.4}
          vectorEffect="non-scaling-stroke"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.6, ease: [0.65, 0, 0.35, 1], delay: 0.2 }}
        />
        {layer === "front" && (
          <motion.circle cx={px} cy={py} r={5} fill="white" style={{ opacity: glow }}
            filter="drop-shadow(0 0 8px rgba(255,255,255,0.95))" />
        )}
      </motion.svg>

      {layer === "front" && onDrag && (
        <motion.button
          type="button"
          aria-label={hint}
          title={hint}
          className="pointer-events-auto absolute left-1/2 top-[95%] hidden size-7 cursor-grab @2xl:grid
            place-items-center rounded-full bg-black/85 text-[9px] text-white shadow-lg
            active:cursor-grabbing"
          style={{ x: "-50%", y: "-50%" }}
          drag="x"
          dragConstraints={{ left: 0, right: 0 }}
          dragElastic={0.6}
          whileHover={{ scale: 1.15 }}
          whileTap={{ scale: 0.92 }}
          onDragEnd={(_, info) => {
            if (Math.abs(info.offset.x) > 30) onDrag(info.offset.x < 0 ? 1 : -1);
          }}
          onClick={() => onDrag(1)}
        >
          ◂▸
        </motion.button>
      )}
    </div>
  );
}

/** 위 줄: 로고 · 항목 탭 · 칩. */
function Header({
  items, active, onPick, deep, chips,
}: {
  items: readonly ShowItem[];
  active: number;
  onPick: (i: number) => void;
  deep: string;
  chips?: { label: string; values: readonly string[]; on: string };
}) {
  return (
    <>
      <div className="absolute left-5 top-5 z-50 flex items-center gap-2 @2xl:left-8
        @2xl:top-7">
        <Icon name="building" size={22} />
        <span className="text-xs font-semibold tracking-[0.2em]">AI COMPANY</span>
      </div>

      <nav
        className="absolute left-1/2 top-5 z-50 hidden -translate-x-1/2 items-center gap-0.5
          rounded-full bg-black/20 p-1 backdrop-blur-md @4xl:flex @2xl:top-6"
      >
        {items.map((e, i) => (
          <button
            key={e.id}
            type="button"
            onClick={() => onPick(i)}
            aria-current={i === active ? "true" : undefined}
            className="relative whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs
              transition-colors"
            style={{ color: i === active ? deep : "rgba(255,255,255,0.85)" }}
          >
            {i === active && (
              <motion.span
                layoutId="show-pill"
                className="absolute inset-0 rounded-full bg-white"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <span className="relative">{e.name}</span>
          </button>
        ))}
      </nav>

      {chips && (
        // 좁은 상자에서는 제목과 부딪힌다 — 그때는 아래 이름 옆 글자로만 보인다.
        <div className="absolute right-5 top-5 z-50 hidden flex-col items-end gap-1.5
          @2xl:right-8 @2xl:top-7 @2xl:flex">
          <span className="text-[10px] uppercase tracking-widest text-white/60">
            {chips.label}
          </span>
          <div className="flex gap-1.5">
            {chips.values.map((m) => (
              <span
                key={m}
                className="relative grid h-8 min-w-8 place-items-center rounded-full px-2.5
                  text-[11px] font-semibold"
                style={{
                  color: m === chips.on ? deep : "rgba(255,255,255,0.75)",
                  background: m === chips.on ? undefined : "rgba(0,0,0,0.18)",
                }}
              >
                {m === chips.on && (
                  <motion.span
                    layoutId="show-chip"
                    className="absolute inset-0 rounded-full bg-white"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                <span className="relative">{m}</span>
              </span>
            ))}
          </div>
        </div>
      )}

    </>
  );
}

/** 왼쪽 위 큰 제목. 처음 한 번, 줄마다 아래에서 올라온다. */
function Headline({ text, embedded }: { text: string; embedded: boolean }) {
  return (
    <h1
      className={`pointer-events-none absolute left-5 z-50 font-medium leading-[1.04]
        tracking-tight @2xl:left-8
        ${embedded
          ? "top-14 text-[clamp(1.6rem,4.4cqw,3.2rem)] @2xl:top-20"
          : "top-16 text-[clamp(1.9rem,4.8cqw,4rem)] @2xl:top-24"}`}
    >
      {text.split("\n").map((line, i) => (
        <span key={i} className="block overflow-hidden pb-[0.06em]">
          <motion.span
            className="block"
            initial={{ y: "105%" }}
            animate={{ y: "0%" }}
            transition={{ duration: 0.9, delay: 0.15 + i * 0.1, ease: [0.22, 1, 0.36, 1] }}
          >
            {line}
          </motion.span>
        </span>
      ))}
    </h1>
  );
}

/** 글자 교체 — 넘긴 방향으로 밀려 나가고 반대편에서 들어온다. */
export function Swap({
  k, dir, className, children,
}: {
  k: string;
  dir: 1 | -1;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className="relative overflow-hidden">
      <AnimatePresence mode="popLayout" initial={false} custom={dir}>
        <motion.p
          key={k}
          className={className}
          custom={dir}
          variants={{
            enter: (d: number) => ({ y: `${d * 100}%`, opacity: 0 }),
            show: { y: "0%", opacity: 1 },
            leave: (d: number) => ({ y: `${d * -100}%`, opacity: 0 }),
          }}
          initial="enter"
          animate="show"
          exit="leave"
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        >
          {children}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}

/** 오른쪽 아래: 화살표 · 몇 번째인지 · 진행 막대 · 이동 버튼.
 *  자동 넘김이면 막대가 남은 시간을, 아니면 전체 중 어디쯤인지를 보인다. */
function Controls({
  active, n, go, running, autoplay, prevLabel, nextLabel, link, deep, hint,
}: {
  active: number;
  n: number;
  go: (d: number) => void;
  running: boolean;
  autoplay: boolean;
  prevLabel: string;
  nextLabel: string;
  link?: { label: string; href: string };
  deep: string;
  /** 마지막 직원에서 한 번 붙잡았을 때의 안내 — "한 번 더 내리면 넘어갑니다". */
  hint: string | null;
}) {
  const round =
    "grid size-11 place-items-center rounded-full border border-white/45 text-white/90" +
    " transition-colors enabled:hover:bg-white enabled:hover:text-[color:var(--deep)]" +
    " disabled:opacity-35";
  return (
    <div className="ml-auto flex shrink-0 flex-col items-end gap-3"
      style={{ ["--deep" as string]: deep }}>
      <div className="flex gap-2">
        <motion.button type="button" className={round} onClick={() => go(-1)}
          disabled={active === 0} aria-label={prevLabel} whileTap={{ scale: 0.9, x: -3 }}>
          <span aria-hidden className="text-lg leading-none">←</span>
        </motion.button>
        <motion.button type="button" className={round} onClick={() => go(1)}
          disabled={active === n - 1} aria-label={nextLabel} whileTap={{ scale: 0.9, x: 3 }}>
          <span aria-hidden className="text-lg leading-none">→</span>
        </motion.button>
      </div>

      <div className="flex w-[100px] flex-col items-center gap-1.5">
        <span className="text-sm tabular-nums">
          <span className="font-semibold">{String(active + 1).padStart(2, "0")}</span>
          <span className="text-white/55"> / {String(n).padStart(2, "0")}</span>
        </span>
        <span className="h-px w-full overflow-hidden bg-white/25">
          {autoplay ? (
            <motion.span
              key={`${active}-${running}`}
              className="block h-full origin-left bg-white"
              initial={{ scaleX: 0 }}
              animate={{ scaleX: running ? 1 : 0 }}
              transition={{ duration: running ? AUTOPLAY_MS / 1000 : 0, ease: "linear" }}
            />
          ) : (
            <motion.span
              className="block h-full origin-left bg-white"
              initial={false}
              animate={{ scaleX: (active + 1) / n }}
              transition={{ type: "spring", stiffness: 200, damping: 30 }}
            />
          )}
        </span>
      </div>

      <AnimatePresence>
        {hint && (
          <motion.span
            className="-mt-1 whitespace-nowrap rounded-full bg-white/15 px-2.5 py-1 text-[11px]
              text-white backdrop-blur-md"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            aria-live="polite"
          >
            {hint} ↓
          </motion.span>
        )}
      </AnimatePresence>

      {link && (
        <motion.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}>
          <Link
            href={link.href}
            className="block whitespace-nowrap rounded-full bg-white px-5 py-2.5 text-sm
              font-semibold shadow-[0_10px_30px_-10px_rgba(0,0,0,0.5)]"
            style={{ color: deep }}
          >
            {link.label}
          </Link>
        </motion.div>
      )}
    </div>
  );
}
