"use client";

/**
 * 결재함 — 대표 승인 지점 (DAY 25 · 사규 §3 ⑦).
 *
 * ## 하나씩
 *
 * 사규는 "대표가 하루에 결정할 일을 최대한 줄인다"고 말한다. 줄일 수 없는
 * 것은 **한 번에 하나씩** 보여준다 — 목록으로 쌓아두면 대표는 제목만 보고
 * 전부 승인한다. 그러면 승인 지점을 둔 의미가 없다.
 *
 * ## 선택지 넷
 *
 * 승인 · 수정 요청 · 보류 · 폐기. 수정 요청은 **무엇을 고칠지** 적어야
 * 보낼 수 있다(사유 없는 반려는 같은 결과를 한 번 더 산다). 폐기는 되돌릴
 * 수 없으므로 한 번 더 묻는다 — 태스크면 그 태스크가 만든 파일을 되돌리고,
 * 계획이면 실행을 멈춘다.
 */
import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api";
import { type Key, useErrorText, useLang } from "@/lib/i18n";
import type { Approval, Decision } from "@/lib/types";
import { Button } from "../ui";

export function ApprovalDesk({
  slug, approvals, onDecided, compact = false,
}: {
  slug: string;
  approvals: Approval[];
  onDecided?: (note: string | null) => void;
  compact?: boolean;
}) {
  const { t } = useLang();
  const errText = useErrorText();
  const [index, setIndex] = useState(0);
  const [mode, setMode] = useState<null | "reject" | "hold" | "discard">(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  if (approvals.length === 0) return null;
  const a = approvals[Math.min(index, approvals.length - 1)];
  const d = a.detail ?? {};

  const decide = async (decision: Decision) => {
    if (busy) return;
    if (decision === "reject" && !comment.trim()) {
      setError(t("approval.needComment"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await api.decide(slug, a.id, decision, comment.trim());
      const msg = decision === "hold" ? t("approval.heldNote")
        : out.note ? t("approval.notResumed", { note: out.note })
          : out.resumed ? t("approval.resumed") : t("approval.recorded");
      setNote(msg);
      setMode(null);
      setComment("");
      setIndex(0);
      onDecided?.(msg);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const conf = typeof d.confidence === "number" ? Math.round(d.confidence * 100) : null;
  const confColor = conf == null ? "var(--dim)"
    : conf >= 80 ? "var(--st-done)" : conf >= 60 ? "var(--st-working)" : "var(--bad)";

  return (
    <section className="glass glass-lit border-2"
      style={{ borderColor: "var(--st-approval)" }}
      aria-live="polite">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="approval-pulse size-2 rounded-full"
          style={{ background: "var(--st-approval)" }} aria-hidden />
        <h2 className="text-[13px] font-semibold" style={{ color: "var(--st-approval)" }}>
          {t("approval.title")}
        </h2>
        <span className="text-[11px] text-dim">
          {t(`approval.gate.${a.gate}` as Key)}
          {d.reason === "confidence" && ` · ${t("approval.lowConfidence")}`}
        </span>
        {a.held && (
          <span className="rounded-md px-1.5 py-0.5 text-[10px] font-semibold"
            style={{ background: "var(--panel-2)", color: "var(--st-integration)" }}>
            {t("approval.held")}
          </span>
        )}
        {approvals.length > 1 && (
          <span className="ml-auto flex items-center gap-1 text-[11px] text-dim">
            <button type="button" className="px-1 hover:text-fg"
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
              aria-label={t("approval.prev")}>‹</button>
            {t("approval.count", { i: Math.min(index, approvals.length - 1) + 1,
                                   n: approvals.length })}
            <button type="button" className="px-1 hover:text-fg"
              onClick={() => setIndex((i) => Math.min(approvals.length - 1, i + 1))}
              aria-label={t("approval.next")}>›</button>
          </span>
        )}
      </header>

      <div className="space-y-3 p-4 text-sm">
        <p className="font-medium">{a.title}</p>

        {a.gate === "plan" && (
          <>
            {d.message && <p className="text-muted">{d.message}</p>}
            {!compact && (
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-[11px] text-dim">{t("approval.tasks")}</p>
                  <ol className="space-y-1 text-xs">
                    {(d.tasks ?? []).map((task) => (
                      <li key={task.id} className="flex gap-1.5">
                        <span className="text-dim">{task.id}</span>
                        <span className="min-w-0 flex-1">{task.title}</span>
                        <span style={{ color: `var(--${task.assignee}, var(--dim))` }}>
                          {task.assignee}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
                <div>
                  <p className="mb-1 text-[11px] text-dim">{t("approval.criteria")}</p>
                  <ul className="space-y-1 text-xs text-muted">
                    {(d.criteria ?? []).map((c) => (
                      <li key={c.id}><span className="text-dim">{c.id}</span> {c.text}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </>
        )}

        {a.gate === "task" && (
          <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              {d.assignee && (
                <span>{t("approval.by")}{" "}
                  <b style={{ color: `var(--${d.assignee}, var(--fg))` }}>{d.assignee}</b>
                </span>
              )}
              {conf != null && (
                <span title={t("approval.confidenceHint")}>
                  {t("approval.confidence")}{" "}
                  <b style={{ color: confColor }}>{conf}%</b>
                  {d.reason === "confidence" && d.threshold != null && (
                    <span className="text-dim">
                      {" "}{t("approval.threshold", { n: Math.round(d.threshold * 100) })}
                    </span>
                  )}
                </span>
              )}
              {typeof d.rework === "number" && d.rework > 0 && (
                <span className="text-dim">{t("approval.reworked", { n: d.rework })}</span>
              )}
            </div>
            {d.message && (
              <p className="rounded-lg bg-panel2 px-3 py-2 text-xs text-muted">
                <span className="mr-1 text-dim">{t("approval.verifierSays")}</span>
                {d.message}
              </p>
            )}
            {(d.files?.length ?? 0) > 0 && (
              <p className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="text-dim">{t("approval.files")}</span>
                {d.files!.map((f) => (
                  <Link key={f} href={`/projects/${encodeURIComponent(slug)}?file=${
                    encodeURIComponent(f)}`}
                    className="rounded-md bg-panel2 px-1.5 py-0.5 font-mono hover:text-accent">
                    {f}
                  </Link>
                ))}
              </p>
            )}
          </>
        )}

        {mode && (
          <div className="space-y-2">
            {mode === "discard" && (
              <p className="text-xs" style={{ color: "var(--bad)" }}>
                {a.gate === "plan" ? t("approval.discardPlanWarn")
                  : t("approval.discardTaskWarn")}
              </p>
            )}
            {mode !== "discard" && (
              <textarea value={comment} onChange={(e) => setComment(e.target.value)}
                rows={2} autoFocus
                placeholder={mode === "reject" ? t("approval.rejectPlaceholder")
                  : t("approval.holdPlaceholder")}
                className="w-full rounded-xl border border-line bg-[color:var(--panel-2)]
                  px-3 py-2 text-sm outline-none placeholder:text-dim focus:border-accent" />
            )}
            <div className="flex gap-2">
              <Button tone={mode === "discard" ? "danger" : "primary"} disabled={busy}
                onClick={() => void decide(mode)}>
                {t(`approval.confirm.${mode}` as Key)}
              </Button>
              <Button tone="ghost" onClick={() => { setMode(null); setError(null); }}>
                {t("approval.cancel")}
              </Button>
            </div>
          </div>
        )}

        {!mode && (
          <div className="flex flex-wrap gap-2">
            <Button tone="primary" disabled={busy} onClick={() => void decide("approve")}>
              {t("approval.approve")}
            </Button>
            <Button disabled={busy} onClick={() => setMode("reject")}>
              {t("approval.reject")}
            </Button>
            <Button tone="ghost" disabled={busy} onClick={() => setMode("hold")}>
              {t("approval.hold")}
            </Button>
            <Button tone="ghost" disabled={busy} onClick={() => setMode("discard")}
              className="ml-auto !text-[color:var(--bad)]">
              {t("approval.discard")}
            </Button>
          </div>
        )}

        {error && <p className="text-xs" style={{ color: "var(--bad)" }}>{error}</p>}
        {note && !error && <p className="text-xs text-dim">{note}</p>}
      </div>
    </section>
  );
}
