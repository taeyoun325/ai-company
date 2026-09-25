"use client";

/**
 * 실시간 작업 로그 (지시서 §13 · DAY 24 개편).
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
 *
 * ## 단계 단위로 접는다 (DAY 24)
 *
 * 직원 다섯 명이 실시간으로 떠드는 원문을 그대로 쌓으면, CEO 는 "지금
 * 무슨 일이 벌어지고 있나"를 알려고 스무 줄을 읽어야 한다. 그래서
 * `phase` 이벤트가 올 때마다 새 묶음을 시작하고, 그 사이의 말풍선은
 * 묶음 안에 접어 넣는다. 기본으로 보이는 건 헤드라인 한 줄
 * ("분석가 완료 — 개발자에게 전달")뿐이고, 화살표를 누르면 그 구간의
 * 원문이 펼쳐진다. 헤드라인은 백엔드가 규칙으로 만든다(app/bus.py) —
 * 모델을 불러 매 줄을 요약하면 비용이 끝없이 나간다.
 *
 * 지금 도는 구간과 문제(error)가 있는 구간은 처음부터 펼쳐 보인다 —
 * "지금 뭘 하고 있나"와 "뭐가 잘못됐나"는 접어두면 안 되는 정보다.
 */
import { api } from "@/lib/api";
import { useErrorText, useLang } from "@/lib/i18n";
import { T, animate, prefersReducedMotion } from "@/lib/motion";
import { Icon, iconOfAgent } from "./icons";
import { useEffect, useRef, useState } from "react";

import type { BusEvent, Roster } from "@/lib/types";
import { eventKey } from "@/lib/useStream";

/** `phase` 이벤트 하나와 그 뒤에 딸린 `message` 들의 묶음.
 *  첫 단계 전에 온 말(요구사항·첨부 안내)은 `phase` 가 없다 —
 *  짧고 항상 중요해서 접지 않고 그대로 보여준다. */
interface Segment {
  key: string;
  phase?: BusEvent;
  messages: BusEvent[];
}

