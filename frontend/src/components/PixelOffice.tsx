"use client";

/**
 * 도트 사무실 (DAY 21 · 지시서 §4).
 *
 * ## 왜 그림이 필요한가
 *
 * 카드 다섯 장으로도 상태는 읽힌다. 하지만 이 제품이 파는 것은 "AI 가
 * 회사처럼 일한다"는 것이고, 카드 목록은 그걸 **말하지 않는다.** 자리에
 * 앉은 사람이 지금 타자를 치고 있는가, 빈 자리가 있는가 — 그건 그림이
 * 한 번에 말한다.
 *
 * ## 왜 도트인가
 *
 * 사진 같은 그림은 지금 이 제품이 할 수 있는 것보다 커 보이게 만든다.
 * 도트는 **명백히 도식**이라 과장하지 않는다. 그리고 파일이 아니라
 * 좌표로 그리므로 색 토큰(`--developer` 등)을 그대로 따른다 — 직원 색이
 * 화면 두 곳에서 다르면 안 된다는 규칙(§4)이 그림에서도 지켜진다.
 *
 * 외부 이미지 파일을 쓰지 않는 이유도 같다. PNG 는 테마를 따라오지
 * 못하고, 라이트 모드에서 혼자 어둡다.
 *
 * ## 살아 움직이는 것과 장식의 차이
 *
 * 움직이는 것은 셋뿐이고 셋 다 **사실을 말한다**:
 *
 * - 일하는 직원만 타자를 친다. 대기 중인 직원은 이따금 눈만 깜빡인다.
 * - 일하는 자리의 모니터만 깜빡인다.
 * - 빈 자리는 의자가 비어 있다. 내보낸 직원이 어디 갔는지 묻지 않아도 된다.
 *
 * 배경에 돌아다니는 고양이 같은 것은 넣지 않았다. 귀엽지만 아무 말도
 * 하지 않고, 화면이 말하지 않는 것으로 시선을 끌면 말하는 것이 묻힌다.
 *
 * ## 움직임을 끈 사람에게는
 *
 * 프레임이 멈춘다. 그림은 그대로 보이고, 일하는 자리는 테두리로 표시한다.
 */
