"use client";

/**
 * 탭 카드 덱 — 사무실 · 요금제 · 설정 · 설명 네 화면을 **카드**로 세운다.
 * 가운데 카드가 지금 쓰는 탭이고, 넘기면 옆 탭 카드가 궤도를 따라 날아와
 * 선다(설명 탭 '직원' 장의 쇼케이스와 같은 움직임).
 *
 * ## 모양
 *
 * - 카드는 위아래로 꽉 차고 양옆으로 90%. 비켜 선 카드(미리보기)는 두지
 *   않는다 — 넘어가는 동안에만 보인다.
 * - 양옆 여백이 조작판이다. 왼쪽은 탭 네 개와 몇 번째인지, 오른쪽은 이전 ·
 *   다음 · 언어 · 사용자. 앱 머리는 이 네 주소에서 그리지 않는다(AppHeader).
 *   폰처럼 좁으면 여백이 없으니 같은 것들을 아래 한 줄에 모은다.
 *
 * ## 비율 — 카드 안에서 스크롤하지 않게
 *
 * 카드는 창보다 작다. 화면을 카드 크기대로 그리면 창 전체에서는 한눈에
 * 보이던 것이 카드 안에서 스크롤로 밀린다. 그래서 각 화면을 **적어도
 * 제 `designH` 높이의 창인 것처럼** 그린 뒤 카드 크기로 줄인다(CSS zoom —
 * transform 과 달리 글자를 다시 그려 흐려지지 않고, 마우스 좌표도 맞는다).
 *
 * ## 스크롤로 넘기되, 페이지를 옮기지 않는다
 *
 * - **카드 밖**(양옆 여백)에서 휠을 굴리거나 끌면 옆 탭으로 넘어간다.
 * - **카드 안**의 휠은 그 화면의 것이다. 끝에 닿아도 넘기지 않는다.
 * - 네 화면은 처음부터 다 떠 있고 자리만 바뀐다 — 넘겨도 입력하던 것 ·
 *   스크롤 위치가 남는다. 비켜 있는 카드는 `inert`.
 * - 탭 주소로 가는 링크도 카드를 돌린다. 주소는 `replaceState` 로만 바꾼다.
 *
 * ## 가볍게
 *
 * - 네 화면의 코드는 **따로 받는다**(next/dynamic). 덱은 레이아웃에 걸려 모든
 *   주소가 받으므로, 정적으로 불러오면 프로젝트 상세를 열어도 네 화면 코드를 다
 *   받는다.
 * - 처음에는 가운데 카드만 띄운다. 양옆 이웃은 브라우저가 한가할 때 미리
 *   띄워 두고(넘길 때 끊기지 않게), 먼 탭은 처음 가는 순간에 띄운다. 한 번 띄운
 *   카드는 내리지 않는다 — 상태를 지키는 게 이 덱의 약속이다.
 * - 카드는 transform(x · y · scale · rotate)으로만 움직인다. left/top 을 움직이면
 *   큰 화면 통째로 매 프레임 배치를 다시 한다.
 * - 비켜 선 카드는 다 빠진 뒤 `visibility: hidden` — 그리지 않는다.
 *
 * 배경은 탭마다 바꾸지 않고 은하 한 장(Galaxy)으로 통일했다.
 *
 * 탭 네 곳이 아닌 주소(프로젝트 상세 · 수동 실행 · 재설정 등)는 덱 없이
 * 원래대로 그린다.
 */
import { LayoutGroup, MotionConfig, motion } from "motion/react";
import { usePathname } from "next/navigation";
import {
  useCallback, useEffect, useRef, useState, type ComponentType, type ReactNode,
  type WheelEvent,
} from "react";

import dynamic from "next/dynamic";

import { LangSwitch } from "./LangSwitch";
import { GALAXY_DEEP, Galaxy } from "./Galaxy";
import { Backdrop } from "./Showcase";
import { UserMenu } from "./UserMenu";
import { Icon, type IconName } from "./icons";
import { type Key, useLang } from "@/lib/i18n";
import { StackCtx } from "@/lib/stack";

// 받는 동안은 빈 카드 — 카드 틀과 배경이 이미 있어 깜빡임이 없다.
const blank = () => <div className="h-full" />;
const OfficePage = dynamic(() => import("@/app/page"), { loading: blank });
const PricingPage = dynamic(() => import("@/app/pricing/page"), { loading: blank });
const SettingsPage = dynamic(() => import("@/app/settings/page"), { loading: blank });
const GuidePage = dynamic(() => import("@/app/guide/page"), { loading: blank });

