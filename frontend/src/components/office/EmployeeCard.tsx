"use client";

/**
 * 직원 한 명 — 평면도에서 누른 사람의 자세한 사정 (DAY 25).
 *
 * 상태와 **이유**(사규 §2 ②), 맡은 태스크와 진행률, 이번 프로젝트에서 쓴
 * 돈과 걸린 시간, 말버릇 두 줄(사규 §1). 말버릇은 직원 프롬프트의 규칙을
 * 사람 말로 옮긴 것이다 — 캐릭터이면서 그 직원이 무엇을 안 하는지를 말한다.
 */
import { type Key, useLang } from "@/lib/i18n";
import type { IntegrationItem, OfficeEmployee } from "@/lib/types";
import { MockBadge, money } from "../ui";
import { Avatar, BUBBLE_KEY, STATE_COLOR } from "./OfficeFloor";

export function EmployeeCard({ e, items, onClose }: {
  e: OfficeEmployee;
  items: IntegrationItem[];
  onClose: () => void;
}) {
  const { t } = useLang();
  const blocked = items.filter((i) => i.affects.includes(e.id));
  return (
    <section className="glass glass-lit p-4">
      <div className="flex items-start gap-3">
        <Avatar e={e} size={46} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-semibold">
            {e.name}
            <span className="text-xs font-normal text-dim">
              {t(`office.dept.${e.dept}` as Key)} · {e.role}
            </span>
            {e.mock && <MockBadge />}
          </p>
          <p className="mt-0.5 text-xs font-semibold" style={{ color: STATE_COLOR[e.state] }}>
            {t(`office.state.${e.state}` as Key)} — “{t(BUBBLE_KEY[e.state])}”
          </p>
          <p className="mt-1 text-sm text-muted">{e.reason}</p>
        </div>
        <button type="button" onClick={onClose} className="text-dim hover:text-fg"
          aria-label={t("office.card.close")}>×</button>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-1.5 text-[11px] sm:grid-cols-4">
        <Cell k={t("office.card.task")} v={e.task?.title ?? "—"} />
        <Cell k={t("office.card.progress")}
          v={e.progress.total ? `${e.progress.done}/${e.progress.total}` : "—"} />
        <Cell k={t("office.card.cost")}
          v={e.calls ? `${money(e.cost)} · ${t("office.card.calls", { n: e.calls })}` : "—"} />
        <Cell k={t("office.card.latency")}
          v={e.avg_ms != null ? `${(e.avg_ms / 1000).toFixed(1)}s` : "—"} />
      </dl>

      {blocked.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs">
          {blocked.map((i) => (
            <li key={i.key} className="rounded-lg px-2.5 py-1.5"
              style={{ background: "color-mix(in srgb, var(--st-integration) 12%, transparent)" }}>
              <b style={{ color: "var(--st-integration)" }}>{t("office.state.integration")}</b>{" "}
              {i.why}
              {i.fix && <a href={i.fix} className="ml-1 underline">{t("office.card.fix")}</a>}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 border-t border-line pt-2 text-xs text-muted">
        <p className="mb-1 text-[10px] text-dim">{t("office.card.catchphrase")}</p>
        <p>“{t(`office.catch.${e.id}.1` as Key)}”</p>
        <p>“{t(`office.catch.${e.id}.2` as Key)}”</p>
      </div>
    </section>
  );
}

function Cell({ k, v }: { k: string; v: string }) {
  return (
    <div className="min-w-0 rounded-md bg-panel2 px-2 py-1">
      <dt className="text-dim">{k}</dt>
      <dd className="truncate font-medium" title={v}>{v}</dd>
    </div>
  );
}

/** 사규 §2 "현재 연동 대기 항목" — 대표가 무엇을 줘야 풀리는가. */
export function IntegrationList({ items }: { items: IntegrationItem[] }) {
  const { t } = useLang();
  if (items.length === 0) return null;
  return (
    <section className="glass glass-lit px-4 py-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold">
        <span className="size-2 rounded-full" style={{ background: "var(--st-integration)" }} />
        {t("office.integrations", { n: items.length })}
      </h3>
      <ul className="space-y-1 text-xs text-muted">
        {items.map((i) => (
          <li key={i.key} className="flex flex-wrap items-baseline gap-x-1.5">
            <b className="text-fg">{i.label}</b>
            <span>{i.why}</span>
            {i.fix && <a href={i.fix} className="underline">{t("office.card.fix")}</a>}
          </li>
        ))}
      </ul>
    </section>
  );
}
