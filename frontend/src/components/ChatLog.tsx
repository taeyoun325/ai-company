"use client";

/**
 * 실시간 작업 로그 (지시서 §13).
 *
 * ## 자동 스크롤의 함정
 *
 * 새 줄이 올 때마다 무조건 바닥으로 내리면, 위쪽을 읽고 있던 사용자를
 * 계속 끌어내린다. 사용자가 위로 올렸으면 **따라오지 않는다.** 대신
 * "새 소식 N" 버튼을 띄운다.
 *
 * ## 종류를 색으로 가른다
 *
 * say(말) · tool(행동) · verdict(판정) · error(문제). 전부 같은 모양이면
 * 판정과 잡담이 구분되지 않고, 로그가 길어질수록 아무도 안 읽는다.
 */
import { useLang } from "@/lib/i18n";
import { Icon, iconOfAgent } from "./icons";
import { useEffect, useRef, useState } from "react";

import type { BusEvent, Roster } from "@/lib/types";

const KIND_COLOR: Record<string, string> = {
  say: "var(--fg)",
  tool: "var(--muted)",
  verdict: "var(--ok)",
  error: "var(--bad)",
};

export function ChatLog({
  events,
  roster,
  connected,
  polling,
  className = "",
}: {
  events: BusEvent[];
  roster: Roster;
  connected: boolean;
  polling: boolean;
  className?: string;
}) {
  const { t } = useLang();
  const box = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(true);
  // 마지막으로 사용자가 본 이벤트 id. **이벤트 핸들러에서만** 갱신한다 —
  // effect 안에서 setState 를 부르면 새 줄이 올 때마다 렌더가 두 번 돈다.
  // 바닥에 붙어 있는 동안은 안 읽은 게 0 이므로 갱신할 필요도 없다.
  const [seenId, setSeenId] = useState(0);

  const rows = events.filter(
    (e) => e.type === "message" || e.type === "phase" || e.type === "done",
  );
  const lastId = rows.length ? rows[rows.length - 1].id : 0;
  // 안 읽은 수는 상태가 아니라 **계산 결과**다. 따로 세면 두 값이 어긋난다.
  const unread = stuck ? 0 : rows.filter((e) => e.id > seenId).length;

  useEffect(() => {
    const el = box.current;
    if (!el || !stuck) return;
    el.scrollTop = el.scrollHeight;
  }, [lastId, stuck]);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom) setSeenId(lastId);
    setStuck(atBottom);
  };

  const toBottom = () => {
    const el = box.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setSeenId(lastId);
    setStuck(true);
  };

  return (
    <div className={`relative flex min-h-0 flex-col ${className}`}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-2 text-xs">
        <span
          className="inline-block size-2 rounded-full"
          style={{ background: connected ? "var(--ok)" : "var(--bad)" }}
          aria-hidden
        />
        <span className="text-muted">
          {connected ? t("log.connected") : t("log.disconnected")}
        </span>
        {polling && (
          // 폴백으로 떨어진 사실을 감추면, 왜 로그가 느린지 아무도 모른다.
          <span className="text-dim">{t("log.polling")}</span>
        )}
        <span className="ml-auto text-dim">{t("log.lines", { n: rows.length })}</span>
      </div>

      <div
        ref={box}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
      >
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-dim">
            {t("log.empty")}
          </p>
        ) : (
          <ol className="space-y-2">
            {rows.map((e) => (
              <Row key={e.id} e={e} roster={roster} />
            ))}
          </ol>
        )}
      </div>

      {unread > 0 && (
        <button
          type="button"
          onClick={toBottom}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border
            border-line bg-panel2 px-3 py-1 text-xs shadow-lg"
        >
          {t("log.unread", { n: unread })}
        </button>
      )}
    </div>
  );
}

function Row({ e, roster }: { e: BusEvent; roster: Roster }) {
  const { t } = useLang();
  if (e.type === "phase") {
    return (
      <li className="flex items-center gap-2 py-1 text-[11px] text-dim">
        <span className="h-px flex-1 bg-line" />
        <span className="uppercase tracking-wide">
          {e.name}
          {e.detail ? ` · ${e.detail}` : ""}
        </span>
        <span className="h-px flex-1 bg-line" />
      </li>
    );
  }

  if (e.type === "done") {
    return (
      <li
        className="rounded-lg border px-3 py-2 text-sm"
        style={{
          borderColor: e.ok
            ? "color-mix(in srgb, var(--ok) 40%, transparent)"
            : "color-mix(in srgb, var(--bad) 40%, transparent)",
          background: e.ok
            ? "color-mix(in srgb, var(--ok) 8%, transparent)"
            : "color-mix(in srgb, var(--bad) 8%, transparent)",
        }}
      >
        <strong>{e.ok ? t("log.done") : t("log.stopped")}</strong>
        {typeof e.score === "number" && t("log.scoreSuffix", { n: e.score })}
        <p className="mt-1 text-muted">{e.summary}</p>
        {e.unmet && e.unmet.length > 0 && (
          <p className="mt-1 text-xs" style={{ color: "var(--warn)" }}>
            {t("proj.unmet")}: {e.unmet.join(", ")}
          </p>
        )}
      </li>
    );
  }

  const who = roster[e.agent ?? ""] ?? { name: e.agent ?? "?" };
  const color = KIND_COLOR[e.kind ?? "say"] ?? "var(--fg)";
  const accent = `var(--${e.agent}, var(--accent))`;

  return (
    <li className="flex gap-2.5">
      <span className="mt-0.5 leading-none" style={{ color: accent }}>
        <Icon name={iconOfAgent(e.agent ?? "")} size={16} />
      </span>
      <div className="min-w-0 flex-1">
        <span className="text-xs font-semibold" style={{ color: accent }}>
          {who.name}
        </span>
        <p
          className={`whitespace-pre-wrap break-words text-sm ${
            e.kind === "tool" ? "font-mono text-xs" : ""
          }`}
          style={{ color }}
        >
          {e.text}
        </p>
      </div>
    </li>
  );
}
