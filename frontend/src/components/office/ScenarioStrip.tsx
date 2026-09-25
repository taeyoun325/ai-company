"use client";

/**
 * 하루 시나리오 12단계 (DAY 25 · 사규 §3).
 *
 * 이 제품의 파이프라인을 사규의 "하루"로 그린다. ★ 은 대표 승인 지점이다 —
 * 켜지 않았으면 "꺼짐"으로 흐리게 보인다. 끄고 켜는 것은 대표의 몫이고,
 * 꺼져 있다는 사실이 화면에 있어야 "왜 안 멈췄지"를 묻지 않는다.
 */
import { type Key, useLang } from "@/lib/i18n";
import type { ScenarioStep } from "@/lib/types";

const GATE = new Set(["plan_gate", "task_gate"]);
const NUM = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫"];

export function ScenarioStrip({ steps }: { steps: ScenarioStep[] }) {
  const { t } = useLang();
  return (
    <ol className="flex gap-1 overflow-x-auto pb-1" aria-label={t("office.scenario")}>
      {steps.map((s, i) => {
        const gate = GATE.has(s.key);
        const color = s.state === "done" ? "var(--st-done)"
          : s.state === "current" ? (gate ? "var(--st-approval)" : "var(--st-working)")
            : "var(--dim)";
        return (
          <li key={s.key}
            aria-current={s.state === "current" ? "step" : undefined}
            className={`flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5
              text-[11px] ${s.state === "current" ? "font-semibold" : ""}
              ${s.state === "off" || s.state === "skip" ? "opacity-45" : ""}`}
            style={{
              borderColor: s.state === "current" ? color : "var(--line)",
              background: s.state === "current"
                ? `color-mix(in srgb, ${color} 14%, transparent)` : "var(--panel)",
            }}
            title={s.state === "off" ? t("office.step.offHint") : undefined}>
            <span style={{ color }}>{s.state === "done" ? "✓" : NUM[i]}</span>
            <span>{gate && "★ "}{t(`office.step.${s.key}` as Key)}</span>
            {s.state === "off" && <span className="text-dim">{t("office.step.off")}</span>}
          </li>
        );
      })}
    </ol>
  );
}
