"use client";

/**
 * 도트 사무실 — 위에서 내려다본 방 (DAY 22 · 지시서 §4).
 *
 * ## 왜 위에서 보나
 *
 * 옆에서 본 그림은 책상 다섯 개를 한 줄로 세워야 하고, 그러면 **방이
 * 아니라 띠**가 된다. 위에서 보면 자리 배치·회의 탁자·빈 자리가 한
 * 화면에 들어오고, "회사가 이렇게 생겼다"가 한 번에 읽힌다.
 *
 * ## 왜 둥근 탁자에 모여 앉나
 *
 * 각자 벽을 보고 앉아 있으면 다섯 명이 **각자 일하는 그림**이다. 이
 * 제품이 파는 것은 그 반대다 — 기획한 사람이 넘기고, 검증자가 되돌리고,
 * 다시 고쳐 오는 **협업**이다. 한 탁자에 둘러앉히면 그 관계가 배치로
 * 보인다. 개인 책상은 벽 쪽에 그대로 두었다. 회의만 하는 회사는 없다.
 *
 * ## 머리 자리에 제공자 마크가 있다
 *
 * 이 제품의 핵심 주장은 **구현자와 검증자가 다른 회사의 모델**이라는
 * 것이다(§8). 글로 적어두면 읽는 사람만 알지만, 자리마다 마크가 박혀
 * 있으면 **보면 안다** — 개발자와 분석가의 마크가 다르다는 사실이 그림
 * 자체로 증거가 된다.
 *
 * 마크는 우리가 도트로 다시 그린 **단순화된 표식**이다. 회사 로고 원본을
 * 픽셀로 늘려 박는 것은 대개 그 회사의 상표 지침이 금지한다(변형 금지).
 * 모양만 빌리고, 어느 회사인지는 이름표에 글자로 적는다.
 *
 * ## 이름은 몸통에 있다
 *
 * 처음에는 머리 위에 말풍선처럼 띄웠는데, 다섯 개가 공중에 떠 있으니
 * 방이 아니라 **이름표 다섯 개가 붙은 그림**으로 보였다. 이름은 몸통에
 * 작게 얹는다. 직함·제공자·상태처럼 늘 필요하지는 않은 것만 가리켰을
 * 때 펼친다.
 *
 * ## 방은 생성된 데이터다
 *
 * 가구는 `scripts/gen-office.mjs` 가 사각형으로 펼쳐 `office-room.ts` 에
 * 박아둔다. 여기서 손으로 적으면 컴포넌트가 천 줄이 되고, 책상 하나를
 * 옮기려면 좌표 스무 개를 고쳐야 한다.
 *
 * ## 살아 움직이는 것과 장식의 차이
 *
 * 움직이는 것은 셋뿐이고 셋 다 **사실을 말한다**:
 *
 * - 일하는 직원만 손이 오르내린다(타자). 대기 중인 자리는 가만히 있다.
 * - 일하는 자리의 노트북 화면만 깜빡인다.
 * - 빈 자리는 의자만 남는다. 내보낸 직원이 어디 갔는지 묻지 않아도 된다.
 *
 * 돌아다니는 고양이 같은 것은 넣지 않았다. 귀엽지만 아무 말도 하지
 * 않고, 말하지 않는 것으로 시선을 끌면 말하는 것이 묻힌다.
 */
