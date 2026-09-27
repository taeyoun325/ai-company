"use client";

/**
 * 은하 배경 — 탭 카드 덱과 직원 쇼케이스가 같이 깐다.
 *
 * 탭마다(직원마다) 배경색을 바꾸던 것을 **하나로** 모았다. 색이 넘길 때마다
 * 바뀌면 화려하지만, 사무실 · 요금제 · 설정 · 설명이 한 회사라는 느낌이 흐려진다.
 * 탭은 가운데 카드와 뒤의 큰 아이콘으로 구별한다.
 *
 * 층: 짙은 남보라 바탕 → 성운 셋(보라 · 자홍 · 파랑, 흐리게) → 별 두 겹.
 *
 * 가볍게: 성운은 한 겹만 아주 천천히(90초) 돈다. 별은 그림 한 장(반복 무늬)이고
 * 두 겹 중 하나만 깜빡인다. 둘 다 CSS 애니메이션(globals.css 의 anim-*)이라
 * 합성 스레드에서 돈다 — JS 가 매 프레임 끼어들지 않는다. 성운에 blur 필터를
 * 걸지 않는다: 방사형 그라디언트가 이미 부드럽고, 화면보다 큰 층을 흐리면
 * 그림 한 장이 수 MB 가 된다. 움직임을 줄인 사람에게는 멈춰 있다.
 */

/** 바탕색. 덱 알약의 글자색 등 '짙은 색' 자리에도 쓴다. */
export const GALAXY_DEEP = "#1b1140";

// 별 — 여러 크기의 점을 반복 무늬로. 두 겹의 칸 크기를 어긋나게 해 되풀이가
// 눈에 띄지 않게 한다.
const STARS_A =
  "radial-gradient(1px 1px at 12% 18%, rgba(255,255,255,0.9), transparent 60%)," +
  "radial-gradient(1px 1px at 68% 42%, rgba(255,255,255,0.75), transparent 60%)," +
  "radial-gradient(1.5px 1.5px at 38% 72%, rgba(255,255,255,0.85), transparent 60%)," +
  "radial-gradient(1px 1px at 84% 86%, rgba(210,220,255,0.8), transparent 60%)," +
  "radial-gradient(1px 1px at 24% 52%, rgba(255,255,255,0.6), transparent 60%)," +
  "radial-gradient(1.2px 1.2px at 92% 12%, rgba(255,230,250,0.8), transparent 60%)";
const STARS_B =
  "radial-gradient(1.6px 1.6px at 30% 30%, rgba(255,255,255,0.95), transparent 60%)," +
  "radial-gradient(1px 1px at 75% 65%, rgba(200,215,255,0.9), transparent 60%)," +
  "radial-gradient(1.3px 1.3px at 55% 90%, rgba(255,255,255,0.8), transparent 60%)," +
  "radial-gradient(1px 1px at 8% 80%, rgba(255,220,245,0.85), transparent 60%)";

export function Galaxy() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden
      style={{
        background:
          `radial-gradient(120% 90% at 50% 110%, #2a1466 0%, transparent 60%),` +
          `linear-gradient(160deg, #0d0826 0%, ${GALAXY_DEEP} 45%, #0a0a2a 100%)`,
      }}>
      {/* 성운 — 크게 흐린 빛 세 덩이. 한 겹으로 묶어 천천히 돌린다. */}
      <div
        className="anim-galaxy absolute -inset-[25%]"
        style={{
          background:
            "radial-gradient(32% 28% at 30% 35%, rgba(139,92,246,0.45), transparent 100%)," +
            "radial-gradient(28% 24% at 70% 30%, rgba(236,72,153,0.30), transparent 100%)," +
            "radial-gradient(34% 30% at 62% 72%, rgba(59,130,246,0.34), transparent 100%)," +
            "radial-gradient(22% 20% at 22% 78%, rgba(45,212,191,0.18), transparent 100%)",
        }}
      />
      {/* 은하수 띠 — 비스듬한 옅은 빛. */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          background:
            "linear-gradient(115deg, transparent 30%, rgba(196,181,253,0.10) 45%," +
            " rgba(244,114,182,0.08) 52%, transparent 68%)",
        }}
      />
      {/* 별 두 겹 — 하나는 가만히, 하나는 천천히 깜빡인다. */}
      <div className="absolute inset-0"
        style={{ backgroundImage: STARS_A, backgroundSize: "220px 220px" }} />
      <div className="anim-twinkle absolute inset-0"
        style={{ backgroundImage: STARS_B, backgroundSize: "310px 290px" }} />
      {/* 가장자리를 눌러 가운데로 시선을 모은다. */}
      <div className="absolute inset-0"
        style={{ background:
          "radial-gradient(130% 110% at 50% 50%, transparent 55%, rgba(0,0,0,0.45))" }} />
    </div>
  );
}
