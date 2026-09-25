"use client";

/**
 * 사무실 평면도 (DAY 25 · 사규 §1–§3).
 *
 * ## 무엇을 보여주나
 *
 * 부서마다 자리가 있고, 위쪽에 대표실 · 회의실 · 비서실, 오른쪽에 휴게실,
 * 아래에 입구가 있다. 직원은 **걸어서** 옮긴다 — 자리에서 일하고, 결재를
 * 기다릴 때는 회의실로 가고, 할 일이 없으면 휴게실에 들른다.
 *
 * 상태 다섯 가지의 색·말풍선은 사규 그대로다. 상태와 이유는 **서버가
 * 정한다**(backend/app/office.py) — 여기서는 그리기만 한다.
 *
 * ## 움직임은 규칙을 따른다
 *
 * - 승인 대기 → 회의실에서 실제로 기다린다.
 * - 인계(handoff)가 일어나면 두 사람이 회의실에서 잠깐 마주 앉고, 넘기는
 *   쪽이 **한 줄만** 말한다.
 * - "회의 소집" 이면 전원이 모여 한 명씩 순서대로 한 줄씩 말한다.
 * - 할 일 없는 직원만 자율 행동(혼잣말 · 휴게실)을 한다. 회의 중이거나
 *   집중 모드면 하지 않는다. 자율 행동에는 "자율" 표시를 붙인다 — 일하는
 *   것처럼 보이면 안 된다.
 * - 실행이 막 시작되면 전원이 입구에서 각자 자리로 걸어 들어간다(출근).
 *
 * ## 좁은 화면
 *
 * 폰에서는 평면도의 칸이 너무 좁아 말풍선이 겹친다. 같은 정보를 부서별
 * 목록으로 그린다 — DAY 22 에 "폰에서는 사무실이 안 보였다"를 한 번 겪었다.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { type Key, useLang } from "@/lib/i18n";
import type { BusEvent, OfficeEmployee, OfficeSnapshot } from "@/lib/types";
import { Icon, iconOfAgent } from "../icons";
import { MockBadge } from "../ui";

export const STATE_COLOR: Record<OfficeEmployee["state"], string> = {
  done: "var(--st-done)",
  working: "var(--st-working)",
  approval: "var(--st-approval)",
  integration: "var(--st-integration)",
  idle: "var(--st-idle-ring)",
};

type Pt = { x: number; y: number };

// 자리 배치 — 평면도 전체를 100×100 으로 본 좌표(%).
const DESK: Record<string, Pt> = {
  strategist: { x: 8.5, y: 62 },
  analyst: { x: 25.5, y: 62 },
  developer: { x: 42.5, y: 62 },
  writer: { x: 59.5, y: 62 },
  designer: { x: 76.5, y: 62 },
};
const DEPT_ROOMS = [
  { id: "strategist", dept: "strategy", x: 0, w: 17 },
  { id: "analyst", dept: "qa", x: 17, w: 17 },
  { id: "developer", dept: "dev", x: 34, w: 17 },
  { id: "writer", dept: "docs", x: 51, w: 17 },
  { id: "designer", dept: "design", x: 68, w: 17 },
];
// 회의실 좌석 — 탁자(가운데) 위아래 두 줄. 말풍선이 옆 사람과 겹치지 않게
// 가로 간격을 탁자 폭만큼 벌린다.
const SEATS: Pt[] = [
  { x: 36, y: 12 }, { x: 50, y: 12 }, { x: 64, y: 12 },
  { x: 36, y: 31 }, { x: 50, y: 31 }, { x: 64, y: 31 },
];
const LOUNGE: Pt[] = [{ x: 92.5, y: 50 }, { x: 92.5, y: 66 }, { x: 92.5, y: 80 }];
const ENTRANCE: Pt = { x: 50, y: 97 };
const CEO: Pt = { x: 13, y: 19 };
const SECRETARY: Pt = { x: 87, y: 19 };

export const BUBBLE_KEY: Record<OfficeEmployee["state"], Key> = {
  done: "office.bubble.done",
  working: "office.bubble.working",
  approval: "office.bubble.approval",
  integration: "office.bubble.integration",
  idle: "office.bubble.idle",
};

/** 인계 한 건을 한 줄로 접는다 — 넘기는 쪽이 말하는 한 줄. */
function handoffLine(h: BusEvent, t: (k: Key, v?: Record<string, string | number>) => string) {
  switch (h.phase) {
    case "PLAN":
      return t("handoff.plan", { n: h.task_titles?.length ?? 0 });
    case "WRITE_TESTS":
      return t("handoff.writeTests", { n: h.covered?.length ?? 0 });
    case "IMPLEMENT":
      return h.summary || t("handoff.implement");
    case "REVIEW":
      return h.verdict === "pass"
        ? t("handoff.reviewPass")
        : t("handoff.reviewFail", { n: h.findings?.length ?? 0 });
    default:
      return h.phase ?? "";
  }
}

