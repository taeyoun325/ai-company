"use client";

/**
 * "왜 느린가" (DAY 25 · backend/app/metrics.py).
 *
 * 비용은 전부터 보였다. 시간은 안 보였다. 여기서 세 가지를 나눠 보여준다:
 *
 * - **누가** — 직원별 호출 수 · 평균 · p95 · 기다린 시간(요청 한도) · 재시도.
 * - **어디서** — 단계별 시간. 태스크가 동시에 돌면 단계 시간의 합이 벽시계보다
 *   길다 — 그래서 "동시에 일한 정도(병렬도)"를 같이 적는다.
 * - **지금** — 응답을 기다리는 호출과 몇 초째인지.
 *
 * 사람을 기다린 시간(결재 대기)은 따로 적는다. 모델이 느린 것과 대표가
 * 아직 안 본 것은 대응이 다르다.
 */
import { useEffect } from "react";

import { api } from "@/lib/api";
import { type Key, useLang } from "@/lib/i18n";
import type { RunMetrics } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { Empty, Skeleton } from "./ui";

const PHASES = ["PLAN", "REPLAN", "WRITE_TESTS", "IMPLEMENT", "TEST", "REVIEW",
                "FINALIZE", "AWAITING"];

function secs(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function MetricsPanel({ slug, live, names }: {
  slug: string; live: boolean; names: Record<string, string>;
}) {
  const { t } = useLang();
  const { data, reload } = useLoader<RunMetrics>(`metrics:${slug}`, () => api.metrics(slug));
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => void reload(), 3000);
    return () => clearInterval(timer);
  }, [live, reload]);

  if (!data) return <Skeleton lines={4} />;
  if (data.calls === 0 && data.inflight.length === 0) return <Empty>{t("metrics.none")}</Empty>;

  const agents = Object.entries(data.by_agent).sort((a, b) => b[1].total_ms - a[1].total_ms);
  const phaseTotal = PHASES.reduce((s, p) => s + (data.by_phase[p]?.ms ?? 0), 0) || 1;

  return (
    <div className="space-y-3 text-xs">
      <dl className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Cell k={t("metrics.wall")} v={secs(data.wall_ms)} />
        <Cell k={t("metrics.model")} v={secs(data.model_ms)} />
        <Cell k={t("metrics.parallel")}
          v={data.parallelism != null ? `×${data.parallelism}` : "—"}
          hint={t("metrics.parallelHint")} />
        <Cell k={t("metrics.humanWait")} v={secs(data.human_wait_ms)} />
      </dl>

      {data.inflight.length > 0 && (
        <ul className="space-y-1">
          {data.inflight.map((c) => (
            <li key={c.call_id} className="flex justify-between rounded-md px-2 py-1"
              style={{ background: "color-mix(in srgb, var(--st-working) 12%, transparent)" }}>
              <span>{t("metrics.waiting", { who: names[c.agent] ?? c.agent,
                                             model: c.model ?? "" })}</span>
              <b className="tabular-nums">{secs(c.elapsed_ms)}</b>
            </li>
          ))}
        </ul>
      )}

      {/* 단계별 — 가로 막대 하나를 나눠 칠한다. */}
      <div>
        <p className="mb-1 text-[10px] text-dim">{t("metrics.byPhase")}</p>
        <div className="flex h-2.5 overflow-hidden rounded-full bg-panel2">
          {PHASES.filter((p) => data.by_phase[p]?.ms).map((p, i) => (
            <span key={p} title={`${t(`metrics.phase.${p}` as Key)} ${secs(data.by_phase[p].ms)}`}
              style={{ width: `${(100 * data.by_phase[p].ms) / phaseTotal}%`,
                       background: p === "AWAITING" ? "var(--st-approval)"
                         : `color-mix(in srgb, var(--accent) ${90 - i * 9}%, transparent)` }} />
          ))}
        </div>
        <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-dim">
          {PHASES.filter((p) => data.by_phase[p]?.ms).map((p) => (
            <li key={p}>{t(`metrics.phase.${p}` as Key)} {secs(data.by_phase[p].ms)}</li>
          ))}
        </ul>
      </div>

      {/* 직원별 */}
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-[10px] text-dim">
            <th className="text-left font-normal">{t("metrics.who")}</th>
            <th className="text-right font-normal">{t("metrics.calls")}</th>
            <th className="text-right font-normal">{t("metrics.avg")}</th>
            <th className="text-right font-normal">p95</th>
            <th className="text-right font-normal" title={t("metrics.waitHint")}>
              {t("metrics.wait")}</th>
            <th className="text-right font-normal">{t("metrics.retries")}</th>
          </tr>
        </thead>
        <tbody>
          {agents.map(([id, a]) => (
            <tr key={id}>
              <td style={{ color: `var(--${id}, var(--muted))` }}>{names[id] ?? id}</td>
              <td className="text-right tabular-nums">
                {a.calls}{a.failed ? <span style={{ color: "var(--bad)" }}> ({a.failed}✕)</span> : null}
              </td>
              <td className="text-right tabular-nums">{secs(a.avg_ms)}</td>
              <td className="text-right tabular-nums">{secs(a.p95_ms)}</td>
              <td className="text-right tabular-nums">{a.wait_ms ? secs(a.wait_ms) : "—"}</td>
              <td className="text-right tabular-nums">{a.retries || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {data.slowest.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[10px] text-dim">{t("metrics.slowest")}</summary>
          <ol className="mt-1 space-y-0.5 text-[11px]">
            {data.slowest.map((c) => (
              <li key={c.call_id} className="flex justify-between gap-2">
                <span className="truncate">{names[c.agent] ?? c.agent}
                  <span className="text-dim"> · {c.model}{c.attempts > 1
                    ? ` · ${t("metrics.attempts", { n: c.attempts })}` : ""}</span></span>
                <b className="tabular-nums" style={{ color: c.ok ? undefined : "var(--bad)" }}>
                  {secs(c.ms)}</b>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

function Cell({ k, v, hint }: { k: string; v: string; hint?: string }) {
  return (
    <div className="rounded-md bg-panel2 px-2 py-1" title={hint}>
      <dt className="text-[10px] text-dim">{k}</dt>
      <dd className="font-semibold tabular-nums">{v}</dd>
    </div>
  );
}
