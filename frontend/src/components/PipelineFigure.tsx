"use client";

/**
 * 히어로 도형 — 회사가 실제로 도는 순서 (DAY 20).
 *
 * ## 왜 영상 자리 대신 이것인가
 *
 * DAY 18 에는 "여기에 히어로 영상이 들어간다"는 점선 박스가 있었다.
 * 그건 만들 것을 적어둔 메모이지 제품 설명이 아니다. 그리고 영상은
 * **우리가 하지 않는 주장**을 하기 쉽다 — 사무실에 사람이 앉아 있는
 * 장면은 예쁘지만 이 제품이 무엇을 하는지는 말하지 않는다.
 *
 * 이 도형은 코드에 실제로 있는 순서를 그대로 그린다. 요구사항이 전략가를
 * 지나 **테스트가 먼저** 쓰이고, 구현이 붙고, **다른 회사 모델**이
 * 판정하고, 반려되면 되돌아간다. 랜딩에서 이 한 장면을 이해하면
 * 제품을 이해한 것이다.
 *
 * ## 좁은 화면에서는 세로로 다시 배치한다
 *
 * 가로 그림을 그대로 줄이면 글자가 6px 이 되고, 옆으로 밀게 두면 절반이
 * 안 보인 채로 판단된다. **무료 요금제를 없앤 뒤로 이 화면이 유일한
 * 체험 창구**이므로, 폰에서 절반만 보이는 것은 그냥 절반만 파는 것이다.
 * 좌표표를 두 벌 두고 갈아 끼운다 — 애니메이션은 id 로 잡으므로 그대로
 * 돈다.
 *
 * ## 스크립트가 없어도 읽힌다
 *
 * 노드·선·라벨은 전부 정적 SVG 다. 움직임은 그 위에 얹은 것이고,
 * 움직이지 않아도 그림은 완성된 상태로 남는다. 판정 칩(반려·통과)만
 * 처음에 숨어 있는데, 그건 설명이 아니라 연출이라 없어도 손해가 없다.
 *
 * ## 움직임을 끈 사람에게는 아무것도 움직이지 않는다
 *
 * `prefers-reduced-motion` 은 취향이 아니라 증상 유발 요인이다.
 * 켜져 있으면 타임라인 자체를 만들지 않는다.
 */
import { useEffect, useRef, useSyncExternalStore } from "react";

import { T, createTimeline, svg, withScope } from "@/lib/motion";

type Key = "req" | "strategist" | "analyst" | "developer" | "verifier" | "out";
type Pt = { x: number; y: number };

const NODES: {
  key: Key; label: string; sub: string; color: string; icon: string;
}[] = [
  { key: "req", label: "요구사항", sub: "CEO 가 한 줄", color: "var(--accent)", icon: "✎" },
  { key: "strategist", label: "전략가", sub: "인수기준으로", color: "var(--strategist)", icon: "🧭" },
  { key: "analyst", label: "분석가", sub: "테스트를 먼저", color: "var(--analyst)", icon: "🔍" },
  { key: "developer", label: "개발자", sub: "tests/ 를 못 본다", color: "var(--developer)", icon: "🛠" },
  { key: "verifier", label: "교차검증", sub: "다른 회사 모델", color: "var(--analyst)", icon: "⚖" },
  { key: "out", label: "산출물", sub: "파일로 남는다", color: "var(--ok)", icon: "📦" },
];

/** 선 id. 타임라인이 이 이름으로 경로를 잡는다. */
const LEGS = ["p-req", "p-plan-test", "p-test-dev", "p-dev-verify", "p-pass",
              "p-reject"] as const;

type Layout = {
  viewBox: string;
  r: number;
  nodes: Record<Key, Pt>;
  paths: Record<(typeof LEGS)[number], string>;
  label: (p: Pt, key: Key) => { x: number; y: number; anchor: "middle" | "start" };
  chips: { test: Pt; verdict: Pt };
};