function buildSegments(rows: BusEvent[]): Segment[] {
  const segments: Segment[] = [];
  let current: Segment = { key: "intro", messages: [] };
  for (const e of rows) {
    if (e.type === "phase") {
      if (current.phase || current.messages.length > 0) segments.push(current);
      current = { key: `phase-${eventKey(e)}`, phase: e, messages: [] };
    } else if (e.type === "message") {
      current.messages.push(e);
    }
  }
  if (current.phase || current.messages.length > 0) segments.push(current);
  return segments;
}

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
  past = false,
  slug,
}: {
  events: BusEvent[];
  roster: Roster;
  connected: boolean;
  polling: boolean;
  className?: string;
  /** 이미 끝난 실행을 보고 있는가. 빈 칸의 뜻이 달라진다. */
  past?: boolean;
  /** 있으면 "쉽게 설명" 버튼이 뜬다(DAY 23 · app/narrator.py).
   *  없는 화면(예: 프로젝트 없이 로그만 보여줄 때)에는 버튼을 숨긴다 —
   *  누를 수 없는 버튼을 보여주는 것보다 없는 편이 낫다. */
  slug?: string | null;
}) {
  const { t } = useLang();
  const errText = useErrorText();
  const box = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(true);
  // 마지막으로 사용자가 본 이벤트 id. **이벤트 핸들러에서만** 갱신한다 —
  // effect 안에서 setState 를 부르면 새 줄이 올 때마다 렌더가 두 번 돈다.
  // 바닥에 붙어 있는 동안은 안 읽은 게 0 이므로 갱신할 필요도 없다.
  const [seenId, setSeenId] = useState(0);

  // "쉽게 설명" (DAY 23). 검증(§11)과 같은 규칙으로 CEO 가 누를 때만
  // 돈다 — 로그가 늘어날 때마다 자동으로 부르면 아무도 안 보는 요약에
  // 계속 비용이 나간다.
  const [narration, setNarration] = useState<string | null>(null);
  const [narrating, setNarrating] = useState(false);
  const [narrateError, setNarrateError] = useState<string | null>(null);

  const explain = async (force: boolean) => {
    if (!slug || narrating) return;
    setNarrating(true);
    setNarrateError(null);
    try {
      const out = await api.narrate(slug, force);
      setNarration(out.text);
    } catch (e) {
      // 서버 문장을 그대로 쓴다 — "아직 설명할 로그가 없습니다"부터
      // 예산 상한까지, 이미 화면 언어로 온다.
      setNarrateError(errText(e));
    } finally {
      setNarrating(false);
    }
  };

  const rows = events.filter(
    (e) => e.type === "message" || e.type === "phase" || e.type === "done",
  );
  const lastId = rows.length ? rows[rows.length - 1].id : 0;
  // 안 읽은 수는 상태가 아니라 **계산 결과**다. 따로 세면 두 값이 어긋난다.
  const unread = stuck ? 0 : rows.filter((e) => e.id > seenId).length;

  // done 은 묶음에 넣지 않는다 — 실행 전체의 마지막 결과이지 어느 한
  // 단계에 속한 게 아니다. 늘 펼쳐진 카드로 맨 끝에 따로 둔다.
  const segments = buildSegments(rows.filter((e) => e.type !== "done"));
  const doneRows = rows.filter((e) => e.type === "done");

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
    // `data-record` — 이 안의 글은 **기록**이다. 만들 때의 언어로 남는다
    // (번역이 아니라 이력). 화면 시험이 "영어 화면에 한국어가 남았나"를 볼 때 뺀다.
    <div data-record className={`relative flex min-h-0 flex-col ${className}`}>
      {/* 좁은 칸에서는 줄을 바꾼다 — 안 바꾸면 글자가 한 자씩 세로로 쌓인다. */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line
        px-4 py-2 text-xs">
        <span
          className="inline-block size-2 shrink-0 rounded-full"
          style={{ background: connected ? "var(--ok)" : "var(--bad)" }}
          aria-hidden
        />
        <span className="whitespace-nowrap text-muted">
          {connected ? t("log.connected") : t("log.disconnected")}
        </span>
        {polling && (
          // 폴백으로 떨어진 사실을 감추면, 왜 로그가 느린지 아무도 모른다.
          <span className="whitespace-nowrap text-dim">{t("log.polling")}</span>
        )}
        <span className="whitespace-nowrap text-dim">
          {t("log.lines", { n: rows.length })}
        </span>
        {slug && (
          <button
            type="button"
            onClick={() => void explain(!!narration)}
            disabled={narrating}
            className="ml-auto flex shrink-0 items-center gap-1 rounded-full
              border border-line bg-panel2 px-2 py-0.5 text-[11px]
              text-muted transition hover:border-accent hover:text-fg
              disabled:opacity-60"
          >
            {narrating
              ? t("narrate.loading")
              : narration
                ? t("narrate.buttonAgain")
                : t("narrate.button")}
          </button>
        )}
      </div>

      {/* 로그를 지우거나 대신하지 않는다 — 옆에 문단 하나를 더할 뿐이다
          (app/narrator.py). 목록 위에 고정해 스크롤해도 안 밀려나간다. */}
      {(narration || narrateError) && (
        <div
          className="border-b border-line px-4 py-2.5 text-sm"
          style={narrateError
            ? { color: "var(--bad)" }
            : { background: "color-mix(in srgb, var(--accent) 6%, transparent)" }}
        >
          {narrateError ?? (
            <>
              <p className="leading-relaxed">{narration}</p>
              <p className="mt-1 text-[10px] text-dim">{t("narrate.hint")}</p>
            </>
          )}
        </div>
      )}

      <div
        ref={box}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
      >
        {rows.length === 0 ? (
          <p className="mx-auto max-w-sm py-8 text-center text-sm leading-relaxed
            text-dim">
            {past ? t("log.past") : t("log.empty")}
          </p>
        ) : (
          <ol className="space-y-2">
            {segments.map((seg, i) => (
              <SegmentRow
                key={seg.key}
                seg={seg}
                roster={roster}
                // 지금 도는 구간(맨 끝)은 처음부터 펼쳐 보인다.
                defaultOpen={i === segments.length - 1}
              />
            ))}
            {doneRows.map((e) => (
              <Row key={eventKey(e)} e={e} roster={roster} />
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

/**
 * 단계 하나의 묶음. 기본은 헤드라인 한 줄이고, 화살표를 누르면 그 구간의
 * 원문(말풍선)이 펼쳐진다.
 */
function SegmentRow({
  seg, roster, defaultOpen,
}: {
  seg: Segment; roster: Roster; defaultOpen: boolean;
}) {
  const { t } = useLang();
  const hasError = seg.messages.some((m) => m.kind === "error");
  const [openState, setOpenState] = useState(defaultOpen);
  // 문제가 있는 구간은 접어뒀어도 강제로 펼친다 — 사용자가 방금 닫았다면
  // 존중하지만(state), 처음 그릴 때는 항상 드러난다.
  const open = openState || hasError;

  // 펼치는 애니메이션은 **사용자가 화살표를 눌렀을 때만** 튼다. 지금 도는
  // 구간처럼 처음부터 펼쳐진 채로 그려지거나, 새 줄이 스트리밍되며
  // 계속 다시 그려질 때마다 움직이면 그게 소음이다.
  const detail = useRef<HTMLOListElement>(null);
  const userToggled = useRef(false);
  useEffect(() => {
    const el = detail.current;
    if (!el || !open || !userToggled.current || prefersReducedMotion()) return;
    userToggled.current = false;
    animate(el, {
      opacity: [0, 1], translateY: [-6, 0], duration: T.fast, ease: T.ease,
    });
  }, [open]);

  if (!seg.phase) {
    // 첫 단계 전의 말(요구사항 등)은 짧고 항상 중요하다 — 접지 않는다.
    return (
      <>
        {seg.messages.map((m) => (
          <Row key={eventKey(m)} e={m} roster={roster} />
        ))}
      </>
    );
  }

  const headline = seg.phase.headline
    ?? `${seg.phase.name ?? ""}${seg.phase.detail ? ` · ${seg.phase.detail}` : ""}`;

  return (
    <li>
      <button
        type="button"
        onClick={() => {
          userToggled.current = true;
          setOpenState((v) => !v);
        }}
        disabled={hasError}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg py-1 text-left
          text-[12px] text-muted transition hover:text-fg disabled:cursor-default"
      >
        <span
          className="shrink-0 text-[9px] transition-transform"
          style={{ transform: open ? "rotate(90deg)" : "none" }}
          aria-hidden
        >
          ▸
        </span>
        <span className="min-w-0 flex-1 truncate font-medium">{headline}</span>
        {seg.messages.length > 0 && (
          <span className="shrink-0 text-[10px] text-dim">
            {t("log.stepLines", { n: seg.messages.length })}
          </span>
        )}
      </button>
      {open && (
        <ol ref={detail} className="ml-4 space-y-2 border-l border-line py-1 pl-3">
          <li className="flex items-center gap-2 text-[10px] uppercase tracking-wide
            text-dim">
            {seg.phase.name}
            {seg.phase.detail ? ` · ${seg.phase.detail}` : ""}
          </li>
          {seg.messages.map((m) => (
            <Row key={eventKey(m)} e={m} roster={roster} />
          ))}
        </ol>
      )}
    </li>
  );
}

function ConfidenceChip({ value }: { value: number }) {
  const { t } = useLang();
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "var(--st-done)" : pct >= 60 ? "var(--st-working)"
    : "var(--bad)";
  return (
    <span className="mt-1 inline-flex items-center gap-1 rounded-full border px-2 py-0.5
      text-[10px] font-medium" title={t("task.confidenceHint")}
      style={{ borderColor: color, color }}>
      {t("log.confidence", { n: pct })}
      {pct < 60 && <span>· {t("task.lowConfidence")}</span>}
    </span>
  );
}

function Row({ e, roster }: { e: BusEvent; roster: Roster }) {
  const { t } = useLang();
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
        {/* 검증자가 이 판정을 얼마나 확신했나 (§18 신뢰도 · DAY 25).
            낮으면 "사람 확인 권장"을 붙인다 — 확신도 게이트를 켜두면
            이런 통과는 결재함으로 간다. */}
        {e.kind === "verdict" && typeof e.confidence === "number" && (
          <ConfidenceChip value={e.confidence} />
        )}
      </div>
    </li>
  );
}
