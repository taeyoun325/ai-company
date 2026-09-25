"use client";

/**
 * 이 프로젝트만의 권한 (DAY 25 · backend/app/agents/permissions.py).
 *
 * 직원 × 구역 표에서 읽기(R)·쓰기(W)를 켜고 끈다. 세 종류의 칸이 있다:
 *
 * - **자유** — 누르면 바뀐다.
 * - **위험** — 구현자의 tests/ 읽기. 켜려면 위험을 확인해야 한다. 켜진
 *   프로젝트는 "교차검증 약화"라는 표시를 계속 단다.
 * - **바닥(잠김)** — 검증자 외의 tests/ 쓰기 등. 누구도 못 푼다. 왜 잠겼는지
 *   말풍선으로 말한다 — 이유 없이 눌리지 않는 칸은 고장으로 보인다.
 *
 * 실행이 **도는 중**에는 바꿀 수 없다. 동시에 도는 태스크끼리 같은 파일을
 * 쓰게 될 수 있어서다(서버가 409 로 막는다). 멈췄거나 결재를 기다릴 때 바꾼다.
 */
import { useState } from "react";

import { api } from "@/lib/api";
import { type Key, useErrorText, useLang } from "@/lib/i18n";
import type { PermissionsView } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { Button, Skeleton } from "./ui";

const AREAS = ["src", "tests", "docs", "design"] as const;
type Ov = Record<string, { writes?: string[]; reads?: string[] }>;

export function PermissionsPanel({ slug, running }: { slug: string; running: boolean }) {
  const { t } = useLang();
  const errText = useErrorText();
  const { data, reload } = useLoader<PermissionsView>(`perm:${slug}`,
    () => api.permissions(slug));
  const [draft, setDraft] = useState<Ov | null>(null);
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!data) return <Skeleton lines={5} />;

  const rows = data.table;
  const current = (id: string, kind: "writes" | "reads") => {
    const d = draft?.[id]?.[kind];
    if (d) return d;
    return rows.find((r) => r.id === id)!.effective[kind];
  };
  const flip = (id: string, kind: "writes" | "reads", area: string) => {
    const now = current(id, kind);
    const next = now.includes(area) ? now.filter((a) => a !== area) : [...now, area];
    setDraft((d) => ({ ...(d ?? {}), [id]: { ...(d?.[id] ?? {}), [kind]: next } }));
    setError(null);
  };
  const dirty = draft && Object.keys(draft).length > 0;
  const risky = rows.some((r) => r.risky.reads.some(
    (a) => current(r.id, "reads").includes(a)));

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      // 서버에는 **바뀐 직원의 실효 값 전체**를 보낸다 — 조각만 보내면 나머지
      // 한쪽(읽기/쓰기)이 기본값으로 돌아간 것처럼 보이는 일이 생긴다.
      const merged: Ov = { ...data.overrides };
      for (const id of Object.keys(draft)) {
        merged[id] = { writes: current(id, "writes"), reads: current(id, "reads") };
      }
      await api.setPermissions(slug, merged, ack);
      setDraft(null);
      await reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await api.setPermissions(slug, {}, false);
      setDraft(null);
      await reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 text-xs">
      {data.risks.includes("tests_visible") && (
        <p className="rounded-lg px-2.5 py-1.5"
          style={{ background: "color-mix(in srgb, var(--warn) 14%, transparent)",
                   color: "var(--warn)" }}>
          {t("perm.riskActive")}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-y-1">
          <thead>
            <tr className="text-[10px] text-dim">
              <th className="text-left font-normal">{t("perm.employee")}</th>
              {AREAS.map((a) => <th key={a} className="font-mono font-normal">{a}/</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="pr-2" style={{ color: `var(--${r.id})` }}>
                  {t(`perm.role.${r.id}` as Key)}
                  {r.overridden && <span className="ml-1 text-dim">•</span>}
                </td>
                {AREAS.map((a) => (
                  <td key={a} className="text-center">
                    <span className="inline-flex gap-1">
                      {(["reads", "writes"] as const).map((kind) => {
                        const on = current(r.id, kind).includes(a);
                        const locked = r.locked[kind].includes(a);
                        const danger = kind === "reads" && r.risky.reads.includes(a);
                        const why = locked ? t(`perm.lock.${kind}` as Key)
                          : danger ? t("perm.riskCell") : "";
                        return (
                          <button key={kind} type="button"
                            disabled={locked || running || busy}
                            onClick={() => flip(r.id, kind, a)}
                            title={why || undefined}
                            aria-pressed={on}
                            aria-label={`${r.id} ${a} ${kind}`}
                            className="w-6 rounded-md border py-0.5 font-mono text-[10px]
                              disabled:cursor-not-allowed"
                            style={{
                              borderColor: on ? (danger ? "var(--warn)" : "var(--accent)")
                                : "var(--line)",
                              background: on
                                ? `color-mix(in srgb, ${danger ? "var(--warn)" : "var(--accent)"} 16%, transparent)`
                                : "transparent",
                              opacity: locked ? 0.45 : 1,
                            }}>
                            {kind === "reads" ? "R" : "W"}
                          </button>
                        );
                      })}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-dim">{t("perm.legend")}</p>
      {running && <p className="text-dim">{t("perm.running")}</p>}
      {dirty && risky && (
        <label className="flex items-start gap-2" style={{ color: "var(--warn)" }}>
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          {t("perm.ack")}
        </label>
      )}
      {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
      <div className="flex gap-2">
        <Button tone="primary" disabled={!dirty || busy || running} onClick={() => void save()}>
          {t("perm.save")}
        </Button>
        {dirty && <Button tone="ghost" onClick={() => setDraft(null)}>{t("perm.discard")}</Button>}
        {Object.keys(data.overrides).length > 0 && !dirty && (
          <Button tone="ghost" disabled={busy || running} onClick={() => void reset()}>
            {t("perm.reset")}
          </Button>
        )}
      </div>
    </div>
  );
}
