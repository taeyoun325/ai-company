"use client";

/**
 * 사무실 — 원탁에 둘러앉은 팀 (DAY 24 개편).
 *
 * ## 왜 도트 그림을 걷어냈나
 *
 * 이전 판은 위에서 내려다본 8-bit 게임 방이었다. 가구·바닥 타일까지
 * 손으로 채운 정성은 있었지만, 결국 "장난감"으로 읽혔다 — 돈을 받는
 * 제품의 핵심 화면이 게임 캐릭터 선택 창처럼 보이면 안 된다.
 *
 * 자리 배치의 **뜻**은 그대로 가져온다: 다섯 명이 원탁에 둘러앉는다.
 * 개인 책상이 아니라 원탁인 이유는 여전히 유효하다 — 이 제품이 파는 것은
 * 각자 일하는 그림이 아니라 기획→구현→검증→재작업으로 돌아가는
 * **협업**이고, 원형 배치가 그 관계를 보여준다.
 *
 * ## 무엇으로 바꿨나
 *
 * - 자리 하나하나가 **진짜 `<button>`**이다. 예전에는 투명 SVG 사각형에
 *   `role="button"`을 얹어 흉내 냈는데, 스크린리더·키보드 양쪽에서
 *   진짜 버튼보다 나을 것이 없었다.
 * - 제공자 표식은 도트 로고 대신 이 제품이 이미 쓰는 아이콘 세트를
 *   재사용한다(`icons.tsx`) — 새 그림 언어를 만들지 않는다.
 * - 움직임은 motion.dev 로 만든다: 등장은 줄줄이 튀어 오르고, 일하는
 *   자리는 부드러운 스프링으로 맥박이 돈다. `prefers-reduced-motion`
 *   에서는 전부 끄고 최종 상태만 보여준다 — 이 파일 바깥의 anime.js
 *   규칙(lib/motion.ts)과 같은 원칙이다.
 *
 * ## 살아 움직이는 것과 장식의 차이는 그대로
 *
 * 일하는 자리만 맥박이 돌고 점 세 개가 오간다. 나머지는 가만히 있는다.
 * 빈 자리는 점선 테두리만 남는다 — 내보낸 직원이 어디 갔는지 굳이
 * 설명하지 않아도 된다.
 */
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";
import { type Key, useLang } from "@/lib/i18n";
import type { Employee } from "@/lib/types";
import { Icon, iconOfAgent } from "./icons";
import { MockBadge } from "./ui";

const PROVIDER_LABEL: Record<string, string> = {
  claude: "Claude",
  gemini: "Gemini",
  openai: "GPT",
};

/** 자리 좌표 (%). 12시 방향부터 시계 방향으로 고르게 돌린다.
 *  가로로 넓은 컨테이너라 rx > ry 인 타원을 쓴다. */
function seatPos(i: number, total: number) {
  const angle = ((-90 + (360 / total) * i) * Math.PI) / 180;
  const rx = 34;
  const ry = 32;
  return {
    left: `${50 + rx * Math.cos(angle)}%`,
    top: `${50 + ry * Math.sin(angle)}%`,
  };
}

/** 일하는 자리 위의 점 세 개. 타자하는 손을 대신한다. */
function TypingDots({ color }: { color: string }) {
  return (
    <span className="flex items-center gap-0.5" aria-hidden>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="size-1 rounded-full"
          style={{ background: color }}
          animate={{ y: [0, -3, 0], opacity: [0.5, 1, 0.5] }}
          transition={{
            duration: 0.9, repeat: Infinity, delay: i * 0.15,
            ease: "easeInOut",
          }}
        />
      ))}
    </span>
  );
}