/** 넓은 화면 — 왼쪽에서 오른쪽으로 흐르는 조립선. */
const ROW: Layout = {
  viewBox: "0 0 680 290",
  r: 31,
  nodes: {
    req: { x: 62, y: 140 },
    strategist: { x: 190, y: 140 },
    analyst: { x: 330, y: 68 },
    developer: { x: 330, y: 212 },
    verifier: { x: 470, y: 140 },
    out: { x: 614, y: 140 },
  },
  paths: {
    "p-req": "M 112 140 L 158 140",
    "p-plan-test": "M 222 140 C 262 140, 270 68, 298 68",
    "p-test-dev": "M 330 100 L 330 180",
    "p-dev-verify": "M 362 212 C 402 212, 410 140, 438 140",
    "p-pass": "M 502 140 L 582 140",
    "p-reject": "M 470 172 C 470 268, 380 272, 336 246",
  },
  // 분석가만 라벨이 위로 간다(아래는 개발자 자리라서). 그런데 위로
  // 올릴 때는 **두 줄 전체**가 원 밖으로 나가야 한다 — 첫 줄만 기준으로
  // 잡으면 둘째 줄이 원 안에 걸쳐서 글자가 깨진 것처럼 보인다.
  label: (p, key) =>
    key === "analyst"
      ? { x: p.x, y: p.y - 56, anchor: "middle" }
      : { x: p.x, y: p.y + 50, anchor: "middle" },
  chips: { test: { x: 440, y: 54 }, verdict: { x: 556, y: 194 } },
};

/** 좁은 화면 — 위에서 아래로 내려가는 한 줄. */
const COL: Layout = {
  viewBox: "0 0 300 620",
  r: 26,
  nodes: {
    req: { x: 58, y: 46 },
    strategist: { x: 58, y: 150 },
    analyst: { x: 58, y: 254 },
    developer: { x: 58, y: 366 },
    verifier: { x: 58, y: 470 },
    out: { x: 58, y: 574 },
  },
  paths: {
    "p-req": "M 58 72 L 58 124",
    "p-plan-test": "M 58 176 L 58 228",
    "p-test-dev": "M 58 280 L 58 340",
    "p-dev-verify": "M 58 392 L 58 444",
    "p-pass": "M 58 496 L 58 548",
    "p-reject": "M 32 458 C 4 424, 4 396, 32 380",
  },
  label: (p) => ({ x: p.x + 38, y: p.y - 3, anchor: "start" }),
  chips: { test: { x: 186, y: 292 }, verdict: { x: 186, y: 508 } },
};

/**
 * 어느 배치를 쓸지. `matchMedia` 를 구독한다 — 창을 줄였을 때 그림이
 * 그대로 남아 있으면 그게 더 어색하다.
 */
function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia("(max-width: 640px)");
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia("(max-width: 640px)").matches,
    // 서버에는 화면이 없다. 넓은 쪽을 기본으로 둔다 — 좁은 화면에서는
    // 물려받은 HTML 이 한 번 가로로 보였다가 바뀌지만, 반대로 두면
    // 데스크톱 사용자 전원이 세로 그림을 한 번 보게 된다.
    () => false,
  );
}

