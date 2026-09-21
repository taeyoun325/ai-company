"use client";

/**
 * 도트 사무실 — 위에서 내려다본 방 (DAY 22 · 지시서 §4).
 *
 * ## 왜 위에서 보나
 *
 * 옆에서 본 그림은 책상 다섯 개를 한 줄로 세워야 하고, 그러면 **방이
 * 아니라 띠**가 된다. 위에서 보면 자리 배치·회의 테이블·빈 자리가 한
 * 화면에 들어오고, "회사가 이렇게 생겼다"가 한 번에 읽힌다.
 *
 * ## 머리 자리에 제공자 마크가 있다
 *
 * 이 제품의 핵심 주장은 **구현자와 검증자가 다른 회사의 모델**이라는
 * 것이다(§8). 글로 적어두면 읽는 사람만 알지만, 자리마다 마크를 박아두면
 * **보면 안다** — 개발자 자리와 분석가 자리의 마크가 다르다는 사실이
 * 그림 자체로 증거가 된다.
 *
 * 마크는 우리가 도트로 다시 그린 **단순화된 표식**이다. 회사 로고 원본을
 * 픽셀로 늘려 박는 것은 대개 그 회사의 상표 지침이 금지한다(변형 금지).
 * 그래서 모양만 빌리고, 어느 회사인지는 이름표에 글자로 적는다 — 그림이
 * 애매하면 글자가 답한다.
 *
 * ## 머리 위의 인적사항
 *
 * 이름·직함·모델·지금 상태가 자리 위에 뜬다. 카드 목록으로 내려두면
 * "저 자리가 누구지"를 눈으로 왕복해야 한다. 다만 **다섯 개를 항상 다
 * 띄우면 방이 안 보이므로**, 기본은 이름 한 줄이고 나머지는 그 자리를
 * 가리키거나 골랐을 때 펼친다.
 *
 * ## 살아 움직이는 것과 장식의 차이
 *
 * 움직이는 것은 셋뿐이고 셋 다 **사실을 말한다**:
 *
 * - 일하는 직원만 손이 오르내린다(타자). 대기 중인 자리는 가만히 있다.
 * - 일하는 자리의 모니터만 깜빡인다.
 * - 빈 자리는 의자만 남는다. 내보낸 직원이 어디 갔는지 묻지 않아도 된다.
 *
 * 돌아다니는 고양이 같은 것은 넣지 않았다. 귀엽지만 아무 말도 하지
 * 않고, 말하지 않는 것으로 시선을 끌면 말하는 것이 묻힌다.
 *
 * ## 움직임을 끈 사람에게는
 *
 * 프레임이 멈춘다. 그림은 그대로 보이고, 일하는 자리는 테두리로 표시한다.
 */