/** 순서가 곧 넘기는 순서다. */
const TABS: readonly {
  id: "office" | "pricing" | "settings" | "guide";
  href: string; nav: Key; icon: IconName;
  Page: ComponentType;
  /** 이 화면을 이 높이의 창인 것처럼 그린 뒤 카드에 맞춰 줄인다. 사무실은
   *  지시창의 '시작' 버튼까지 다 보이려면 1220px 가 들지만(실측) 그러면
   *  노트북에서 글자가 너무 작다 — 1100 으로 두고 지시창 끝자락만 스크롤한다.
   *  요금제 · 설정은 원래 긴 문서라 줄여도 스크롤이 남으니 글자 크기를 지킨다. */
  designH: number;
}[] = [
  { id: "office", href: "/", nav: "nav.office", icon: "building",
    Page: OfficePage, designH: 1100 },
  { id: "pricing", href: "/pricing", nav: "nav.pricing", icon: "card",
    Page: PricingPage, designH: 1000 },
  { id: "settings", href: "/settings", nav: "nav.settings", icon: "gear",
    Page: SettingsPage, designH: 1000 },
  { id: "guide", href: "/guide", nav: "nav.guide", icon: "book",
    Page: GuidePage, designH: 1000 },
];

const WHEEL_LOCK_MS = 750;
/** 이보다 작게는 줄이지 않는다 — 글자가 못 읽을 만큼 작아진다. */
const MIN_ZOOM = 0.64;
/** 좁은 상자(폰): 아래 조작 줄 높이. */
const BAR = 64;

function tabOf(path: string): number {
  return TABS.findIndex((t) => t.href === path);
}

/** 이 주소에서 덱이 서는가 — 앱 머리가 자기를 숨길지 여기에 묻는다. */
export function isDeckPath(path: string): boolean {
  return tabOf(path) >= 0;
}

type Slot = "queued" | "next" | "center" | "prev" | "gone";
/** dx · dy: 가운데에서 무대 폭 · 높이의 몇 배만큼 떨어졌나. */
type Pos = { dx: number; dy: number; scale: number; rotate: number; opacity: number;
             z: number };

/** 카드 자리. 옆 자리(next · prev)는 보이지 않는다 — 넘어가는 길목일 뿐이다.
 *  들어오는 카드는 오른쪽 위에서 커지며, 나가는 카드는 왼쪽 아래로 줄며 빠진다. */
const SLOTS: Record<"wide" | "narrow", Record<Slot, Pos>> = {
  wide: {
    queued: { dx: 0.54, dy: -0.56, scale: 0.1, rotate: 16, opacity: 0, z: 10 },
    next: { dx: 0.46, dy: -0.38, scale: 0.2, rotate: 10, opacity: 0, z: 20 },
    center: { dx: 0, dy: 0, scale: 1, rotate: 0, opacity: 1, z: 38 },
    prev: { dx: -0.46, dy: 0.4, scale: 0.2, rotate: -10, opacity: 0, z: 30 },
    gone: { dx: -0.58, dy: 0.64, scale: 0.12, rotate: -16, opacity: 0, z: 10 },
  },
  narrow: {
    queued: { dx: 0.58, dy: -0.54, scale: 0.1, rotate: 16, opacity: 0, z: 10 },
    next: { dx: 0.44, dy: -0.4, scale: 0.2, rotate: 10, opacity: 0, z: 20 },
    center: { dx: 0, dy: 0, scale: 1, rotate: 0, opacity: 1, z: 38 },
    prev: { dx: -0.44, dy: 0.38, scale: 0.2, rotate: -10, opacity: 0, z: 30 },
    gone: { dx: -0.6, dy: 0.62, scale: 0.12, rotate: -16, opacity: 0, z: 10 },
  },
};

function slotOf(rel: number): Slot {
  if (rel === 0) return "center";
  if (rel === 1) return "next";
  if (rel >= 2) return "queued";
  if (rel === -1) return "prev";
  return "gone";
}

/** 카드 크기와 무대 크기(px). */
type Box = { w: number; h: number; stageW: number; stageH: number };

export function TabDeck({ children }: { children: ReactNode }) {
  const path = usePathname();
  if (tabOf(path) < 0) return <>{children}</>;
  return <Deck />;
}

