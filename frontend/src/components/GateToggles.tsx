"use client";

/**
 * 대표 승인 지점 켜고 끄기 (DAY 25 · HITL).
 *
 * 새 일을 맡길 때도, 도는 중에도 바꿀 수 있다 — "이 다음 태스크부터는 내가
 * 보겠다"가 실제로 자주 생기는 요구다. 도는 중에 바꾸면 **다음 승인 지점부터**
 * 적용된다(이미 지난 지점을 되돌려 멈추지는 않는다).
 *
 * 선택지는 넷이다: 계획 승인 · 모든 결과 승인 · 개발자 결과만 · 확신 낮을 때만.
 * "모든 결과"를 켜면 "개발자만"은 의미가 없으므로 흐리게 한다.
 */
import { useLang } from "@/lib/i18n";

export const GATE_OPTIONS = ["plan", "task", "task:developer", "confidence"] as const;

export function GateToggles({ value, onChange, disabled = false }: {
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const { t } = useLang();
  const label: Record<(typeof GATE_OPTIONS)[number], [string, string]> = {
    plan: [t("gate.plan"), t("gate.planHint")],
    task: [t("gate.task"), t("gate.taskHint")],
    "task:developer": [t("gate.taskDev"), t("gate.taskDevHint")],
    confidence: [t("gate.confidence"), t("gate.confidenceHint")],
  };
  const toggle = (g: string) =>
    onChange(value.includes(g) ? value.filter((x) => x !== g) : [...value, g]);
  return (
    <fieldset className="flex flex-wrap gap-1.5" disabled={disabled}>
      <legend className="sr-only">{t("gate.legend")}</legend>
      {GATE_OPTIONS.map((g) => {
        const on = value.includes(g);
        const moot = g === "task:developer" && value.includes("task");
        return (
          <label key={g} title={label[g][1]}
            className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5
              py-1 text-[11px] transition ${moot ? "opacity-45" : ""}`}
            style={{
              borderColor: on ? "var(--st-approval)" : "var(--line)",
              background: on ? "color-mix(in srgb, var(--st-approval) 12%, transparent)"
                : "var(--panel)",
            }}>
            <input type="checkbox" checked={on} onChange={() => toggle(g)}
              className="accent-[color:var(--st-approval)]" />
            ★ {label[g][0]}
          </label>
        );
      })}
    </fieldset>
  );
}