function Seat({
  e, pos, empty, isWorking, picked, hovered, still, onPick, onHover, t,
}: {
  e: Employee;
  pos: { left: string; top: string };
  empty: boolean;
  isWorking: boolean;
  picked: boolean;
  hovered: boolean;
  still: boolean;
  onPick?: (id: string) => void;
  onHover: (id: string | null) => void;
  t: (k: Key, v?: Record<string, string | number>) => string;
}) {
  const color = `var(--${e.id}, var(--accent))`;
  const active = picked || hovered;

  return (
    <motion.button
      type="button"
      disabled={!onPick}
      style={{ left: pos.left, top: pos.top, ["--c" as string]: color }}
      className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col
        items-center gap-1 outline-none"
      initial={still ? false : { opacity: 0, scale: 0.5 }}
      animate={{ opacity: empty ? 0.55 : 1, scale: 1 }}
      transition={still ? { duration: 0 } : {
        type: "spring", stiffness: 260, damping: 18, delay: seatDelay(e.id),
      }}
      whileHover={onPick && !still ? { scale: 1.07 } : undefined}
      whileTap={onPick && !still ? { scale: 0.95 } : undefined}
      onClick={() => onPick?.(e.id)}
      onMouseEnter={() => onHover(e.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(e.id)}
      onBlur={() => onHover(null)}
      aria-pressed={onPick ? picked : undefined}
      aria-label={`${e.name} · ${e.role} · ${
        empty ? t("staff.empty") : isWorking ? t("office.working") : t("office.idle")
      }`}
    >
      <span className="relative grid place-items-center">
        {/* 일하는 자리의 맥박. 스프링이 아니라 반복 트윈 — 심장박동처럼
            일정해야 "지금도 도는 중"으로 읽힌다. */}
        {isWorking && !still && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ background: color }}
            animate={{ scale: [1, 1.6], opacity: [0.35, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
            aria-hidden
          />
        )}
        <span
          className="relative grid size-11 place-items-center rounded-full border-2
            transition-shadow"
          style={{
            // 캔버스가 테마와 무관하게 항상 어두우므로, 자리도 고정된
            // 밝기로 그린다 — 라이트 모드에서 `bg-panel2`(밝은 회색)를
            // 쓰면 어두운 캔버스 위에서 흰 원반처럼 붕 뜬다.
            background: "rgba(255,255,255,0.07)",
            borderColor: empty ? "rgba(255,255,255,0.28)" : color,
            borderStyle: empty ? "dashed" : "solid",
            boxShadow: active && !empty
              ? `0 0 0 3px color-mix(in srgb, ${color} 30%, transparent)`
              : isWorking
                ? `0 0 0 2px color-mix(in srgb, ${color} 45%, transparent)`
                : "none",
            color,
          }}
        >
          {empty ? (
            <Icon name="person" size={18} className="opacity-50" />
          ) : (
            <Icon name={iconOfAgent(e.id)} size={20} />
          )}
        </span>
      </span>

      <span className="flex flex-col items-center gap-0.5">
        <span
          className="max-w-[76px] truncate text-[11px] font-semibold"
          style={{ color: empty ? "rgba(255,255,255,0.45)" : "#eef0f7" }}
        >
          {e.name}
        </span>
        <span className="h-3">
          {isWorking && !empty && <TypingDots color={color} />}
        </span>
      </span>
    </motion.button>
  );
}

/** 이름에서 뽑은 고정 지연값. 자리마다 조금씩 다르게 등장하되, 렌더마다
 *  달라지면 안 되므로 무작위 대신 이름 길이를 쓴다. */
function seatDelay(id: string): number {
  return (id.length % 5) * 0.05;
}

function PhaseChip({ phase, detail }: { phase?: string; detail?: string }) {
  if (!phase) return null;
  const label = detail ? `${phase} · ${detail}` : phase;
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={label}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.22 }}
        className="max-w-[220px] truncate rounded-full border px-3 py-1
          text-[11px] font-semibold backdrop-blur-sm"
        style={{
          color: "var(--accent)",
          background: "rgba(10,11,17,0.72)",
          borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
        }}
      >
        {label}
      </motion.div>
    </AnimatePresence>
  );
}

