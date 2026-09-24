"use client";

/**
 * 사무실 — 핸드오프 그래프 (DAY 25 개편).
 *
 * ## 왜 원탁에서 그래프로 바꿨나
 *
 * 원탁은 "지금 누가 있는가"를 보여줬다. 이 제품이 실제로 파는 것은
 * **일이 사람 사이로 넘어가는 과정**이다(기획→구현→검증→재작업). 그
 * 흐름은 앉은 자리로는 안 보이고, 로그를 줄줄이 읽어야만 알 수 있었다.
 *
 * 백엔드가 이미 `bus.handoff()` 로 그 근거를 구조화해서 내보내고
 * 있다(app/bus.py) — message_to_team 한 줄로 뭉개지던 self_check ·
 * findings · met/unmet 같은 값들이다. 화면이 그걸 안 쓰면 만들어 둔
 * 데이터가 로그에 묻힌다.
 *
 * ## 그래프에 안 그리는 것
 *
 * WRITE_TESTS → IMPLEMENT, FINALIZE → SYSTEM 처럼 상대가 특정 직원이
 * 아닌 인계는 선을 안 그린다. 있지도 않은 직원에게 선을 잇는 것보다,
 * 목록에만 적고 그래프는 조용한 편이 맞다.
 */
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";
import { type Key, useLang } from "@/lib/i18n";
import type { BusEvent, Employee, Roster } from "@/lib/types";
import { Icon, iconOfAgent } from "./icons";

function nodeAt(i: number, total: number) {
  const angle = ((-90 + (360 / total) * i) * Math.PI) / 180;
  const rx = 37, ry = 34;
  return { x: 50 + rx * Math.cos(angle), y: 50 + ry * Math.sin(angle) };
}

/** 두 점을 잇는 곡선. 중심 쪽으로 살짝 당긴 제어점 하나만 쓴다 —
 *  직선은 원탁의 반복이고, 과한 곡률은 관계가 아니라 장식으로 읽힌다. */
function edgePath(a: { x: number; y: number }, b: { x: number; y: number }) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const cx = 50 + (mx - 50) * 0.55, cy = 50 + (my - 50) * 0.55;
  return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
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

/** handoff 이벤트 한 줄 요약. 단계마다 실려 오는 필드가 달라
 *  (app/orchestrator/engine.py), 여기서 그 필드를 읽어 사람이 읽는
 *  한 문장으로 접는다. */
function summarize(h: BusEvent, t: (k: Key, v?: Record<string, string | number>) => string) {
  switch (h.phase) {
    case "PLAN":
      return t("handoff.plan", { n: h.task_titles?.length ?? 0 });
    case "WRITE_TESTS":
      return t("handoff.writeTests", { n: h.covered?.length ?? 0 });
    case "IMPLEMENT":
      return h.summary || t("handoff.implement");
    case "REVIEW":
      return h.verdict === "pass"
        ? t("handoff.reviewPass")
        : t("handoff.reviewFail", { n: h.findings?.length ?? 0 });
    case "FINALIZE":
      return t("handoff.finalize", { n: h.met?.length ?? 0 });
    default:
      return h.phase ?? "";
  }
}

function nodeLabel(id: string | undefined, roster: Roster, t: (k: Key) => string) {
  if (!id) return "";
  if (id === "SYSTEM") return t("handoff.system");
  return roster[id]?.name ?? id;
}