import { useEffect, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";
import { useLang } from "@/lib/i18n";
import type { Employee } from "@/lib/types";
import { ROOM, ROOM_RECTS } from "./office-room";

/** 생성기가 쓰는 이름 → 실제 색. 색은 토큰에서만 나온다(§4). */
const PAINT: Record<string, string> = {
  floor: "color-mix(in srgb, var(--panel-solid) 92%, transparent)",
  floorLine: "color-mix(in srgb, var(--line) 60%, transparent)",
  floorDot: "color-mix(in srgb, var(--line) 45%, transparent)",
  wall: "color-mix(in srgb, var(--fg) 16%, transparent)",
  wallEdge: "color-mix(in srgb, var(--line-strong) 65%, transparent)",
  glass: "color-mix(in srgb, var(--accent) 45%, transparent)",
  board: "color-mix(in srgb, var(--panel-solid) 60%, #fff)",
  boardInk: "color-mix(in srgb, var(--dim) 70%, transparent)",
  // 가구는 바닥보다 **밝아야** 한다. 같은 밝기면 방이 평면으로 보이고,
  // 어두우면 구멍처럼 읽힌다.
  desk: "color-mix(in srgb, var(--fg) 12%, transparent)",
  deskEdge: "color-mix(in srgb, var(--fg) 22%, transparent)",
  chair: "color-mix(in srgb, var(--fg) 9%, transparent)",
  chairSeat: "color-mix(in srgb, var(--fg) 14%, transparent)",
  door: "color-mix(in srgb, var(--warn) 22%, transparent)",
  doorFrame: "color-mix(in srgb, var(--warn) 45%, transparent)",
  doorKnob: "color-mix(in srgb, var(--warn) 75%, transparent)",
  clock: "color-mix(in srgb, var(--fg) 20%, transparent)",
  clockHand: "var(--dim)",
  // 천장 조명이 닿는 자리. 아주 옅게 — 여기가 세면 방이 얼룩덜룩해진다.
  lightPool: "color-mix(in srgb, var(--fg) 3.5%, transparent)",
  monitor: "color-mix(in srgb, var(--fg) 30%, transparent)",
  monitorStand: "var(--line)",
  keyboard: "color-mix(in srgb, var(--line) 80%, transparent)",
  mouse: "var(--line)",
  paper: "color-mix(in srgb, #fff 55%, transparent)",
  shelf: "color-mix(in srgb, var(--fg) 13%, transparent)",
  book1: "color-mix(in srgb, var(--strategist) 70%, transparent)",
  book2: "color-mix(in srgb, var(--writer) 65%, transparent)",
  book3: "color-mix(in srgb, var(--analyst) 65%, transparent)",
  counter: "color-mix(in srgb, var(--fg) 12%, transparent)",
  machine: "color-mix(in srgb, var(--fg) 28%, transparent)",
  machineDrip: "color-mix(in srgb, var(--warn) 60%, transparent)",
  cup: "color-mix(in srgb, #fff 45%, transparent)",
  leaf: "color-mix(in srgb, var(--ok) 55%, transparent)",
  pot: "color-mix(in srgb, var(--warn) 45%, transparent)",
  rack: "color-mix(in srgb, var(--fg) 13%, transparent)",
  rackSlot: "color-mix(in srgb, var(--fg) 26%, transparent)",
  rackLed: "var(--ok)",
  rug: "color-mix(in srgb, var(--accent) 10%, transparent)",
  rugInner: "color-mix(in srgb, var(--accent) 7%, transparent)",
};

/**
 * 제공자 표식 (7×7). `X` 가 찍히는 칸이다.
 * 원본 로고가 아니라 그 회사를 가리키는 **도형**을 도트로 다시 그렸다.
 */
const MARK: Record<string, string[]> = {
  claude: ["...X...", ".X.X.X.", "..XXX..", "XXXXXXX",
           "..XXX..", ".X.X.X.", "...X..."],
  gemini: ["...X...", "..XXX..", ".XXXXX.", "XXXXXXX",
           ".XXXXX.", "..XXX..", "...X..."],
  openai: ["..XXX..", ".X...X.", "X.....X", "X.....X",
           "X.....X", ".X...X.", "..XXX.."],
  unknown: ["..XXX..", ".X...X.", "....X..", "...X...",
            "...X...", ".......", "...X..."],
};

const PROVIDER_LABEL: Record<string, string> = {
  claude: "Claude",
  gemini: "Gemini",
  openai: "GPT",
};

/** 회의 탁자와 그 둘레의 자리. 다섯 명이 고르게 앉는다. */
const TABLE = { cx: 122, cy: 77, rx: 38, ry: 27 };
const SEATS = [
  { x: 122, y: 45 },
  { x: 163, y: 66 },
  { x: 146, y: 105 },
  { x: 98, y: 105 },
  { x: 81, y: 66 },
];

/** 노트북은 자리와 탁자 중심 사이에 놓인다. */
function laptopAt(seat: { x: number; y: number }) {
  return {
    x: seat.x + (TABLE.cx - seat.x) * 0.42 - 6,
    y: seat.y + (TABLE.cy - seat.y) * 0.42 - 3,
  };
}

function Mark({ provider, x, y, color }: {
  provider: string; x: number; y: number; color: string;
}) {
  const rows = MARK[provider] ?? MARK.unknown;
  const out: React.ReactNode[] = [];
  rows.forEach((row, r) => {
    [...row].forEach((ch, c) => {
      if (ch !== "X") return;
      out.push(
        <rect key={`${r}-${c}`} x={x + c} y={y + r} width="1" height="1"
              fill={color} />,
      );
    });
  });
  return <>{out}</>;
}

/**
 * 위에서 본 직원 한 명.
 *
 * 머리(제공자 표식) · 몸통(이름) · 두 손. 손만 프레임마다 움직인다 —
 * 위에서 보면 사람이 하는 일 중 눈에 보이는 것은 그것뿐이다.
 */
function Worker({ seat, color, provider, name, typing, frame, empty }: {
  seat: { x: number; y: number };
  color: string; provider: string; name: string;
  typing: boolean; frame: number; empty: boolean;
}) {
  const x = seat.x - 9;
  const y = seat.y - 9;
  if (empty) {
    // 빈 자리는 의자만. 흐릿한 사람을 그려두면 "불러오는 중"으로 읽힌다.
    return (
      <g opacity="0.75">
        <rect x={x + 1} y={y + 2} width="16" height="15" rx="4"
              fill="none" stroke="var(--line-strong)" strokeWidth="1"
              strokeDasharray="2 2" />
      </g>
    );
  }
  const lift = typing ? (frame === 0 ? [1, 0] : [0, 1]) : [0, 0];
  return (
    <g>
      {/* 의자 등받이 */}
      <rect x={x - 1} y={y + 3} width="20" height="15" rx="5"
            fill="color-mix(in srgb, var(--line) 85%, transparent)" />
      {/* 몸통 — 이름이 여기 앉는다 */}
      <rect x={x + 1} y={y + 7} width="16" height="9" rx="3" fill={color} />
      <text
        x={x + 9} y={y + 13.4} textAnchor="middle" fontSize="4.2"
        fontWeight="700" fill="#0b0d16" style={{ letterSpacing: "-0.1px" }}
      >
        {name.length > 4 ? `${name.slice(0, 4)}…` : name}
      </text>
      {/* 머리 — 표식이 앉는 자리 */}
      <rect x={x + 4} y={y - 2} width="11" height="11" rx="3.5"
            fill="var(--panel-solid)" stroke={color} strokeWidth="0.9" />
      <Mark provider={provider} x={x + 6} y={y} color={color} />
      {/* 손 */}
      <rect x={x - 1} y={y + 8 - lift[0]} width="3.4" height="3.4" rx="1.7"
            fill="#e9c69f" />
      <rect x={x + 15.6} y={y + 8 - lift[1]} width="3.4" height="3.4" rx="1.7"
            fill="#e9c69f" />
    </g>
  );
}

/** 탁자 위의 노트북. 일하는 자리만 화면이 켜져 있다. */
function Laptop({ seat, working, empty }: {
  seat: { x: number; y: number }; working: boolean; empty: boolean;
}) {
  const p = laptopAt(seat);
  return (
    <g opacity={empty ? 0.35 : 1}>
      <rect x={p.x} y={p.y} width="12" height="7" rx="1.2"
            fill="color-mix(in srgb, var(--fg) 34%, transparent)" />
      <rect
        className={working ? "px-screen" : ""}
        x={p.x + 1} y={p.y + 1} width="10" height="4" rx="0.8"
        fill={working ? "var(--accent)" : "var(--dim)"}
      />
      <rect x={p.x + 1} y={p.y + 5.6} width="10" height="1" rx="0.5"
            fill="color-mix(in srgb, var(--fg) 20%, transparent)" />
    </g>
  );
}

export function PixelOffice({
  employees, working, onPick, picked, className = "",
}: {
  employees: Employee[];
  /** 지금 일하는 직원 id. */
  working: (id: string) => boolean;
  onPick?: (id: string) => void;
  picked?: string | null;
  className?: string;
}) {
  const { t } = useLang();
  const [frame, setFrame] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const still = prefersReducedMotion();
  const anyWorking = employees.some((e) => working(e.id));

  // 타자 프레임. 일하는 사람이 없으면 타이머 자체를 걸지 않는다 —
  // 아무도 일하지 않는 화면이 계속 다시 그려질 이유가 없다.
  useEffect(() => {
    if (still || !anyWorking) return;
    const id = window.setInterval(() => setFrame((f) => (f + 1) % 2), 190);
    return () => window.clearInterval(id);
  }, [still, anyWorking]);

  const open = employees.find((e) => e.id === (picked ?? hover));

  return (
    <div className={`glass glass-lit overflow-hidden ${className}`}>
      <svg
        viewBox={`0 0 ${ROOM.w} ${ROOM.h}`}
        className="block w-full"
        role="img"
        aria-label={t("office.alt")}
      >
        {/* 방 — 생성된 데이터 (scripts/gen-office.mjs) */}
        {ROOM_RECTS.map((q, i) => (
          <rect key={i} x={q.x} y={q.y} width={q.w} height={q.h} rx={q.rx}
                fill={PAINT[q.fill] ?? "var(--line)"} />
        ))}

        {/* 회의 탁자 */}
        <ellipse cx={TABLE.cx} cy={TABLE.cy} rx={TABLE.rx} ry={TABLE.ry}
                 fill="color-mix(in srgb, var(--fg) 14%, transparent)"
                 stroke="color-mix(in srgb, var(--fg) 26%, transparent)"
                 strokeWidth="1" />
        <ellipse cx={TABLE.cx} cy={TABLE.cy} rx={TABLE.rx - 4}
                 ry={TABLE.ry - 3} fill="none" stroke="var(--line)"
                 strokeWidth="0.5" opacity="0.7" />

        {employees.slice(0, SEATS.length).map((e, i) => {
          const seat = SEATS[i];
          const empty = e.active === false;
          const isWorking = !empty && working(e.id);
          const color = `var(--${e.id}, var(--accent))`;
          return (
            <g key={e.id}>
              <Laptop seat={seat} working={isWorking} empty={empty} />
              <Worker
                seat={seat}
                color={color}
                provider={e.provider}
                name={e.name}
                typing={isWorking && !still}
                frame={frame}
                empty={empty}
              />
              {/* 고른 자리 · 일하는 자리 표시 */}
              {(picked === e.id || (isWorking && still)) && (
                <rect x={seat.x - 12} y={seat.y - 13} width="24" height="26"
                      rx="6" fill="none"
                      stroke={picked === e.id ? "var(--accent)" : color}
                      strokeWidth="1" />
              )}
              <rect
                x={seat.x - 12} y={seat.y - 13} width="24" height="26"
                fill="transparent"
                style={{ cursor: onPick ? "pointer" : "default" }}
                onMouseEnter={() => setHover(e.id)}
                onMouseLeave={() => setHover(null)}
                onClick={() => onPick?.(e.id)}
              >
                <title>{`${e.name} · ${e.role}`}</title>
              </rect>
            </g>
          );
        })}
      </svg>

      {/*
        인적사항은 가리켰을 때만. 다섯 개를 늘 띄우면 방이 아니라 이름표
        다섯 개가 붙은 그림이 된다. SVG 밖에 두는 이유는 글자 크기 —
        방 좌표계 안에서는 글자가 4px 이라 읽히지 않는다.
      */}
      <div className="flex min-h-[38px] items-center gap-2 border-t border-line
        px-3 py-2 text-[11px]">
        {open ? (
          <>
            <span className="size-2 rounded-full"
                  style={{ background: `var(--${open.id}, var(--accent))` }} />
            <strong className="text-fg">{open.name}</strong>
            <span className="text-muted">{open.role}</span>
            <span className="text-dim">
              {PROVIDER_LABEL[open.provider] ?? open.provider} · {open.model}
            </span>
            <span className="ml-auto"
                  style={{ color: working(open.id)
                    ? `var(--${open.id}, var(--accent))` : "var(--dim)" }}>
              {open.active === false
                ? t("staff.empty")
                : working(open.id)
                  ? t("office.working")
                  : t("office.idle")}
              {open.mock ? " · MOCK" : ""}
            </span>
          </>
        ) : (
          <span className="text-dim">{t("office.hint")}</span>
        )}
      </div>
    </div>
  );
}
