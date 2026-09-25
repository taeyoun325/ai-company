"use client";

/**
 * 끌면 따라오고, 놓으면 튕겨 돌아오는 조각 (DAY 26 · 설명 탭).
 *
 * ## 두 라이브러리가 나눠 맡는다
 *
 * - **motion.dev** (`motion/react`) — 손을 따라가는 쪽. 끌기 · 끄는 방향으로
 *   기울기(`x` → `rotate`) · 놓으면 스프링으로 제자리(`dragSnapToOrigin`) ·
 *   다른 조각이 끌리는 동안 옆 조각이 한 발 물러서기.
 * - **anime.js** (`lib/motion.ts` 의 `burst`) — 놓는 순간 그 자리에서 점이 튄다.
 *
 * 손이 하는 일은 motion 이, 한 번 터지고 끝나는 일은 anime.js 가 한다. 둘이
 * 같은 요소의 transform 을 두고 다투지 않게 — 등장 애니메이션(anime.js)은
 * 바깥 요소가, 끌기(motion)는 안쪽 요소가 맡는다.
 *
 * ## 끌 수 없는 때
 *
 * - **터치 화면.** 손가락으로 카드를 누르면 페이지가 스크롤돼야 한다. 카드가
 *   끌리면 카드로 가득한 이 페이지는 스크롤할 수 없게 된다.
 * - **움직임을 줄인 사람.** 아무것도 튀지 않는다.
 */
import { motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import {
  createContext, useContext, useId, useMemo, useState, type ReactNode,
} from "react";

import { useMedia } from "@/lib/media";
import { burst } from "@/lib/motion";

type Group = { active: string | null; set: (id: string | null) => void };
const FlingGroup = createContext<Group | null>(null);

/** 이 안의 조각 하나를 끄는 동안 나머지가 물러선다. */
export function FlingArea({ children }: { children: ReactNode }) {
  const [active, set] = useState<string | null>(null);
  const value = useMemo(() => ({ active, set }), [active]);
  return <FlingGroup.Provider value={value}>{children}</FlingGroup.Provider>;
}

/** 지금 끌 수 있는가 — 마우스·펜이고, 움직임을 줄이지 않았을 때. */
export function useCanFling(): boolean {
  const fine = useMedia("(pointer: fine)", true);
  const reduced = useReducedMotion();
  return fine && !reduced;
}

type Tag = "li" | "div";

export function Fling({
  as = "div", color = "var(--accent)", className = "", children, reveal = true,
}: {
  as?: Tag;
  /** 놓을 때 튀는 점의 색. 직원·상태의 색을 그대로 쓴다. */
  color?: string;
  className?: string;
  children: ReactNode;
  /** 바깥 요소에 등장 애니메이션 표시(`data-reveal`)를 단다. */
  reveal?: boolean;
}) {
  const id = useId();
  const group = useContext(FlingGroup);
  const can = useCanFling();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  // 오른쪽으로 끌면 오른쪽으로, 왼쪽이면 왼쪽으로 기운다. 멀리 끌수록 더.
  const rotate = useTransform(x, [-180, 0, 180], [-12, 0, 12]);
  const [held, setHeld] = useState(false);
  const other = !!group?.active && group.active !== id;
  const Outer = as;

  return (
    <Outer data-reveal={reveal ? "" : undefined}
      className="relative" style={{ zIndex: held ? 40 : undefined }}>
      <motion.div
        drag={can}
        dragSnapToOrigin
        dragElastic={0.6}
        dragTransition={{ bounceStiffness: 380, bounceDamping: 16 }}
        whileDrag={{ scale: 1.08, boxShadow: "0 22px 48px rgba(0,0,0,0.45)" }}
        // 올라오는 느낌은 y 가 아니라 크기로 — y 는 끌기가 쓰는 값이라, 둘이
        // 같은 값을 두고 다투면 놓은 뒤 제자리로 다 못 돌아온다(DAY 26 시험).
        whileHover={can ? { scale: 1.025 } : undefined}
        animate={{ scale: other ? 0.96 : 1, opacity: other ? 0.6 : 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 24 }}
        onDragStart={() => {
          setHeld(true);
          group?.set(id);
        }}
        onDragEnd={(event) => {
          setHeld(false);
          group?.set(null);
          const p = event as PointerEvent;
          if (typeof p.clientX === "number") burst(p.clientX, p.clientY, color);
        }}
        style={{ x, y, rotate }}
        className={`h-full ${can ? "cursor-grab active:cursor-grabbing" : ""} ${className}`}>
        {children}
      </motion.div>
    </Outer>
  );
}

/**
 * 제목의 낱말 하나하나를 끌 수 있게 한다. 줄바꿈은 **낱말 단위**로 남긴다 —
 * 글자 단위로 쪼개면 한글이 글자마다 줄을 바꾼다(DAY 20 에 겪었다).
 */
export function FlingWords({ text }: { text: string }) {
  const can = useCanFling();
  const words = text.split(" ").filter(Boolean);
  return (
    <>
      {words.map((w, i) => (
        <span key={`${i}-${w}`}>
          <span className="guide-word inline-block" data-reveal>
            <motion.span
              className={`inline-block ${can ? "cursor-grab active:cursor-grabbing" : ""}`}
              drag={can}
              dragSnapToOrigin
              dragElastic={0.9}
              dragTransition={{ bounceStiffness: 500, bounceDamping: 14 }}
              whileDrag={{ scale: 1.2, color: "var(--accent)" }}
              whileHover={can ? { scale: 1.08, rotate: i % 2 ? 3 : -3 } : undefined}>
              {w}
            </motion.span>
          </span>
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </>
  );
}