function Deck() {
  const { t } = useLang();
  const path = usePathname();
  const pathIdx = tabOf(path);
  const n = TABS.length;

  const [active, setActive] = useState(Math.max(0, pathIdx));
  const [seen, setSeen] = useState(pathIdx);
  const [dir, setDir] = useState<1 | -1>(1);
  const [stageSize, setStageSize] = useState<{ w: number; h: number } | null>(null);
  const [mounted, setMounted] = useState<ReadonlySet<number>>(
    () => new Set([Math.max(0, pathIdx)]));
  const stage = useRef<HTMLElement>(null);
  const wheelAt = useRef(0);
  const panFromCard = useRef(false);

  // 주소가 밖에서 바뀌었으면(뒤로 가기 등) 그 탭을 가운데로 — 렌더 중에 맞춘다.
  if (pathIdx !== seen) {
    setSeen(pathIdx);
    if (pathIdx >= 0 && pathIdx !== active) {
      setDir(pathIdx > active ? 1 : -1);
      setActive(pathIdx);
    }
  }

  // 가운데로 온 카드는 띄운다(처음 가는 먼 탭). 한 번 띄우면 내리지 않는다.
  if (!mounted.has(active)) setMounted(new Set(mounted).add(active));

  // 한가할 때 양옆 이웃을 미리 띄워 둔다 — 넘기는 순간 화면을 처음 그리면 끊긴다.
  useEffect(() => {
    const want = [active - 1, active + 1].filter((i) => i >= 0 && i < TABS.length);
    if (want.every((i) => mounted.has(i))) return;
    const add = () => setMounted((m) => {
      const next = new Set(m);
      want.forEach((i) => next.add(i));
      return next;
    });
    // Safari 는 requestIdleCallback 이 없다.
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(add, { timeout: 2500 });
      return () => window.cancelIdleCallback(id);
    }
    const id = window.setTimeout(add, 1200);
    return () => window.clearTimeout(id);
  }, [active, mounted]);

  const go = useCallback((i: number) => {
    if (i < 0 || i >= TABS.length || i === active) return;
    setDir(i > active ? 1 : -1);
    setActive(i);
    // 페이지를 옮기지 않고 주소만. 설명 탭의 장(#staff 등)은 그 탭이 다시 쓴다.
    window.history.replaceState(null, "", TABS[i].href);
  }, [active]);

  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) =>
      setStageSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 탭 주소로 가는 링크는 페이지를 옮기지 않고 카드를 돌린다. Next 의 Link 는
  // 이미 막힌(defaultPrevented) 클릭을 따라가지 않는다 — 그래서 캡처에서 막는다.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey ||
          e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]");
      if (!(a instanceof HTMLAnchorElement) || a.target === "_blank" ||
          a.origin !== window.location.origin) return;
      const i = tabOf(a.pathname);
      if (i < 0) return;
      e.preventDefault();
      go(i);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [go]);

  const inCard = (el: EventTarget | null) =>
    el instanceof Element && !!el.closest("[data-deck-center]");

  const onWheel = (e: WheelEvent) => {
    if (inCard(e.target)) return;
    const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    if (Math.abs(d) < 18) return;
    const now = Date.now();
    if (now - wheelAt.current < WHEEL_LOCK_MS) return;
    wheelAt.current = now;
    go(active + (d > 0 ? 1 : -1));
  };

  const narrow = (stageSize?.w ?? 1200) < 672;
  // 넓으면 위아래 12px 씩만 남기고 양옆 90%. 좁으면 양옆 8px, 아래는 조작 줄.
  const box: Box | null = stageSize && (() => {
    const w = narrow ? stageSize.w - 16 : stageSize.w * 0.9;
    const h = narrow ? stageSize.h - BAR - 8 : stageSize.h - 24;
    return { w, h, stageW: stageSize.w, stageH: stageSize.h };
  })();
  const s = TABS[active];
  const slots = SLOTS[narrow ? "narrow" : "wide"];
  const names = TABS.map((x) => t(x.nav));

  return (
    <MotionConfig reducedMotion="user">
      <div className="h-full p-2" style={{ background: "var(--bg)" }}>
        <motion.section
          ref={stage}
          className="relative h-full overflow-hidden rounded-[24px] text-white"
          style={{ containerType: "size", background: GALAXY_DEEP }}
          onWheel={onWheel}
          onPointerDownCapture={(e) => {
            panFromCard.current = inCard(e.target);
          }}
          onPanEnd={(_, info) => {
            if (panFromCard.current) return;
            const { x, y } = info.offset;
            const d = Math.abs(x) > Math.abs(y) ? -x : -y;
            if (Math.abs(d) >= 50) go(active + (d > 0 ? 1 : -1));
          }}
          aria-roledescription="carousel"
          aria-label="AI COMPANY"
        >
          <Galaxy />
          <Backdrop s={s} dir={dir} />

          {box && TABS.map((tab, i) => {
            const slot = slotOf(i - active);
            return (
              <Card key={tab.id} tab={tab} slot={slot} pos={slots[slot]} dir={dir} box={box}
                narrow={narrow} live={mounted.has(i)} />
            );
          })}

          <LayoutGroup id="deck">
            {narrow ? (
              <BottomBar active={active} go={go} deep={GALAXY_DEEP} names={names} n={n}
                prevLabel={t("deck.prev")} nextLabel={t("deck.next")} />
            ) : (
              <>
                <LeftRail active={active} go={go} deep={GALAXY_DEEP} names={names} n={n} />
                <RightRail active={active} go={go} n={n} hint={t("deck.hint")}
                  prevLabel={t("deck.prev")} nextLabel={t("deck.next")} />
              </>
            )}
          </LayoutGroup>
        </motion.section>
      </div>
    </MotionConfig>
  );
}

