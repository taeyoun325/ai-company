"use client";

/**
 * 가상 사무실 (지시서 §4).
 *
 * ## 무엇을 보여주는 화면인가
 *
 * 직원 다섯 명의 자리. 지금 누가 일하고 있고, 누가 어떤 모델로 일하며,
 * 얼마를 썼는지. 게임처럼 보이는 것이 목적이 아니라 **한눈에 상태가
 * 읽히는 것**이 목적이다.
 *
 * ## Mock 을 숨기지 않는다
 *
 * 자리마다 Mock 배지가 붙는다. 예쁜 화면을 위해 이걸 빼면, 시연에서
 * 아무도 진짜 AI 와 대본을 구분하지 못한다.
 *
 * ## 움직임 (DAY 20 에 보탬)
 *
 * 일하는 중인 자리에만 맥박이 돈다. 전부 움직이면 어디를 봐야 할지
 * 알 수 없고, 아무것도 안 움직이면 진행 중인지 멈춘 건지 알 수 없다.
 * `prefers-reduced-motion` 에서는 테두리로 대신한다 (globals.css).
 *
 * 여기에 두 가지를 더했다. 둘 다 **정보를 나르는 움직임**이다:
 *
 * 1. **일감을 받는 순간** 그 자리가 한 번 튄다. 맥박은 "지금 일하는 중"을
 *    말하지만 "방금 넘어왔다"는 말하지 못한다. 눈이 다른 데 가 있다가
 *    돌아오면 누가 언제 받았는지 알 수 없다.
 * 2. **호출 수와 비용이 숫자를 세며 올라간다.** 값이 툭 바뀌면 바뀐 줄
 *    모르고 지나간다. 돈이 늘어나는 것은 사용자가 놓치면 안 되는 정보다.
 *
 * 장식은 더하지 않았다. 작업 화면에서 움직임은 소음이고, 소음이 늘면
 * 진짜 신호(맥박)가 묻힌다.
 */
import { useEffect, useRef } from "react";

import { T, animate, prefersReducedMotion, stagger, withScope }
  from "@/lib/motion";
import { useLang } from "@/lib/i18n";
import type { Employee } from "@/lib/types";
import { Icon, iconOfAgent } from "./icons";
import { MockBadge, money } from "./ui";

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

export function Office({
  employees,
  phase,
  detail,
  busy,
  onPick,
  picked,
}: {
  employees: Employee[];
  phase?: string;
  detail?: string;
  /** MANUAL 에서 지금 일하는 직원 id. AUTO 에서는 phase 로 판단한다. */
  busy?: string | null;
  onPick?: (id: string) => void;
  picked?: string | null;
}) {
  const working = (id: string) => {
    if (busy) return busy === id;
    if (!phase) return false;
    const owners = PHASE_OWNER[phase] ?? [];
    // IMPLEMENT 는 담당자가 여럿일 수 있다. 단계 설명에 이름이 들어 있으면
    // 그 사람만 켠다 — 셋을 동시에 켜면 누가 일하는지 알 수 없다.
    if (owners.length > 1 && detail) {
      const e = employees.find((x) => detail.includes(x.name));
      return e ? e.id === id : owners.includes(id);
    }
    return owners.includes(id);
  };

  const root = useRef<HTMLDivElement>(null);
  const seen = useRef(false);

  // 자리들이 처음 들어올 때만 줄줄이 등장한다. 상태가 바뀔 때마다 다시
  // 등장하면, 직원 하나가 일을 시작할 때 다섯 자리가 전부 깜빡인다.
  useEffect(() => {
    const el = root.current;
    if (!el || seen.current || employees.length === 0) return;
    seen.current = true;
    return withScope(el, () => {
      animate(el.querySelectorAll(".desk"), {
        opacity: [0, 1], translateY: [10, 0], duration: T.base,
        ease: T.ease, delay: stagger(T.step),
      });
    });
  }, [employees.length]);

  return (
    <div
      ref={root}
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
    >
      {employees.map((e) => (
        <Desk
          key={e.id}
          e={e}
          working={working(e.id)}
          picked={picked === e.id}
          onPick={onPick}
        />
      ))}
    </div>
  );
}

/**
 * 숫자가 세며 올라간다.
 *
 * 값이 툭 바뀌면 바뀐 줄 모르고 지나간다. 특히 비용은 사용자가 놓치면
 * 안 되는 정보다. 다만 **세는 동안에도 항상 진짜 값에 수렴**해야 한다 —
 * 애니메이션이 끊기면 마지막 프레임이 화면에 남으므로, 끝값을 직접
 * 한 번 더 쓴다.
 */