import { useEffect, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";
import type { Employee } from "@/lib/types";

/**
 * 사람 도트. 한 칸이 한 픽셀이고, 글자가 팔레트 키다.
 *
 *   .  비어 있음   H 머리카락   S 피부   E 눈
 *   B  옷(직원 색)  D 옷 그늘    A 팔    P 손
 *
 * 앉아 있으므로 상반신만 있다. 책상 아래는 보이지 않는다.
 */
const BODY = [
  "...HHHHH...",
  "..HHHHHHH..",
  "..HSSSSSH..",
  "..HSESESH..",   // ← 눈. 깜빡일 때 이 줄만 바뀐다
  "..HSSSSSH..",
  "...SSSSS...",
  "....SSS....",
  "..BBBBBBB..",
  ".BBBBBBBBB.",
  ".BBBBBBBBB.",
  ".BBBBBBBBB.",
  ".BDBBBBBDB.",
  ".B.......B.",
  ".B.......B.",
];

const EYE_ROW = 3;
/** 눈을 감은 줄. 1픽셀 눈이라 피부색으로 덮는 것이 곧 깜빡임이다. */
const BLINK_ROW = "..HSSSSSH..";

/**
 * 팔. 프레임마다 손 높이가 다르다 — 이게 타자 치는 동작이다.
 * 좌표는 몸통 격자 기준(11×11)이고, 손은 2×2 다.
 */
const ARMS: { left: [number, number]; right: [number, number] }[] = [
  { left: [0, 9], right: [9, 10] },     // 왼손 위
  { left: [0, 10], right: [9, 9] },     // 오른손 위
];
const IDLE_ARMS = { left: [0, 10] as [number, number],
                    right: [9, 10] as [number, number] };

/** 방 한 칸의 크기. 책상 다섯 개가 가로로 들어간다. */
const ROOM = { w: 170, h: 104 };
const DESK = { w: 28, gap: 5, top: 66, thick: 4, y0: 4 };
const SEAT_X = (i: number) => DESK.y0 + i * (DESK.w + DESK.gap);

type Palette = { H: string; S: string; E: string; B: string; D: string };

/**
 * 직원마다 다른 사람으로 보여야 한다. 옷은 그 직원의 색(§4 토큰)이고,
 * 머리카락은 id 에서 뽑는다 — 무작위로 하면 새로고침할 때마다 다른
 * 사람이 앉아 있다.
 */
const HAIR = ["#2b2118", "#4a2f1d", "#1d2430", "#3c2a3a", "#23313a"];

function paletteOf(id: string, color: string): Palette {
  let sum = 0;
  for (const ch of id) sum += ch.charCodeAt(0);
  return {
    H: HAIR[sum % HAIR.length],
    S: "#e8c39a",
    E: "#2b2118",
    B: color,
    D: "color-mix(in srgb, " + color + " 65%, #000)",
  };
}

function Sprite({
  x, y, palette, blink, arms,
}: {
  x: number; y: number; palette: Palette; blink: boolean;
  arms: { left: [number, number]; right: [number, number] };
}) {
  const rows = BODY.map((row, r) =>
    r === EYE_ROW && blink ? BLINK_ROW : row);
  const cells: React.ReactNode[] = [];
  rows.forEach((row, r) => {
    [...row].forEach((ch, c) => {
      if (ch === ".") return;
      const fill = palette[ch as keyof Palette];
      if (!fill) return;
      cells.push(
        <rect key={`${r}-${c}`} x={x + c} y={y + r} width="1" height="1"
              fill={fill} />,
      );
    });
  });
  // 손은 몸통 격자 밖에 둔다 — 프레임마다 위치가 바뀌는 것은 이 둘뿐이라,
  // 손 때문에 몸통 전체를 다시 그리는 것은 낭비다.
  const hand = (p: [number, number]) => (
    <rect x={x + p[0]} y={y + p[1]} width="2" height="2" fill={palette.S} />
  );
  return (
    <g>
      {cells}
      {hand(arms.left)}
      {hand(arms.right)}
    </g>
  );
}

/** 책상 · 의자 · 모니터. 사람이 없어도 자리는 남는다. */
function Seat({
  i, working, empty,
}: {
  i: number; working: boolean; empty: boolean;
}) {
  const x = SEAT_X(i);
  return (
    <g>
      {/* 의자 등받이 — 사람 뒤에 그린다 */}
      <rect x={x + 4} y={58} width="9" height="8" fill="var(--line)" />
      {/* 책상 */}
      <rect x={x} y={DESK.top} width={DESK.w} height={DESK.thick}
            fill="var(--panel2)" />
      <rect x={x} y={DESK.top} width={DESK.w} height="1" fill="var(--line)" />
      <rect x={x + 2} y={DESK.top + DESK.thick} width="3" height="16"
            fill="var(--panel2)" />
      <rect x={x + DESK.w - 5} y={DESK.top + DESK.thick} width="3" height="16"
            fill="var(--panel2)" />
      {/* 모니터 — 일하는 자리만 화면이 켜져 있다 */}
      <rect x={x + 15} y={54} width="12" height="11" fill="var(--line)" />
      <rect
        className={working ? "px-screen" : ""}
        x={x + 16} y={55} width="10" height="9"
        fill={working ? "var(--accent)" : "var(--panel2)"}
        opacity={empty ? 0.35 : 1}
      />
      <rect x={x + 20} y={65} width="2" height="1" fill="var(--line)" />
    </g>
  );
}

export function PixelOffice({
  employees, working, onPick, picked,
}: {
  employees: Employee[];
  /** 지금 일하는 직원 id. 한 명만 표시한다 — 둘이 켜지면 누가 일하는지 모른다. */
  working: (id: string) => boolean;
  onPick?: (id: string) => void;
  picked?: string | null;
}) {
  const [frame, setFrame] = useState(0);
  const [blinking, setBlinking] = useState<string | null>(null);
  const still = prefersReducedMotion();
  const anyWorking = employees.some((e) => working(e.id));

  // 타자 프레임. 일하는 사람이 없으면 타이머 자체를 걸지 않는다 —
  // 아무도 일하지 않는 화면이 계속 다시 그려질 이유가 없다.
  useEffect(() => {
    if (still || !anyWorking) return;
    const id = window.setInterval(() => setFrame((f) => (f + 1) % ARMS.length), 180);
    return () => window.clearInterval(id);
  }, [still, anyWorking]);

  // 눈 깜빡임. 한 번에 한 명만, 불규칙하게. 다 같이 깜빡이면 사람이
  // 아니라 기계로 보인다.
  const ids = employees.map((e) => e.id).join(",");
  useEffect(() => {
    if (still || employees.length === 0) return;
    let timer = 0;
    const tick = () => {
      const pool = ids.split(",").filter(Boolean);
      const who = pool[Math.floor(Math.random() * pool.length)];
      setBlinking(who);
      window.setTimeout(() => setBlinking(null), 140);
      timer = window.setTimeout(tick, 1800 + Math.random() * 2600);
    };
    timer = window.setTimeout(tick, 1200);
    return () => window.clearTimeout(timer);
  }, [still, ids, employees.length]);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-panel">
      <svg
        viewBox={`0 0 ${ROOM.w} ${ROOM.h}`}
        className="block w-full"
        role="img"
        aria-label="도트로 그린 사무실. 자리마다 직원이 앉아 있고, 일하는 직원은 타자를 칩니다."
        style={{ imageRendering: "pixelated" }}
      >
        {/* 벽과 바닥 */}
        <rect x="0" y="0" width={ROOM.w} height="58" fill="var(--panel2)" />
        <rect x="0" y="58" width={ROOM.w} height={ROOM.h - 58} fill="var(--panel)" />
        <rect x="0" y="57" width={ROOM.w} height="1" fill="var(--line)" />

        {/* 창문 — 밖이 있다는 것만 알려주면 된다 */}
        <rect x="8" y="16" width="26" height="18" fill="var(--line)" />
        <rect x="9" y="17" width="24" height="16"
              fill="color-mix(in srgb, var(--accent) 22%, transparent)" />
        <rect x="20" y="17" width="1" height="16" fill="var(--line)" />
        <rect x="9" y="24" width="24" height="1" fill="var(--line)" />

        {/* 시계 — 회사에는 시계가 있다 */}
        <rect x="78" y="18" width="9" height="9" fill="var(--line)" />
        <rect x="79" y="19" width="7" height="7" fill="var(--panel)" />
        <rect x="82" y="20" width="1" height="3" fill="var(--dim)" />
        <rect x="83" y="22" width="3" height="1" fill="var(--dim)" />

        {/* 게시판 — 벽이 비어 있으면 방이 아니라 배경처럼 보인다 */}
        <rect x="108" y="16" width="26" height="18" fill="var(--line)" />
        <rect x="109" y="17" width="24" height="16" fill="var(--panel)" />
        <rect x="112" y="20" width="8" height="6"
              fill="color-mix(in srgb, var(--warn) 45%, transparent)" />
        <rect x="122" y="22" width="8" height="8"
              fill="color-mix(in srgb, var(--ok) 40%, transparent)" />

        {/* 화분 — 구석 하나면 충분하다 */}
        <rect x="159" y="70" width="9" height="5"
              fill="color-mix(in srgb, var(--ok) 55%, transparent)" />
        <rect x="161" y="65" width="5" height="6"
              fill="color-mix(in srgb, var(--ok) 75%, transparent)" />
        <rect x="160" y="75" width="7" height="11" fill="var(--line)" />

        {employees.map((e, i) => {
          const empty = e.active === false;
          const isWorking = !empty && working(e.id);
          const color = `var(--${e.id}, var(--accent))`;
          const x = SEAT_X(i);
          return (
            <g key={e.id}>
              <Seat i={i} working={isWorking} empty={empty} />
              {!empty && (
                <Sprite
                  x={x + 1}
                  y={52}
                  palette={paletteOf(e.id, color)}
                  blink={blinking === e.id}
                  arms={isWorking && !still ? ARMS[frame] : IDLE_ARMS}
                />
              )}
              {empty && (
                // 빈 자리는 비어 보여야 한다. 흐릿한 사람을 그려두면
                // "로딩 중"으로 읽힌다.
                <text x={x + 7} y={62} fontSize="9" fill="var(--dim)">
                  ?
                </text>
              )}
              {/* 고른 자리 표시 */}
              {picked === e.id && (
                <rect x={x - 1} y={50} width={DESK.w + 2} height={36}
                      fill="none" stroke="var(--accent)" strokeWidth="1" />
              )}
              {/* 일하는 자리 — 움직임을 끈 사람에게는 이 테두리가 유일한 신호다 */}
              {isWorking && still && (
                <rect x={x - 1} y={50} width={DESK.w + 2} height={36}
                      fill="none" stroke={color} strokeWidth="1" />
              )}
              <text
                x={x + DESK.w / 2}
                y={93}
                textAnchor="middle"
                fontSize="5"
                fill={empty ? "var(--dim)" : "var(--fg)"}
              >
                {e.name}
              </text>
              <text
                x={x + DESK.w / 2}
                y={99}
                textAnchor="middle"
                fontSize="4"
                fill={isWorking ? color : "var(--dim)"}
              >
                {e.role}
              </text>
              {/* 자리를 통째로 누를 수 있게 한다. SVG 안에 투명한 사각형을
                  두는 편이, 화면 위에 HTML 을 겹쳐 좌표를 맞추는 것보다
                  어긋날 일이 없다. */}
              {onPick && (
                <rect
                  x={x - 1} y={44} width={DESK.w + 2} height={58}
                  fill="transparent"
                  style={{ cursor: "pointer" }}
                  onClick={() => onPick(e.id)}
                >
                  <title>{e.name}</title>
                </rect>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