export function PixelOffice({
  employees, working, onPick, picked, className = "", phase, detail,
}: {
  employees: Employee[];
  /** 지금 일하는 직원 id. */
  working: (id: string) => boolean;
  onPick?: (id: string) => void;
  picked?: string | null;
  className?: string;
  /** 지금 어느 단계인가. 원탁 가운데에 놓는다. */
  phase?: string;
  detail?: string;
}) {
  const { t } = useLang();
  const [hover, setHover] = useState<string | null>(null);
  const still = prefersReducedMotion();
  const open = employees.find((e) => e.id === (picked ?? hover));
  const seats = employees.slice(0, 5);

  return (
    <div className={`glass glass-lit overflow-hidden ${className}`}>
      <div
        role="group"
        aria-label={t("office.alt")}
        className="relative aspect-[16/10] w-full overflow-hidden"
      >
        {/* 짙은 캔버스. **테마와 무관하게 항상 어둡다** — 지도·에디터
            처럼, 사람이 바라보는 시각화 자체는 밝은 화면 안에서도 어두운
            자리가 오히려 자연스럽다(레퍼런스 영상의 톤). `var(--bg)` 를
            쓰면 라이트 모드에서 밝은 회색으로 뒤집혀 글로우가 묻힌다. */}
        <div
          className="absolute inset-0"
          style={{
            background: `
              radial-gradient(60% 55% at 50% 42%,
                color-mix(in srgb, var(--accent) 22%, transparent), transparent 70%),
              radial-gradient(40% 40% at 85% 90%,
                color-mix(in srgb, var(--accent-2) 16%, transparent), transparent 70%),
              radial-gradient(120% 100% at 50% 0%, #14161f, #08090d)`,
          }}
          aria-hidden
        />
        <div
          className="absolute inset-0 opacity-[0.25]"
          style={{
            backgroundImage:
              "radial-gradient(rgba(255,255,255,0.5) 1px, transparent 1px)",
            backgroundSize: "16px 16px",
          }}
          aria-hidden
        />

        {/* 원탁. `rounded-full` 은 가로세로가 다른 상자에서 알약 모양이
            된다 — 타원을 보려면 반지름을 퍼센트로 줘야 한다. */}
        <div
          className="absolute left-1/2 top-1/2 grid h-[46%] w-[54%] -translate-x-1/2
            -translate-y-1/2 place-items-center"
          style={{
            borderRadius: "50%",
            background: "rgba(255,255,255,0.045)",
            border: "1px solid rgba(255,255,255,0.12)",
            boxShadow: "inset 0 0 24px rgba(0,0,0,0.35)",
          }}
          aria-hidden
        >
          <div className="px-4">
            <PhaseChip phase={phase} detail={detail} />
          </div>
        </div>

        {seats.map((e) => {
          const i = seats.indexOf(e);
          const pos = seatPos(i, seats.length);
          const empty = e.active === false;
          const isWorking = !empty && working(e.id);
          return (
            <Seat
              key={e.id}
              e={e}
              pos={pos}
              empty={empty}
              isWorking={isWorking}
              picked={picked === e.id}
              hovered={hover === e.id}
              still={still}
              onPick={onPick}
              onHover={setHover}
              t={t}
            />
          );
        })}
      </div>

      {/* 단계가 바뀌는 것은 그림으로만 알 수 있었다. 화면을 못 보는
          사람에게 "지금 무슨 일이 일어나는지"를 말해준다. */}
      <p className="sr-only" aria-live="polite">
        {phase ? `${phase}${detail ? ` · ${detail}` : ""}` : ""}
      </p>

      <div className="flex min-h-[38px] items-center gap-2 border-t border-line
        px-3 py-2 text-[11px]">
        {open ? (
          <>
            <span className="size-2 rounded-full"
                  style={{ background: `var(--${open.id}, var(--accent))` }} />
            <strong className="text-fg">{open.name}</strong>
            <span className="text-muted">{open.role}</span>
            <span className="text-dim">
              {PROVIDER_LABEL[open.provider] ?? open.provider} · {open.model}
            </span>
            <span className="ml-auto flex items-center gap-1.5"
                  style={{ color: working(open.id)
                    ? `var(--${open.id}, var(--accent))` : "var(--dim)" }}>
              {open.active === false
                ? t("staff.empty")
                : working(open.id)
                  ? t("office.working")
                  : t("office.idle")}
              {open.mock && <MockBadge title={t("mock.badge")} />}
            </span>
          </>
        ) : (
          <span className="text-dim">{t("office.hint")}</span>
        )}
      </div>
    </div>
  );
}
