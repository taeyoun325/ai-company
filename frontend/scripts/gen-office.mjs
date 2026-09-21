/**
 * 사무실 방 데이터를 만든다 (DAY 22).
 *
 * ## 왜 생성하나
 *
 * 방을 촘촘하게 그리려면 사각형이 수백 개 필요하다. 그걸 JSX 에 손으로
 * 적으면 컴포넌트가 천 줄이 되고, 가구 하나를 옮기려면 좌표 스무 개를
 * 손으로 고쳐야 한다.
 *
 * 그래서 **가구 단위로 적고 사각형은 여기서 펼친다.** 책상 하나가
 * `desk(x, y)` 한 줄이고, 결과는 좌표 배열이다. 컴포넌트는 그 배열을
 * 그리기만 한다.
 *
 * ## 왜 빌드 때 돌리나 (런타임이 아니라)
 *
 * 방은 **바뀌지 않는다.** 매번 브라우저에서 계산하면 같은 답을 얻으려고
 * 사용자의 기기를 쓰는 것이다. 여기서 한 번 펼쳐 파일로 박아둔다.
 *
 * ## 무작위를 쓰되 고정한다
 *
 * 바닥 얼룩 같은 것은 불규칙해야 방처럼 보인다. 다만 매번 다르면
 * **새로고침할 때마다 다른 사무실**이 되고, 그건 방이 아니라 화면 노이즈다.
 * 씨앗을 고정한 난수를 쓴다.
 *
 * 고칠 때: `node scripts/gen-office.mjs` → src/components/office-room.ts
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const OUT = join(dirname(fileURLToPath(import.meta.url)),
                 "..", "src", "components", "office-room.ts");

export const ROOM = { w: 240, h: 150 };

/** 씨앗 고정 난수 (mulberry32). 같은 씨앗이면 언제나 같은 방. */
function rng(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rects = [];
const r = (x, y, w, h, fill, extra = {}) =>
  rects.push({ x: +x.toFixed(1), y: +y.toFixed(1), w: +w.toFixed(1),
               h: +h.toFixed(1), fill, ...extra });

// ── 바닥 ────────────────────────────────────────────────────────────
r(0, 0, ROOM.w, ROOM.h, "floor");

// 마루 결. 세로줄만 그어도 바닥이 바닥으로 보인다.
for (let x = 0; x < ROOM.w; x += 10) r(x, 0, 0.6, ROOM.h, "floorLine");

// 바닥 얼룩 — 불규칙하되 고정
const rand = rng(20260922);
for (let i = 0; i < 26; i++) {
  const x = 8 + rand() * (ROOM.w - 20);
  const y = 10 + rand() * (ROOM.h - 22);
  r(x, y, 1.4 + rand() * 2.2, 1, "floorDot");
}

// ── 벽 ──────────────────────────────────────────────────────────────
const WALL = 7;
r(0, 0, ROOM.w, WALL, "wall");
r(0, 0, WALL, ROOM.h, "wall");
r(ROOM.w - WALL, 0, WALL, ROOM.h, "wall");
r(0, ROOM.h - WALL, ROOM.w, WALL, "wall");
// 걸레받이 — 벽과 바닥 사이에 선이 하나 있으면 깊이가 생긴다
r(WALL, WALL, ROOM.w - WALL * 2, 1.2, "wallEdge");

// ── 창문 둘 (왼쪽 벽) ───────────────────────────────────────────────
function window_(y) {
  r(0.8, y, 5.4, 26, "glass");
  r(0.8, y + 12, 5.4, 1, "wallEdge");
  r(0.2, y - 1.2, 6.6, 1.2, "wallEdge");
  r(0.2, y + 26, 6.6, 1.2, "wallEdge");
}
window_(30);
window_(86);

// ── 화이트보드 (위쪽 벽) ────────────────────────────────────────────
r(150, 1, 52, 5.5, "board");
r(156, 2.4, 18, 1, "boardInk");
r(156, 4.2, 30, 1, "boardInk");
r(190, 2.4, 9, 2.8, "boardInk");

// ── 벽쪽 책상 (개인 자리) ──────────────────────────────────────────
/** 개인 책상 하나. 회의 탁자에 모여 앉아 있어도 자기 자리는 있다. */
function deskAt(x, y, flip = false) {
  r(x, y, 34, 12, "desk");
  r(x, y, 34, 1, "deskEdge");
  // 모니터를 위에서 보면 화면 윗면과 받침만 보인다
  r(x + 11, y + (flip ? 7.5 : 2), 13, 3.4, "monitor");
  r(x + 16.5, y + (flip ? 6 : 5.6), 2, 1.6, "monitorStand");
  // 자판과 마우스
  r(x + 10, y + (flip ? 2.6 : 7), 14, 3, "keyboard");
  r(x + 26, y + (flip ? 3 : 7.4), 2.4, 2.4, "mouse", { rx: 1.2 });
  // 서류 더미
  r(x + 2.5, y + 3.5, 5, 5, "paper");
  r(x + 3.2, y + 2.8, 5, 5, "paper");
}
deskAt(14, 16);
deskAt(14, 118, true);
deskAt(192, 40);
deskAt(192, 96);

// ── 책장 · 캐비닛 (오른쪽 벽) ──────────────────────────────────────
for (let i = 0; i < 3; i++) {
  const y = 16 + i * 12;
  r(228, y, 9, 10, "shelf");
  r(229.5, y + 1.5, 1.6, 7, "book1");
  r(231.5, y + 1.5, 1.6, 7, "book2");
  r(233.5, y + 2.5, 1.6, 6, "book3");
}

// ── 커피 자리 (왼쪽 아래) ───────────────────────────────────────────
r(12, 92, 26, 11, "counter");
r(12, 92, 26, 1, "deskEdge");
r(15, 95, 6, 6, "machine");
r(16.2, 100, 3.6, 1.2, "machineDrip");
r(24, 96.5, 3.4, 3.4, "cup", { rx: 1.7 });
r(29, 96.5, 3.4, 3.4, "cup", { rx: 1.7 });

// ── 화분 ────────────────────────────────────────────────────────────
function plant(x, y, size) {
  r(x - size, y - size, size * 2, size * 2, "leaf", { rx: size });
  r(x - size * 0.45, y + size * 0.6, size * 0.9, size * 1.1, "pot");
}
plant(20, 138, 5.5);
plant(222, 136, 6.5);
plant(212, 14, 5);

// ── 서버랙 (오른쪽 아래) ────────────────────────────────────────────
r(196, 118, 22, 22, "rack");
for (let i = 0; i < 5; i++) {
  r(199, 121 + i * 4, 16, 2.4, "rackSlot");
  r(213, 121.6 + i * 4, 1.2, 1.2, "rackLed");
}

// ── 러그 (회의 탁자 아래) ───────────────────────────────────────────
r(76, 42, 92, 70, "rug", { rx: 8 });
r(80, 46, 84, 62, "rugInner", { rx: 6 });


// ── 문 (아래쪽 벽) ─────────────────────────────────────────────────
r(104, ROOM.h - 7.4, 34, 7.4, "door");
r(104, ROOM.h - 8.6, 34, 1.4, "doorFrame");
r(132, ROOM.h - 4.4, 2, 2, "doorKnob", { rx: 1 });

// ── 벽시계 (위쪽 벽) ───────────────────────────────────────────────
r(108, 0.6, 10, 5.8, "clock", { rx: 2 });
r(112.4, 1.8, 1, 2.6, "clockHand");
r(112.4, 3.6, 2.6, 1, "clockHand");

// ── 천장 조명이 바닥에 만드는 빛 웅덩이 ────────────────────────────
// 방이 통짜로 같은 밝기면 평면으로 보인다. 빛이 닿는 자리를 만든다.
[[62, 40], [178, 40], [62, 112], [178, 112]].forEach(([x, y]) => {
  r(x - 17, y - 11, 34, 22, "lightPool", { rx: 11 });
});

writeFileSync(
  OUT,
  `/**
 * 사무실 방 — **생성된 파일이다. 손으로 고치지 마세요.**
 *
 * 고치려면 \`frontend/scripts/gen-office.mjs\` 를 고치고 다시 돌린다:
 *
 *     node scripts/gen-office.mjs
 *
 * 가구 단위로 적은 것을 사각형으로 펼친 결과다. 왜 이렇게 하는지는
 * 생성기 머리말에 적혀 있다.
 */
export const ROOM = ${JSON.stringify(ROOM)};

export type Rect = {
  x: number; y: number; w: number; h: number; fill: string; rx?: number;
};

export const ROOM_RECTS: Rect[] = ${JSON.stringify(rects)};
`,
  "utf8",
);

console.log(`사각형 ${rects.length}개 → ${OUT}`);