export function HandoffGraph({
  employees, working, onPick, picked, className = "", phase, detail,
  events = [], roster = {},
}: {
  employees: Employee[];
  working: (id: string) => boolean;
  onPick?: (id: string) => void;
  picked?: string | null;
  className?: string;
  phase?: string;
  detail?: string;
  /** 최근 handoff 이벤트. 그래프 선·펄스·인계 목록에 쓴다. */
  events?: BusEvent[];
  roster?: Roster;
}) {
  const { t } = useLang();
  const [hover, setHover] = useState<string | null>(null);
  const still = prefersReducedMotion();
  const seats = employees.slice(0, 5);
  const ids = new Set(seats.map((e) => e.id));
  const pos = new Map(seats.map((e, i) => [e.id, nodeAt(i, seats.length)]));

  const handoffs = useMemo(
    () => events.filter((e) => e.type === "handoff").slice(-30).reverse(),
    [events],
  );
  // 그래프에 그릴 수 있는 건 양쪽 다 실제 자리인 경우뿐이다.
  const drawable = handoffs.filter((h) => h.from && h.to
    && ids.has(h.from) && ids.has(h.to));
  const latest = drawable[0];
  const recentPairs = new Map<string, number>();
  drawable.slice(0, 6).forEach((h, i) => {
    const key = [h.from, h.to].sort().join("|");
    if (!recentPairs.has(key)) recentPairs.set(key, i);
  });

  return (
    <div className={`glass glass-lit overflow-hidden ${className}`}>
      <div
        role="group"
        aria-label={t("office.alt")}
        className="relative aspect-[16/10] w-full overflow-hidden"
      >
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

        {/* 선 — 자리 좌표계와 같은 0~100 좌표를 쓴다. */}
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          aria-hidden
        >
          {[...recentPairs.entries()].map(([key, rank]) => {
            const [aId, bId] = key.split("|");
            const a = pos.get(aId), b = pos.get(bId);
            if (!a || !b) return null;
            return (
              <path
                key={key}
                d={edgePath(a, b)}
                stroke="rgba(255,255,255,0.16)"
                strokeWidth={0.5}
                fill="none"
                opacity={1 - rank * 0.14}
              />
            );
          })}
          {latest && !still && pos.get(latest.from!) && pos.get(latest.to!) && (
            <motion.circle
              key={latest.id}
              r={1.1}
              fill={`var(--${latest.from}, var(--accent))`}
              initial={{ offsetDistance: "0%", opacity: 0 }}
              animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
              style={{
                offsetPath: `path("${edgePath(pos.get(latest.from!)!, pos.get(latest.to!)!)}")`,
              }}
            />
          )}
        </svg>

        <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <PhaseChip phase={phase} detail={detail} />
        </div>

        {seats.map((e, i) => {
          const p = pos.get(e.id)!;
          const empty = e.active === false;
          const isWorking = !empty && working(e.id);
          const active = picked === e.id || hover === e.id;
          const color = `var(--${e.id}, var(--accent))`;
          return (
            <motion.button
              key={e.id}
              type="button"
              disabled={!onPick}
              style={{ left: `${p.x}%`, top: `${p.y}%`, ["--c" as string]: color }}
              className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col
                items-center gap-1 outline-none"
              initial={still ? false : { opacity: 0, scale: 0.5 }}
              animate={{ opacity: empty ? 0.55 : 1, scale: 1 }}
              transition={still ? { duration: 0 } : {
                type: "spring", stiffness: 260, damping: 18, delay: (i % 5) * 0.05,
              }}
              whileHover={onPick && !still ? { scale: 1.07 } : undefined}
              whileTap={onPick && !still ? { scale: 0.95 } : undefined}
              onClick={() => onPick?.(e.id)}
              onMouseEnter={() => setHover(e.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(e.id)}
              onBlur={() => setHover(null)}
              aria-pressed={onPick ? picked === e.id : undefined}
              aria-label={`${e.name} · ${e.role} · ${
                empty ? t("staff.empty") : isWorking ? t("office.working") : t("office.idle")
              }`}
            >
              <span className="relative grid place-items-center">
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
              </span>
            </motion.button>
          );
        })}

        <p className="sr-only" aria-live="polite">
          {phase ? `${phase}${detail ? ` · ${detail}` : ""}` : ""}
        </p>
      </div>

      {/* 최근 인계 — 원탁에는 없던 칸이다. 이 화면의 요점(일이 어떻게
          넘어갔나)은 자리 배치가 아니라 여기로 말한다. */}
      {handoffs.length > 0 && (
        <div className="border-t border-line px-3 py-2.5">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-dim">
            {t("handoff.recent")}
          </div>
          <ul className="space-y-1">
            {handoffs.slice(0, 3).map((h) => (
              <li
                key={h.id}
                className="flex items-baseline gap-1.5 rounded-lg px-1.5 py-1 text-[11px]"
                style={{ borderLeft: `2px solid var(--${h.to}, var(--line-strong))` }}
              >
                <span className="shrink-0 font-semibold" style={{ color: `var(--${h.from}, var(--muted))` }}>
                  {nodeLabel(h.from, roster, t)}
                </span>
                <span className="shrink-0 text-dim">→</span>
                <span className="shrink-0 font-semibold" style={{ color: `var(--${h.to}, var(--muted))` }}>
                  {nodeLabel(h.to, roster, t)}
                </span>
                <span className="min-w-0 truncate text-dim">· {summarize(h, t)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
