"use client";

/**
 * 대표 지시창 (DAY 25 · 사규 §4).
 *
 * 대표가 아무 때나 묻는 창구. 답은 서버의 비서실(backend/app/secretary.py)
 * 이 **기록을 읽어** 만든다 — 모델을 부르지 않으므로 공짜고 즉시 온다.
 *
 * 자주 쓰는 말은 단추로 둔다. 손으로 쳐도 된다(세 언어 모두 알아듣는다).
 * "회의 소집"·"집중 모드"는 말로 끝나지 않고 사무실이 움직인다 — 답에
 * 실려 오는 `action` 을 부모가 받아 평면도에 반영한다.
 */
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { type Key, useErrorText, useLang } from "@/lib/i18n";
import type { AskAnswer, OfficeSnapshot } from "@/lib/types";
import { Icon, iconOfAgent } from "../icons";

interface Row {
  id: number;
  who: string;          // "ceo" | "secretary" | 직원 id
  text: string;
}

const QUICK: Key[] = ["cmd.status", "cmd.why", "cmd.meeting", "cmd.brief",
                      "cmd.focus", "cmd.approve"];

export function CommandWindow({
  run, snap, focus, onAction, className = "",
}: {
  run: string | null;
  snap: OfficeSnapshot | null;
  focus: boolean;
  onAction: (answer: AskAnswer) => void;
  className?: string;
}) {
  const { t } = useLang();
  const errText = useErrorText();
  const [rows, setRows] = useState<Row[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [rows]);

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true);
    setText("");
    setRows((r) => [...r, { id: ++seq.current, who: "ceo", text: question }]);
    try {
      const a = await api.ask(question, run);
      setRows((r) => [...r, ...a.lines.map((l) => ({ id: ++seq.current, ...l }))]);
      onAction(a);
    } catch (e) {
      setRows((r) => [...r, { id: ++seq.current, who: "secretary", text: errText(e) }]);
    } finally {
      setBusy(false);
    }
  };

  const nameOf = (who: string) => {
    if (who === "ceo") return t("office.ceo");
    if (who === "secretary") return t("office.secretary");
    return snap?.employees.find((e) => e.id === who)?.name ?? who;
  };

  const people = (snap?.employees ?? []).filter((e) => e.hired);

  return (
    <section className={`glass glass-lit flex flex-col ${className}`}>
      <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <h2 className="text-[13px] font-semibold tracking-tight">{t("cmd.title")}</h2>
        <span className="text-[11px] text-dim">{t("cmd.hint")}</span>
      </header>

      {/* 답은 버튼을 누른 **뒤에** 온다 — 화면 낭독기가 알려주지 않으면 누른
          사람은 답이 왔는지 모른다 (DAY 26). */}
      <div ref={box} role="log" aria-live="polite" aria-label={t("cmd.title")}
        className="max-h-72 min-h-24 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {rows.length === 0 && (
          <p className="py-4 text-center text-xs text-dim">{t("cmd.empty")}</p>
        )}
        {rows.map((r) => (
          <div key={r.id}
            className={`flex gap-2 ${r.who === "ceo" ? "flex-row-reverse text-right" : ""}`}>
            <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full
              bg-panel2">
              <Icon size={14}
                name={r.who === "ceo" ? "person" : r.who === "secretary" ? "system"
                  : iconOfAgent(r.who)}
                style={{ color: `var(--${r.who}, var(--muted))` }} />
            </span>
            <div className={`min-w-0 max-w-[85%] rounded-xl px-3 py-1.5 text-[13px] ${
              r.who === "ceo" ? "grad-accent text-white" : "bg-panel2"}`}>
              {r.who !== "ceo" && (
                <p className="text-[10px] font-semibold"
                  style={{ color: `var(--${r.who}, var(--muted))` }}>
                  {nameOf(r.who)}
                </p>
              )}
              <p className="whitespace-pre-line break-words leading-relaxed">{r.text}</p>
            </div>
          </div>
        ))}
        {busy && <p className="text-xs text-dim">{t("cmd.thinking")}</p>}
      </div>

      <div className="space-y-2 border-t border-line px-3 py-2.5">
        <div className="flex flex-wrap gap-1.5">
          {QUICK.map((k) => (
            <Chip key={k} disabled={busy} onClick={() => void ask(
              k === "cmd.focus" && focus ? t("cmd.unfocus") : t(k))}>
              {k === "cmd.focus" && focus ? t("cmd.unfocus") : t(k)}
            </Chip>
          ))}
        </div>
        {people.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {people.map((e) => (
              <Chip key={e.id} disabled={busy}
                onClick={() => void ask(t("cmd.whois", { name: e.name }))}>
                <span style={{ color: `var(--${e.id})` }}>
                  {t("cmd.whois", { name: e.name })}
                </span>
              </Chip>
            ))}
          </div>
        )}
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void ask(text); }}>
          <input value={text} onChange={(e) => setText(e.target.value)}
            aria-label={t("cmd.title")}
            placeholder={t("cmd.placeholder")} maxLength={500}
            className="min-w-0 flex-1 rounded-xl border border-line bg-[color:var(--panel-2)]
              px-3 py-1.5 text-sm outline-none placeholder:text-dim focus:border-accent" />
          <button type="submit" disabled={busy || !text.trim()}
            className="rounded-xl border border-line bg-panel2 px-3 text-sm
              disabled:opacity-45">
            {t("cmd.send")}
          </button>
        </form>
      </div>
    </section>
  );
}

function Chip({ children, onClick, disabled }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className="rounded-full border border-line bg-panel2 px-2.5 py-0.5 text-[11px]
        text-muted transition hover:border-accent hover:text-fg disabled:opacity-50">
      {children}
    </button>
  );
}