import { useEffect, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";
import { useLang } from "@/lib/i18n";
import type { Employee } from "@/lib/types";

const ROOM = { w: 208, h: 132 };

/**
 * 제공자 표식 (7×7). `X` 가 찍히는 칸이다.
 * 원본 로고가 아니라 그 회사를 가리키는 **도형**을 도트로 다시 그렸다.
 */
const MARK: Record<string, string[]> = {
  claude: [
    "...X...",
    ".X.X.X.",
    "..XXX..",
    "XXXXXXX",
    "..XXX..",
    ".X.X.X.",
    "...X...",
  ],
  gemini: [
    "...X...",
    "..XXX..",
    ".XXXXX.",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "...X...",
  ],
  openai: [
    "..XXX..",
    ".X...X.",
    "X.....X",
    "X.....X",
    "X.....X",
    ".X...X.",
    "..XXX..",
  ],
  unknown: [
    "..XXX..",
    ".X...X.",
    "....X..",
    "...X...",
    "...X...",
    ".......",
    "...X...",
  ],
};

const PROVIDER_LABEL: Record<string, string> = {
  claude: "Claude",
  gemini: "Gemini",
  openai: "GPT",
};

/** 자리 좌표. 위 줄 셋 · 아래 줄 둘 — 실제 사무실이 그렇게 생겼다. */
const SEATS = [
  { x: 16, y: 30 },
  { x: 58, y: 30 },
  { x: 100, y: 30 },
  { x: 37, y: 82 },
  { x: 79, y: 82 },
];
const DESK = { w: 32, h: 11 };

/** 7×7 표식을 원하는 자리에 찍는다. */
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
 * 머리(표식) · 어깨 · 두 손. 손만 프레임마다 움직인다 — 위에서 보면
 * 사람이 하는 일 중 눈에 보이는 것은 그것뿐이다.
 */
function Worker({ x, y, color, provider, typing, frame }: {
  x: number; y: number; color: string; provider: string;
  typing: boolean; frame: number;
}) {
  const lift = typing ? (frame === 0 ? [1, 0] : [0, 1]) : [0, 0];
  return (
    <g>
      {/* 어깨 */}
      <rect x={x} y={y + 9} width="15" height="7" rx="2.5" fill={color} />
      <rect x={x + 1.5} y={y + 13.5} width="12" height="2" rx="1"
            fill="rgba(0,0,0,0.18)" />
      {/* 머리 — 표식이 앉는 자리 */}
      <rect x={x + 2.5} y={y - 1} width="10" height="11" rx="3"
            fill="var(--panel-solid)" stroke={color} strokeWidth="0.9" />
      <Mark provider={provider} x={x + 4} y={y + 1} color={color} />
      {/* 손 — 자판 쪽으로 뻗어 있다 */}
      <rect x={x - 1.5} y={y + 5 - lift[0]} width="3.5" height="3.5" rx="1.5"
            fill="#e9c69f" />
      <rect x={x + 13} y={y + 5 - lift[1]} width="3.5" height="3.5" rx="1.5"
            fill="#e9c69f" />
    </g>
  );
}

/** 책상 · 모니터 · 의자. 사람이 없어도 자리는 남는다. */
function Seat({ x, y, working, empty }: {
  x: number; y: number; working: boolean; empty: boolean;
}) {
  return (
    <g>
      <rect x={x} y={y} width={DESK.w} height={DESK.h} rx="2"
            fill="var(--panel-2)" stroke="var(--line)" strokeWidth="0.8" />
      {/* 위에서 보면 모니터는 받침과 화면의 윗면만 보인다 */}
      <rect x={x + 10} y={y + 1.5} width="12" height="4" rx="1"
            fill="var(--line-strong)" />
      <rect
        className={working ? "px-screen" : ""}
        x={x + 11} y={y + 2.4} width="10" height="2.2" rx="0.6"
        fill={working ? "var(--accent)" : "var(--dim)"}
        opacity={empty ? 0.3 : 0.9}
      />
      {/* 자판 */}
      <rect x={x + 9} y={y + 7} width="14" height="3" rx="1"
            fill="var(--line)" />
      {/* 의자 — 사람 뒤 */}
      <rect x={x + 10} y={y + 29} width="12" height="5" rx="2.5"
            fill="var(--line)" />
    </g>
  );
}

/** 방 — 바닥·벽·회의 탁자·화분. 사람이 일하는 곳처럼 보여야 한다. */
function Room() {
  return (
    <g>
      <rect x="0" y="0" width={ROOM.w} height={ROOM.h}
            fill="color-mix(in srgb, var(--panel-solid) 90%, transparent)" />
      {/* 바닥 격자 — 위에서 본 방은 바닥이 보인다 */}
      {Array.from({ length: Math.ceil(ROOM.w / 16) }, (_, i) => (
        <rect key={`v${i}`} x={i * 16} y="0" width="0.5" height={ROOM.h}
              fill="var(--line)" opacity="0.5" />
      ))}
      {Array.from({ length: Math.ceil(ROOM.h / 16) }, (_, i) => (
        <rect key={`h${i}`} x="0" y={i * 16} width={ROOM.w} height="0.5"
              fill="var(--line)" opacity="0.5" />
      ))}
      {/* 벽 */}
      <rect x="0" y="0" width={ROOM.w} height="6" fill="var(--line-strong)" />
      <rect x="0" y="0" width="5" height={ROOM.h} fill="var(--line-strong)" />
      <rect x={ROOM.w - 5} y="0" width="5" height={ROOM.h}
            fill="var(--line-strong)" />
      <rect x="0" y={ROOM.h - 5} width={ROOM.w} height="5"
            fill="var(--line-strong)" />
      {/* 회의 탁자와 의자 넷 */}
      <ellipse cx="166" cy="46" rx="20" ry="14" fill="var(--panel-2)"
               stroke="var(--line)" strokeWidth="0.8" />
      <rect x="160" y="26" width="12" height="5" rx="2.5" fill="var(--line)" />
      <rect x="160" y="61" width="12" height="5" rx="2.5" fill="var(--line)" />
      <rect x="139" y="43" width="5" height="10" rx="2.5" fill="var(--line)" />
      <rect x="188" y="43" width="5" height="10" rx="2.5" fill="var(--line)" />
      {/* 화분 둘 */}
      <circle cx="164" cy="98" r="7"
              fill="color-mix(in srgb, var(--ok) 55%, transparent)" />
      <rect x="161" y="99" width="6" height="7" rx="1" fill="var(--line-strong)" />
      <circle cx="186" cy="112" r="5"
              fill="color-mix(in srgb, var(--ok) 45%, transparent)" />
      <rect x="184" y="113" width="4" height="5" rx="1" fill="var(--line-strong)" />
      {/* 커피 자리 */}
      <rect x="12" y="112" width="26" height="9" rx="2" fill="var(--panel-2)"
            stroke="var(--line)" strokeWidth="0.8" />
      <circle cx="18" cy="116.5" r="2.2"
              fill="color-mix(in srgb, var(--warn) 70%, transparent)" />
      <circle cx="25" cy="116.5" r="2.2"
              fill="color-mix(in srgb, var(--warn) 45%, transparent)" />
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

  return (
    <div className={`glass glass-lit overflow-hidden ${className}`}>
      <svg
        viewBox={`0 0 ${ROOM.w} ${ROOM.h}`}
        className="block w-full"
        role="img"
        aria-label={t("office.alt")}
      >
        <Room />
        {employees.slice(0, SEATS.length).map((e, i) => {
          const seat = SEATS[i];
          const empty = e.active === false;
          const isWorking = !empty && working(e.id);
          const color = `var(--${e.id}, var(--accent))`;
          const open = picked === e.id || hover === e.id;
          return (
            <g key={e.id}>
              <Seat x={seat.x} y={seat.y} working={isWorking} empty={empty} />
              {!empty && (
                <Worker
                  x={seat.x + 8.5}
                  y={seat.y + 15}
                  color={color}
                  provider={e.provider}
                  typing={isWorking && !still}
                  frame={frame}
                />
              )}

              {/* 인적사항 — 머리 위. 기본은 이름 한 줄, 가리키면 펼친다.
                  다섯을 항상 다 띄우면 방이 안 보인다. */}
              <g transform={`translate(${seat.x + DESK.w / 2} ${seat.y - 4})`}>
                <rect
                  x={-25} y={open ? -25 : -11} width="50"
                  height={open ? 25 : 11} rx="3"
                  fill="var(--panel-solid)"
                  stroke={isWorking ? color : "var(--line)"}
                  strokeWidth="0.8"
                  opacity={empty ? 0.5 : 0.94}
                />
                <text x="0" y={open ? -16 : -3} textAnchor="middle"
                      fontSize="5.4" fontWeight="600"
                      fill={empty ? "var(--dim)" : "var(--fg)"}>
                  {e.name}
                </text>
                {open && (
                  <>
                    <text x="0" y={-9.5} textAnchor="middle" fontSize="4.4"
                          fill="var(--muted)">
                      {e.role} · {PROVIDER_LABEL[e.provider] ?? e.provider}
                    </text>
                    <text x="0" y={-3.5} textAnchor="middle" fontSize="4.2"
                          fill={isWorking ? color : "var(--dim)"}>
                      {empty
                        ? t("staff.empty")
                        : isWorking
                          ? t("office.working")
                          : t("office.idle")}
                      {e.mock ? " · MOCK" : ""}
                    </text>
                  </>
                )}
              </g>

              {/* 고른 자리 · 일하는 자리 표시 */}
              {(picked === e.id || (isWorking && still)) && (
                <rect x={seat.x - 2} y={seat.y - 2} width={DESK.w + 4}
                      height="38" rx="3" fill="none"
                      stroke={picked === e.id ? "var(--accent)" : color}
                      strokeWidth="0.9" />
              )}

              {/* 자리를 통째로 누를 수 있게 한다. SVG 안에 투명한 사각형을
                  두는 편이, 화면 위에 HTML 을 겹쳐 좌표를 맞추는 것보다
                  어긋날 일이 없다. */}
              <rect
                x={seat.x - 3} y={seat.y - 26} width={DESK.w + 6} height="64"
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
    </div>
  );
}