function useCountUp(value: number, format: (n: number) => string) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(value);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const from = prev.current;
    prev.current = value;
    if (from === value) return;
    if (prefersReducedMotion()) {
      el.textContent = format(value);
      return;
    }
    const box = { n: from };
    const anim = animate(box, {
      n: value, duration: T.slow, ease: "out(3)",
      onUpdate: () => {
        el.textContent = format(box.n);
      },
      onComplete: () => {
        el.textContent = format(value);
      },
    });
    return () => {
      anim.pause();
      el.textContent = format(value);
    };
  }, [value, format]);

  return ref;
}

function Desk({
  e,
  working,
  picked,
  onPick,
}: {
  e: Employee;
  working: boolean;
  picked: boolean;
  onPick?: (id: string) => void;
}) {
  const { t } = useLang();
  const color = `var(--${e.id}, var(--accent))`;
  const usage = e.usage ?? {};
  const Tag = onPick ? "button" : "div";
  const seat = useRef<HTMLElement>(null);
  const was = useRef(working);

  // 일감을 **받는 순간**에만 한 번 튄다. 맥박(.working)은 "지금 일하는
  // 중"을 말하고, 이 한 번은 "방금 넘어왔다"를 말한다. 둘은 다른 정보다.
  useEffect(() => {
    const el = seat.current;
    const started = working && !was.current;
    was.current = working;
    if (!el || !started || prefersReducedMotion()) return;
    animate(el, { scale: [1, 1.035, 1], duration: 420, ease: "out(2)" });
  }, [working]);

  return (
    <Tag
      {...(onPick
        ? { onClick: () => onPick(e.id), type: "button" as const }
        : {})}
      ref={seat as React.Ref<HTMLButtonElement & HTMLDivElement>}
      style={{ ["--c" as string]: color }}
      className={`desk rounded-xl border bg-panel p-3 text-left transition
        ${working ? "working" : ""}
        ${picked ? "border-accent" : "border-line"}
        ${onPick ? "hover:border-dim cursor-pointer" : ""}`}
    >
      <div className="flex items-start gap-3">
        <div
          className="grid size-10 shrink-0 place-items-center rounded-lg"
          style={{
            background: `color-mix(in srgb, ${color} 16%, transparent)`,
            border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
            color,
          }}
          aria-hidden
        >
          <Icon name={iconOfAgent(e.id)} size={22} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold">{e.name}</span>
            <span className="text-xs text-muted">{e.role}</span>
            {e.mock && <MockBadge />}
          </div>
          <p className="mt-0.5 truncate text-xs text-dim" title={e.desc}>
            {e.desc}
          </p>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <Cell label={t("office.model")} value={e.model} title={e.model} />
        <CountCell label={t("office.calls")} value={usage.calls ?? 0}
                   format={fmtCalls} />
        <CountCell label={t("office.cost")} value={usage.cost ?? 0}
                   format={money} />
      </dl>

      <p className="mt-2 text-[11px] text-dim">
        {t("office.writes")}{" "}
        {e.writes.length
          ? e.writes.map((w) => `${w}/`).join(" ")
          : t("office.none")}
        {" · "}
        {t("office.reads")} {e.reads.map((r) => `${r}/`).join(" ")}
      </p>

      <p className="mt-1 text-[11px]" style={{ color: working ? color : "var(--dim)" }}>
        {working ? t("office.working") : t("office.idle")}
      </p>
    </Tag>
  );
}

const fmtCalls = (n: number) => String(Math.round(n));

function CountCell({
  label,
  value,
  format,
}: {
  label: string;
  value: number;
  format: (n: number) => string;
}) {
  const ref = useCountUp(value, format);
  return (
    <div className="rounded-md bg-panel2 px-2 py-1">
      <dt className="text-dim">{label}</dt>
      <dd className="truncate font-medium tabular-nums">
        {/* 서버가 보낸 HTML 에도 숫자가 들어 있어야 한다. 스크립트가
            늦게 붙어도 빈칸이 보이지 않는다. */}
        <span ref={ref}>{format(value)}</span>
      </dd>
    </div>
  );
}

function Cell({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div className="rounded-md bg-panel2 px-2 py-1">
      <dt className="text-dim">{label}</dt>
      <dd className="truncate font-medium" title={title}>
        {value}
      </dd>
    </div>
  );
}