export interface MeetingCall {
  /** 회의 소집 — 전원이 모여 한 줄씩. 끝나면 null 로 돌린다. */
  who: string[];
  lines: { who: string; text: string }[];
  startedAt: number;
}

const HANDOFF_MEETING_MS = 5500;
const LINE_EVERY_MS = 1300;

export function OfficeFloor({
  snap, events, focus, meetingCall, selected, onSelect, arrivalKey, still = false,
}: {
  snap: OfficeSnapshot;
  events: BusEvent[];
  focus: boolean;
  /** 자율 행동을 아예 끈다 — 직원을 지목하는 화면(MANUAL)에서 사람이
   *  돌아다니면 누르기 어렵다. 집중 모드와 달리 표시를 달지 않는다. */
  still?: boolean;
  meetingCall: MeetingCall | null;
  selected: string | null;
  onSelect: (id: string | null) => void;
  /** 바뀌면 전원이 입구에서 출근한다(새 실행이 시작됐을 때). */
  arrivalKey: string | null;
}) {
  const { t } = useLang();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // ── 출근 ───────────────────────────────────────────────────────
  const [arriving, setArriving] = useState(false);
  const seenArrival = useRef<string | null>(null);
  useEffect(() => {
    if (!arrivalKey || seenArrival.current === arrivalKey) return;
    seenArrival.current = arrivalKey;
    // 한 프레임 입구에 세웠다가 자리로 보낸다 — 트랜지션이 걷는 모습이 된다.
    const a = setTimeout(() => setArriving(true), 0);
    const b = setTimeout(() => setArriving(false), 80);
    return () => {
      clearTimeout(a);
      clearTimeout(b);
    };
  }, [arrivalKey]);

  // ── 인계 회의 ──────────────────────────────────────────────────
  const ids = useMemo(() => new Set(snap.employees.map((e) => e.id)), [snap.employees]);
  const handoff = useMemo(() => {
    const hs = events.filter((e) => e.type === "handoff" && e.from && e.to
      && ids.has(e.from) && ids.has(e.to));
    return hs.length ? hs[hs.length - 1] : null;
  }, [events, ids]);
  const handoffLive = handoff && now - handoff.ts * 1000 < HANDOFF_MEETING_MS
    ? handoff : null;

  // ── 자율 행동 ──────────────────────────────────────────────────
  const tick = Math.floor(now / 9000);
  const inCall = meetingCall
    && now - meetingCall.startedAt < meetingCall.lines.length * LINE_EVERY_MS + 3000;

  const places = useMemo(() => {
    const out: Record<string, { pt: Pt; mode: "desk" | "meeting" | "lounge" | "away";
      line?: string; self?: boolean }> = {};
    let seat = 0;
    let lounge = 0;
    const meet = new Set<string>();
    snap.employees.filter((e) => e.place === "meeting").forEach((e) => meet.add(e.id));
    if (inCall) meetingCall!.who.forEach((w) => meet.add(w));
    if (handoffLive) {
      meet.add(handoffLive.from!);
      meet.add(handoffLive.to!);
    }
    for (const e of snap.employees) {
      if (!e.hired) {
        out[e.id] = { pt: DESK[e.id] ?? ENTRANCE, mode: "away" };
        continue;
      }
      if (arriving) {
        out[e.id] = { pt: ENTRANCE, mode: "desk" };
        continue;
      }
      if (meet.has(e.id)) {
        out[e.id] = { pt: SEATS[seat++ % SEATS.length], mode: "meeting" };
        continue;
      }
      const free = (e.state === "idle" || e.state === "done") && !focus && !still;
      if (free) {
        const roll = hash(`${e.id}:${tick}`) % 4;
        if (roll === 0) {
          out[e.id] = { pt: LOUNGE[lounge++ % LOUNGE.length], mode: "lounge", self: true };
          continue;
        }
        if (roll === 1) {
          out[e.id] = { pt: DESK[e.id], mode: "desk", self: true,
                        line: t(`office.catch.${e.id}.${tick % 2 ? 1 : 2}` as Key) };
          continue;
        }
      }
      out[e.id] = { pt: DESK[e.id] ?? ENTRANCE, mode: "desk" };
    }
    return out;
  }, [snap.employees, arriving, inCall, meetingCall, handoffLive, focus, still, tick, t]);

  // ── 회의실에서 지금 말하는 한 줄 ────────────────────────────────
  const speaking = useMemo(() => {
    if (inCall && meetingCall) {
      const i = Math.floor((now - meetingCall.startedAt) / LINE_EVERY_MS);
      return meetingCall.lines.slice(0, Math.min(i + 1, meetingCall.lines.length));
    }
    if (handoffLive) {
      return [{ who: handoffLive.from!, text: handoffLine(handoffLive, t) }];
    }
    return [];
  }, [inCall, meetingCall, now, handoffLive, t]);
  const lastSpeaker = speaking.length ? speaking[speaking.length - 1] : null;

  const approval = snap.approvals[0];

  return (
    <>
      {/* 넓은 화면 — 평면도 */}
      {/* `@container` — 말풍선이 자리 폭(17%)을 넘지 않게 `cqw` 로 잰다 (DAY 26).
          고정 132px 이면 1280px 화면에서 옆자리 말풍선과 겹쳤다. */}
      <div className="@container glass glass-lit relative hidden aspect-[16/10] min-h-[380px]
        w-full overflow-hidden sm:block" role="group" aria-label={t("office.floor.alt")}>
        <Rooms approval={!!approval} t={t} />

        {/* 회의실 탁자와 지금 말하는 한 줄 */}
        <div className="absolute left-1/2 top-[21%] -translate-x-1/2 -translate-y-1/2
          rounded-full border px-6 py-2.5 text-center"
          style={{ borderColor: "var(--room-line)", background: "var(--floor)" }}>
          <span className="block max-w-[220px] truncate text-[10px] text-dim">
            {approval
              ? t("office.meeting.approval", { title: approval.title })
              : inCall ? t("office.meeting.call")
                : handoffLive ? t("office.meeting.handoff") : t("office.meeting.empty")}
          </span>
        </div>
        {/* 비서실이 회의를 닫는 한 줄은 비서실 자리에서 말한다. */}
        {lastSpeaker?.who === "secretary" && (
          <Speech at={SECRETARY} text={lastSpeaker.text} who="secretary"
            name={nameOf("secretary", snap, t)} />
        )}

        {/* 대표 · 비서실 */}
        <Fixture pt={CEO} icon="person" label={t("office.ceo")}
          badge={snap.approvals.length || undefined}
          pulse={!!approval} />
        <Fixture pt={SECRETARY} icon="system" label={t("office.secretary")} />
        <span className="sr-only" aria-live="polite">
          {lastSpeaker ? `${nameOf(lastSpeaker.who, snap, t)}: ${lastSpeaker.text}` : ""}
        </span>

        {/* 직원 */}
        {snap.employees.map((e) => {
          const p = places[e.id];
          if (!p) return null;
          return (
            <Token key={e.id} e={e} at={p.pt} mode={p.mode}
              line={p.line} self={p.self} now={now} snapNow={snap.now}
              speech={lastSpeaker?.who === e.id ? lastSpeaker.text : null}
              quiet={p.mode === "meeting" && e.state !== "approval"
                && lastSpeaker?.who !== e.id}
              selected={selected === e.id}
              onClick={() => onSelect(selected === e.id ? null : e.id)} />
          );
        })}

        {focus && (
          <span className="absolute right-3 top-3 rounded-full px-2 py-0.5 text-[10px]
            font-semibold" style={{ background: "var(--st-working)", color: "#111" }}>
            {t("office.focusOn")}
          </span>
        )}
      </div>

      {/* 좁은 화면 — 부서별 목록 */}
      <ul className="glass glass-lit divide-y divide-line sm:hidden">
        {approval && (
          <li className="px-3 py-2 text-xs" style={{ color: "var(--st-approval)" }}>
            {t("office.meeting.approval", { title: approval.title })}
          </li>
        )}
        {snap.employees.map((e) => (
          <li key={e.id}>
            <button type="button" onClick={() => onSelect(selected === e.id ? null : e.id)}
              className="flex w-full items-start gap-3 px-3 py-2.5 text-left">
              <Avatar e={e} size={34} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  {e.name}
                  <span className="text-[11px] text-dim">
                    {t(`office.dept.${e.dept}` as Key)}
                  </span>
                  {e.mock && <MockBadge className="scale-90" />}
                </span>
                <span className="block text-[11px] font-semibold"
                  style={{ color: STATE_COLOR[e.state] }}>
                  {t(`office.state.${e.state}` as Key)} · {t(BUBBLE_KEY[e.state])}
                </span>
                <span className="block text-[11px] text-muted">{e.reason}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function nameOf(id: string, snap: OfficeSnapshot,
                t: (k: Key, v?: Record<string, string | number>) => string) {
  if (id === "secretary") return t("office.secretary");
  return snap.employees.find((e) => e.id === id)?.name ?? id;
}

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** 방 경계와 이름. 장식이 아니라 "어디에 있나"를 읽는 격자다. */
function Rooms({ approval, t }: {
  approval: boolean;
  t: (k: Key, v?: Record<string, string | number>) => string;
}) {
  const box = (x: number, y: number, w: number, h: number) => ({
    left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`,
  });
  const label = "absolute left-2 top-1.5 text-[10px] font-semibold tracking-wide text-dim";
  const room = "absolute border";
  const style = { borderColor: "var(--room-line)", background: "var(--floor)" };
  return (
    <div aria-hidden>
      <div className={room} style={{ ...style, ...box(0, 0, 26, 38) }}>
        <span className={label}>{t("office.room.ceo")}</span>
      </div>
      <div className={`${room} ${approval ? "approval-pulse" : ""}`}
        style={{ ...style, ...box(26, 0, 48, 38),
                 borderColor: approval ? "var(--st-approval)" : "var(--room-line)" }}>
        <span className={label}>{t("office.room.meeting")}</span>
      </div>
      <div className={room} style={{ ...style, ...box(74, 0, 26, 38) }}>
        <span className={label}>{t("office.room.secretary")}</span>
      </div>
      {DEPT_ROOMS.map((r) => (
        <div key={r.id} className={room}
          style={{ ...style, ...box(r.x, 38, r.w, 50) }}>
          <span className={label} style={{ color: `var(--${r.id})` }}>
            {t(`office.dept.${r.dept}` as Key)}
          </span>
        </div>
      ))}
      <div className={room} style={{ ...style, ...box(85, 38, 15, 50) }}>
        <span className={label}>{t("office.room.lounge")}</span>
      </div>
      <div className="absolute bottom-0 left-0 right-0 flex h-[12%] items-end
        justify-center pb-1 text-[9px] uppercase tracking-[0.2em] text-dim">
        {t("office.room.entrance")}
      </div>
    </div>
  );
}

function Fixture({ pt, icon, label, badge, pulse }: {
  pt: Pt; icon: "person" | "system"; label: string; badge?: number; pulse?: boolean;
}) {
  return (
    <div className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center"
      style={{ left: `${pt.x}%`, top: `${pt.y}%` }}>
      <span className={`relative grid size-10 place-items-center rounded-full border-2
        bg-[color:var(--panel-solid)] ${pulse ? "approval-pulse" : ""}`}
        style={{ borderColor: pulse ? "var(--st-approval)" : "var(--line-strong)" }}>
        <Icon name={icon} size={20} className="text-muted" />
        {badge ? (
          <span className="absolute -right-1.5 -top-1.5 grid min-w-5 place-items-center
            rounded-full px-1 text-[10px] font-bold text-white"
            style={{ background: "var(--st-approval)" }}>
            {badge}
          </span>
        ) : null}
      </span>
      <span className="mt-1 text-[10px] text-dim">{label}</span>
    </div>
  );
}

export function Avatar({ e, size = 40 }: { e: OfficeEmployee; size?: number }) {
  return (
    <span className={`relative grid shrink-0 place-items-center rounded-full border-[3px]
      bg-[color:var(--panel-solid)] ${e.state === "working" ? "working" : ""}
      ${e.state === "approval" ? "approval-pulse" : ""}`}
      style={{ width: size, height: size, borderColor: STATE_COLOR[e.state],
               ["--c" as string]: STATE_COLOR[e.state],
               opacity: e.hired ? 1 : 0.35 }}>
      <Icon name={iconOfAgent(e.id)} size={Math.round(size * 0.5)}
        style={{ color: `var(--${e.id}, var(--muted))` }} />
    </span>
  );
}

/** 회의에서 지금 말하는 한 줄 — 말하는 사람 머리 위에 조금 넓게. */
function Speech({ at, text, who, name }: {
  at: Pt; text: string; who: string; name: string;
}) {
  return (
    <span key={text}
      className="bubble absolute z-30 w-[220px] rounded-xl border px-2.5 py-1.5
        text-[11px] leading-snug shadow-lg"
      style={{ left: `${at.x}%`, top: `calc(${at.y}% - 64px)`,
               transform: "translateX(-50%)", background: "var(--panel-solid)",
               borderColor: `var(--${who}, var(--line-strong))` }}>
      <b className="mr-1" style={{ color: `var(--${who}, var(--muted))` }}>{name}</b>
      <span className="line-clamp-2 text-muted">{text}</span>
    </span>
  );
}

function Token({ e, at, mode, line, self, now, snapNow, selected, onClick,
                 speech = null, quiet = false }: {
  e: OfficeEmployee; at: Pt; mode: "desk" | "meeting" | "lounge" | "away";
  line?: string; self?: boolean; now: number; snapNow: number;
  selected: boolean; onClick: () => void;
  /** 회의에서 지금 이 사람이 말하는 한 줄. */
  speech?: string | null;
  /** 회의 중 말하지 않는 사람 — 말풍선을 접는다(한 명씩만 말한다). */
  quiet?: boolean;
}) {
  const { t } = useLang();
  // 모델 응답을 기다린 시간 — 서버가 준 값에 그 뒤로 흐른 시간을 더한다.
  const waited = e.inflight_ms != null
    ? Math.max(0, Math.round((e.inflight_ms + (now - snapNow * 1000)) / 1000)) : null;
  const bubble = mode === "lounge" ? t("office.bubble.lounge")
    : line ?? t(BUBBLE_KEY[e.state]);
  return (
    <button type="button" onClick={onClick}
      title={`${e.name} · ${t(`office.state.${e.state}` as Key)} — ${e.reason}`}
      aria-label={`${e.name}: ${t(`office.state.${e.state}` as Key)} — ${e.reason}`}
      className="walker absolute z-10 flex w-[120px] -translate-x-1/2 -translate-y-1/2
        flex-col items-center"
      style={{ left: `${at.x}%`, top: `${at.y}%` }}>
      {speech && (
        <span key={speech}
          className={`bubble absolute left-1/2 z-30 w-[220px] rounded-xl border
            px-2.5 py-1.5 text-left text-[11px] leading-snug shadow-lg
            ${mode === "meeting" && at.y > 20 ? "top-full mt-1" : "-top-14"}`}
          style={{ background: "var(--panel-solid)",
                   borderColor: `var(--${e.id}, var(--line-strong))` }}>
          <span className="line-clamp-2 text-fg">{speech}</span>
        </span>
      )}
      {mode !== "away" && !speech && !quiet && (
        <span key={bubble}
          className={`bubble absolute -top-9 left-1/2 max-w-[min(132px,16cqw)] truncate rounded-lg border
            px-2 py-0.5 text-[10px] shadow ${self ? "italic" : "font-medium"}`}
          style={{
            background: "var(--panel-solid)",
            borderColor: self ? "var(--line)" : STATE_COLOR[e.state],
            color: self ? "var(--muted)" : "var(--fg)",
          }}>
          {self && <span className="mr-1 not-italic text-dim">{t("office.self")}</span>}
          {bubble}
        </span>
      )}
      <span className={`rounded-full ${selected ? "ring-2 ring-offset-2 ring-[color:var(--accent)]"
        : ""}`} style={{ ["--tw-ring-offset-color" as string]: "var(--bg)" }}>
        <Avatar e={e} />
      </span>
      <span className="mt-1 flex items-center gap-1 text-[11px] font-medium">
        {e.name}
        {e.mock && <span className="text-[9px] font-bold" style={{ color: "var(--mock)" }}>M</span>}
      </span>
      {mode !== "away" && e.state === "working" && e.task?.title && (
        <span className="max-w-[min(118px,16cqw)] truncate text-[10px] text-dim">
          {e.task.title}
        </span>
      )}
      {waited != null && (
        <span className="text-[10px] tabular-nums" style={{ color: "var(--st-working)" }}>
          ⏱ {waited}s
        </span>
      )}
    </button>
  );
}