/* ─────────────────────────────────────────────────────────────── */

/** 탭 카드 한 장. 요소는 그대로 두고 자리만 바꾼다 — 화면 상태가 남는다. */
function Card({
  tab, slot, pos, dir, box, narrow, live,
}: {
  tab: (typeof TABS)[number];
  slot: Slot;
  pos: Pos;
  dir: 1 | -1;
  box: Box;
  narrow: boolean;
  /** 화면을 띄웠나. 아직이면 빈 틀만 — 가운데로 오면 덱이 띄운다. */
  live: boolean;
}) {
  const center = slot === "center";
  const order: Slot[] = dir === 1
    ? ["gone", "prev", "center", "next", "queued"]
    : ["queued", "next", "center", "prev", "gone"];
  const Page = tab.Page;
  // 폰은 원래 한 줄씩 쌓아 스크롤하는 화면이다. 거기서까지 줄이면 글자만 작아진다.
  const zoom = Math.min(1, Math.max(narrow ? 0.9 : MIN_ZOOM, box.h / tab.designH));
  // 좁으면 카드를 아래 조작 줄만큼 위로 올린다.
  const lift = narrow ? (BAR - 8) / 2 : 0;

  return (
    <motion.div
      data-deck-center={center || undefined}
      aria-hidden={center ? undefined : true}
      className="absolute left-1/2 top-1/2"
      style={{
        width: box.w,
        height: box.h,
        // 가운데를 translate(-50%) 로 맞추면 반 픽셀에 걸려 글자가 흐려진다.
        // 여백으로 맞추면 가운데 카드의 transform 은 비어 있게 된다.
        marginLeft: Math.round(-box.w / 2),
        marginTop: Math.round(-box.h / 2 - lift),
        zIndex: pos.z,
      }}
      initial={false}
      animate={{
        x: pos.dx * box.stageW, y: pos.dy * box.stageH,
        scale: pos.scale, rotate: pos.rotate, opacity: pos.opacity,
        // 가운데로 오는 카드는 바로 보이게, 빠지는 카드는 다 빠진 뒤 그리지 않게.
        visibility: "visible",
        transitionEnd: center ? undefined : { visibility: "hidden" },
      }}
      transition={{
        type: "spring", stiffness: 85, damping: 18, mass: 1,
        delay: order.indexOf(slot) * 0.05,
        // 옆 자리는 보이지 않는 길목이다. 빠질 때는 빨리 흐려지고, 들어올 때는
        // 자리를 잡는 동안 서서히 나타난다.
        opacity: { duration: center ? 0.45 : 0.35, delay: center ? 0.1 : 0 },
      }}
    >
      <div
        inert={!center}
        className="h-full w-full overflow-hidden rounded-2xl border border-white/15
          text-[color:var(--fg)] shadow-[0_40px_90px_-30px_rgba(0,0,0,0.8)]"
        style={{ background: "var(--bg)" }}
      >
        <div
          style={{
            width: box.w / zoom,
            height: box.h / zoom,
            zoom,
          }}
        >
          {live && (
            <StackCtx.Provider value={{ inCard: true, active: center }}>
              <Page />
            </StackCtx.Provider>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/** 탭 알약 — 세로(왼쪽 여백) 또는 가로(폰의 아래 줄). */
function TabPills({
  active, go, deep, names, vertical,
}: {
  active: number;
  go: (i: number) => void;
  deep: string;
  names: string[];
  vertical: boolean;
}) {
  return (
    <nav className={`flex shrink-0 items-center gap-1 rounded-full bg-black/25 p-1
      backdrop-blur-md ${vertical ? "flex-col" : ""}`}>
      {TABS.map((x, i) => (
        <button
          key={x.id}
          type="button"
          onClick={() => go(i)}
          aria-current={i === active ? "page" : undefined}
          aria-label={names[i]}
          title={names[i]}
          className="relative grid size-10 place-items-center rounded-full transition-colors"
          style={{ color: i === active ? deep : "rgba(255,255,255,0.85)" }}
        >
          {i === active && (
            <motion.span
              layoutId="deck-pill"
              className="absolute inset-0 rounded-full bg-white"
              transition={{ type: "spring", stiffness: 380, damping: 32 }}
            />
          )}
          <Icon name={x.icon} size={18} className="relative" />
        </button>
      ))}
    </nav>
  );
}

function Counter({ active, n }: { active: number; n: number }) {
  return (
    <span className="shrink-0 whitespace-nowrap text-[11px] tabular-nums">
      <span className="font-semibold">{String(active + 1).padStart(2, "0")}</span>
      <span className="text-white/55">/{String(n).padStart(2, "0")}</span>
    </span>
  );
}

const ROUND =
  "grid size-10 place-items-center rounded-full border border-white/45 text-white/90" +
  " transition-colors enabled:hover:bg-white/20 disabled:opacity-35";

/** 왼쪽 여백: 탭 네 개 · 몇 번째인지. */
function LeftRail({
  active, go, deep, names, n,
}: {
  active: number;
  go: (i: number) => void;
  deep: string;
  names: string[];
  n: number;
}) {
  return (
    <div className="absolute inset-y-0 left-0 z-50 flex w-[5cqw] select-none flex-col
      items-center justify-center gap-3">
      <TabPills active={active} go={go} deep={deep} names={names} vertical />
      <Counter active={active} n={n} />
    </div>
  );
}

/** 오른쪽 여백: 스크롤 안내 · 이전 · 다음 · 언어 · 사용자. */
function RightRail({
  active, go, n, hint, prevLabel, nextLabel,
}: {
  active: number;
  go: (i: number) => void;
  n: number;
  hint: string;
  prevLabel: string;
  nextLabel: string;
}) {
  return (
    <div className="absolute inset-y-0 right-0 z-50 flex w-[5cqw] select-none flex-col
      items-center justify-between py-4">
      <span className="relative mt-1 h-7 w-[18px] rounded-full border border-white/70"
        title={hint} aria-label={hint} role="img">
        <span className="anim-hint absolute left-1/2 top-1.5 h-1.5 w-0.5 -translate-x-1/2
          rounded-full bg-white" />
      </span>
      <div className="flex flex-col gap-2">
        <motion.button type="button" className={ROUND} onClick={() => go(active - 1)}
          disabled={active === 0} aria-label={prevLabel} whileTap={{ scale: 0.9, y: -3 }}>
          <span aria-hidden className="text-lg leading-none">↑</span>
        </motion.button>
        <motion.button type="button" className={ROUND} onClick={() => go(active + 1)}
          disabled={active === n - 1} aria-label={nextLabel} whileTap={{ scale: 0.9, y: 3 }}>
          <span aria-hidden className="text-lg leading-none">↓</span>
        </motion.button>
      </div>
      <div className="flex flex-col items-center gap-2">
        <LangSwitch compact vertical />
        <UserMenu compact />
      </div>
    </div>
  );
}

/** 폰: 여백이 없으니 탭 · 이전/다음 · 언어 · 사용자를 아래 한 줄에. */
function BottomBar({
  active, go, deep, names, n, prevLabel, nextLabel,
}: {
  active: number;
  go: (i: number) => void;
  deep: string;
  names: string[];
  n: number;
  prevLabel: string;
  nextLabel: string;
}) {
  return (
    <div className="absolute inset-x-0 bottom-0 z-50 flex select-none items-center gap-1.5
      px-2"
      style={{ height: BAR }}>
      <TabPills active={active} go={go} deep={deep} names={names} vertical={false} />
      <motion.button type="button" className={`${ROUND} ml-auto hidden min-[400px]:grid`}
        onClick={() => go(active - 1)} disabled={active === 0} aria-label={prevLabel}>
        <span aria-hidden className="leading-none">←</span>
      </motion.button>
      <Counter active={active} n={n} />
      <motion.button type="button" className={`${ROUND} hidden min-[400px]:grid`}
        onClick={() => go(active + 1)} disabled={active === n - 1} aria-label={nextLabel}>
        <span aria-hidden className="leading-none">→</span>
      </motion.button>
      <div className="ml-auto flex shrink-0 items-center gap-1.5 whitespace-nowrap
        min-[400px]:ml-0">
        <LangSwitch compact />
        <UserMenu compact />
      </div>
    </div>
  );
}