export function PipelineFigure({ className = "" }: { className?: string }) {
  const root = useRef<HTMLDivElement>(null);
  const narrow = useNarrow();
  const L = narrow ? COL : ROW;

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    return withScope(el, () => {
      // 1) 선을 그린다. 한 번에 다 나타나면 순서가 안 보이고, 순서가
      //    이 그림의 전부다.
      const lines = svg.createDrawable(".pipe-line");
      const flow = createTimeline({
        loop: true, autoplay: false, defaults: { ease: "inOut(2)" },
      });
      const intro = createTimeline({
        defaults: { ease: T.ease },
        // 소개가 끝난 **뒤에** 일감을 흘린다. 같이 돌면 선이 그려지는
        // 도중에 토큰이 허공을 지나간다.
        onComplete: () => flow.play(),
      });
      intro.add(lines, { draw: ["0 0", "0 1"], duration: 900,
                         delay: (_t?: unknown, i = 0) => i * 90 }, 0);
      intro.add(".pipe-node", {
        opacity: [0, 1], scale: [0.7, 1], duration: 520, ease: T.pop,
        delay: (_t?: unknown, i = 0) => 200 + i * 95,
      }, 0);
      intro.add(".pipe-label", {
        opacity: [0, 1], duration: 380,
        delay: (_t?: unknown, i = 0) => 420 + i * 95,
      }, 0);

      // 2) 일감이 실제로 흘러간다. 한 바퀴가 곧 AUTO 한 사이클이다.
      const leg = (id: string, duration = 620) => {
        const path = svg.createMotionPath(`#${id}`);
        return { translateX: path.translateX, translateY: path.translateY,
                 duration };
      };
      // 노드가 일을 받는 순간의 맥박. 진행이 0초에 끝나면 제대로 도는지
      // 확인할 수 없다(§4 와 같은 이유).
      const beat = () => ({
        scale: [1, 1.22, 1], duration: 520, ease: "out(2)",
      });

      flow.add(".pipe-token", { opacity: [0, 1], duration: 200 }, 0);
      flow.add(".pipe-token", leg("p-req"), 0);
      flow.add("#ring-strategist", beat(), 620);

      flow.add(".pipe-token", leg("p-plan-test", 700), 820);
      flow.add("#ring-analyst", beat(), 1520);
      flow.add("#chip-test", { opacity: [0, 1], translateY: [6, 0],
                               duration: 320 }, 1520);

      flow.add(".pipe-token", leg("p-test-dev", 520), 1900);
      flow.add("#ring-developer", beat(), 2420);

      flow.add(".pipe-token", leg("p-dev-verify", 700), 2620);
      flow.add("#ring-verifier", beat(), 3320);

      // 첫 판정은 반려다. 한 번에 통과하는 그림을 보여주면 이 제품이
      // 하는 일의 절반(재작업 루프)이 사라진다.
      flow.add("#chip-reject", { opacity: [0, 1], scale: [0.8, 1],
                                 duration: 300 }, 3460);
      flow.add(".pipe-token", leg("p-reject", 820), 3700);
      flow.add("#chip-reject", { opacity: 0, duration: 260 }, 4300);
      flow.add("#ring-developer", beat(), 4560);

      flow.add(".pipe-token", leg("p-dev-verify", 700), 4800);
      flow.add("#ring-verifier", beat(), 5500);
      flow.add("#chip-pass", { opacity: [0, 1], scale: [0.8, 1],
                               duration: 300 }, 5640);

      flow.add(".pipe-token", leg("p-pass", 620), 5900);
      flow.add("#node-out", { scale: [1, 1.18, 1], duration: 520 }, 6500);
      flow.add("#out-glow", { opacity: [0, 0.9, 0], duration: 900 }, 6500);

      // 한 바퀴를 마치면 흔적을 지우고 다시 시작한다. 지우지 않으면
      // 두 번째 바퀴에서 이미 통과한 칩이 남아 순서가 거짓말이 된다.
      flow.add(".pipe-token", { opacity: 0, duration: 260 }, 7000);
      flow.add("#chip-pass", { opacity: 0, duration: 260 }, 7200);
      flow.add("#chip-test", { opacity: 0, duration: 260 }, 7200);
    });
    // 배치가 바뀌면 경로 좌표가 통째로 달라진다. 타임라인을 다시 만든다.
  }, [narrow]);

  return (
    <div ref={root} className={`pipe-wrap ${className}`}>
      <svg
        viewBox={L.viewBox}
        className="mx-auto w-full"
        style={{ maxHeight: narrow ? "none" : undefined }}
        role="img"
        aria-label="요구사항이 전략가를 지나 분석가가 테스트를 먼저 쓰고, 개발자가 구현하고, 다른 회사 모델이 교차검증해 반려되면 되돌아가는 흐름"
      >
        <defs>
          <radialGradient id="out-halo">
            <stop offset="0%" stopColor="var(--ok)" stopOpacity="0.55" />
            <stop offset="100%" stopColor="var(--ok)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* 선 — 반려 경로만 점선과 경고색이다. 되돌아가는 길이 다른
            길과 같아 보이면, 그게 실패 경로라는 사실이 안 읽힌다. */}
        {LEGS.map((id) => (
          <path
            key={id}
            id={id}
            d={L.paths[id]}
            className="pipe-line"
            fill="none"
            stroke={id === "p-reject" ? "var(--bad)" : "var(--line)"}
            strokeWidth={id === "p-reject" ? 1.5 : 2}
            strokeDasharray={id === "p-reject" ? "5 5" : undefined}
            strokeLinecap="round"
            opacity={id === "p-reject" ? 0.75 : 1}
          />
        ))}

        <circle
          id="out-glow"
          cx={L.nodes.out.x}
          cy={L.nodes.out.y}
          r={L.r + 15}
          fill="url(#out-halo)"
          opacity="0"
        />

        {NODES.map((n) => {
          const p = L.nodes[n.key];
          const origin = `${p.x}px ${p.y}px`;
          return (
            <g key={n.key} id={`node-${n.key}`} className="pipe-node"
               style={{ transformOrigin: origin }}>
              <circle id={`ring-${n.key}`} cx={p.x} cy={p.y} r={L.r}
                      fill="var(--panel)" stroke={n.color} strokeWidth="1.6"
                      style={{ transformOrigin: origin }} />
              <circle cx={p.x} cy={p.y} r={L.r} fill={n.color} opacity="0.1" />
              <text x={p.x} y={p.y + 6} textAnchor="middle" fontSize="19" aria-hidden>
                {n.icon}
              </text>
            </g>
          );
        })}

        {/* 라벨은 노드 그룹 밖에 둔다 — 맥박이 뛸 때 글자까지 커지면
            읽는 중에 흔들린다. */}
        {NODES.map((n) => {
          const pos = L.label(L.nodes[n.key], n.key);
          return (
            <g key={`l-${n.key}`} className="pipe-label">
              <text x={pos.x} y={pos.y} textAnchor={pos.anchor} fontSize="12.5"
                    fontWeight="600" fill="var(--fg)">
                {n.label}
              </text>
              <text x={pos.x} y={pos.y + 15} textAnchor={pos.anchor}
                    fontSize="10.5" fill="var(--dim)">
                {n.sub}
              </text>
            </g>
          );
        })}

        {/* 판정 칩 — 연출이라 처음에는 숨어 있다. 스크립트가 없으면
            나타나지 않을 뿐, 설명이 사라지지는 않는다. */}
        <Chip id="chip-test" at={L.chips.test} w={128} color="var(--analyst)"
              text="테스트가 먼저 쓰인다" />
        <Chip id="chip-reject" at={L.chips.verdict} w={80} color="var(--bad)"
              text="반려 · 재작업" />
        <Chip id="chip-pass" at={L.chips.verdict} w={52} color="var(--ok)"
              text="통과" />

        {/* 일감 */}
        <circle className="pipe-token" cx="0" cy="0" r="6.5"
                fill="var(--accent)" opacity="0" />
      </svg>
    </div>
  );
}

function Chip({ id, at, w, color, text }: {
  id: string; at: Pt; w: number; color: string; text: string;
}) {
  return (
    <g id={id} opacity="0" style={{ transformOrigin: `${at.x}px ${at.y}px` }}>
      <rect x={at.x - w / 2} y={at.y - 12} width={w} height="24" rx="12"
            fill="var(--panel)" stroke={color} strokeWidth="1" />
      <text x={at.x} y={at.y + 4} textAnchor="middle" fontSize="11"
            fill={color} fontWeight="600">
        {text}
      </text>
    </g>
  );
}
