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
 * ## 움직임
 *
 * 일하는 중인 자리에만 맥박이 돈다. 전부 움직이면 어디를 봐야 할지
 * 알 수 없고, 아무것도 안 움직이면 진행 중인지 멈춘 건지 알 수 없다.
 * `prefers-reduced-motion` 에서는 테두리로 대신한다 (globals.css).
 */
import type { Employee } from "@/lib/types";
import { MockBadge, money } from "./ui";

const ICONS: Record<string, string> = {
  strategist: "🧭",
  developer: "🛠️",
  analyst: "🔍",
  writer: "✍️",
  designer: "🎨",
};

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

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
  const color = `var(--${e.id}, var(--accent))`;
  const usage = e.usage ?? {};
  const Tag = onPick ? "button" : "div";

  return (
    <Tag
      {...(onPick
        ? { onClick: () => onPick(e.id), type: "button" as const }
        : {})}
      style={{ ["--c" as string]: color }}
      className={`rounded-xl border bg-panel p-3 text-left transition
        ${working ? "working" : ""}
        ${picked ? "border-accent" : "border-line"}
        ${onPick ? "hover:border-dim cursor-pointer" : ""}`}
    >
      <div className="flex items-start gap-3">
        <div
          className="grid size-10 shrink-0 place-items-center rounded-lg text-xl"
          style={{
            background: `color-mix(in srgb, ${color} 16%, transparent)`,
            border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
          }}
          aria-hidden
        >
          {ICONS[e.id] ?? "👤"}
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
        <Cell label="모델" value={e.model} title={e.model} />
        <Cell label="호출" value={String(usage.calls ?? 0)} />
        <Cell label="비용" value={money(usage.cost)} />
      </dl>

      <p className="mt-2 text-[11px] text-dim">
        쓰기 {e.writes.length ? e.writes.map((w) => `${w}/`).join(" ") : "없음"}
        {" · "}
        읽기 {e.reads.map((r) => `${r}/`).join(" ")}
      </p>

      <p className="mt-1 text-[11px]" style={{ color: working ? color : "var(--dim)" }}>
        {working ? "작업 중" : "대기"}
      </p>
    </Tag>
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
