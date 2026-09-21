/**
 * 아이콘 (DAY 20).
 *
 * ## 왜 이모지를 걷어냈나
 *
 * 🧭 🛠️ 🔍 ✍️ 🎨 로 직원을 표시하고 있었다. 빨리 만들기에는 좋지만
 * 세 가지가 걸린다:
 *
 * 1. **운영체제마다 다른 그림이 나온다.** 윈도우·맥·안드로이드가 각각
 *    다르게 그리고, 우리가 정한 색 체계(`--strategist` 등)와도 무관하게
 *    제멋대로 알록달록하다. 화면 두 곳이 다른 파랑을 쓰면 안 된다는
 *    §4 규칙이 이모지 앞에서만 예외가 되고 있었다.
 * 2. **급조한 티가 난다.** 이모지를 아이콘으로 쓰는 화면은 "만들다 만
 *    것"으로 읽힌다. 돈을 받는 제품에서 첫인상이 그러면 안 된다.
 * 3. 크기·굵기를 맞출 수 없다. 이모지는 글자라서 선 굵기가 없다.
 *
 * ## 직접 그린다
 *
 * 외부 아이콘 패키지를 넣지 않았다. 필요한 건 열 개뿐이고, 패키지는
 * 수백 개를 들고 오면서 라이선스 표기와 번들 크기를 함께 들고 온다.
 *
 * 규칙: 24×24 격자, 선 굵기 1.6, 색은 `currentColor`. 채우지 않는다 —
 * 채운 아이콘과 선 아이콘이 섞이면 한 화면에서 두 가지 무게가 보인다.
 *
 * ## 두 가지 모양으로 쓴다
 *
 * `<Icon>` 은 평범한 자리에, `glyph()` 는 **SVG 안에서** 쓴다(히어로
 * 도형). 같은 좌표계를 공유하려면 `<svg>` 를 중첩하는 대신 path 만
 * 꺼내 옮겨 붙여야 한다.
 */
import type { ReactNode } from "react";

export type IconName =
  | "strategist" | "developer" | "analyst" | "writer" | "designer"
  | "building" | "req" | "verify" | "package" | "person" | "system"
  | "plus" | "play" | "stop" | "panel";

/** 24×24 격자 위의 path 들. 바깥에서 stroke 속성을 걸어준다. */
const GLYPHS: Record<IconName, ReactNode> = {
  // 나침반 — 전략가. 방향을 정하는 사람이다.
  strategist: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M15.4 8.6 13.5 13.5 8.6 15.4 10.5 10.5Z" />
    </>
  ),
  // 꺾쇠 — 개발자. 망치보다 이쪽이 하는 일에 가깝다.
  developer: (
    <>
      <polyline points="9.2 7.8 4.8 12 9.2 16.2" />
      <polyline points="14.8 7.8 19.2 12 14.8 16.2" />
    </>
  ),
  // 돋보기 — 분석가(검증자).
  analyst: (
    <>
      <circle cx="10.8" cy="10.8" r="6.3" />
      <line x1="15.4" y1="15.4" x2="20" y2="20" />
    </>
  ),
  // 펜 — 작가.
  writer: (
    <>
      <path d="M5 19.2 5.9 15.5 16.3 5.1a1.9 1.9 0 0 1 2.7 2.7L8.6 18.2Z" />
      <line x1="14.7" y1="6.7" x2="17.4" y2="9.4" />
    </>
  ),
  // 팔레트 — 디자이너.
  designer: (
    <>
      <path d="M12 3.5a8.5 8.5 0 1 0 0 17c1 0 1.8-.8 1.8-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.1 0-1 .8-1.8 1.8-1.8h2.1a3.8 3.8 0 0 0 3.8-3.8A8.6 8.6 0 0 0 12 3.5Z" />
      <circle cx="8.3" cy="10.4" r="1.1" />
      <circle cx="11.4" cy="7.6" r="1.1" />
      <circle cx="15.4" cy="8.6" r="1.1" />
    </>
  ),
  // 건물 — 로고. 이 제품의 이름이 '회사'다.
  building: (
    <>
      <path d="M4.5 20V6.4a1 1 0 0 1 .72-.96l6.5-1.9a1 1 0 0 1 1.28.96V20" />
      <path d="M13 10h5.3a1 1 0 0 1 1 1V20" />
      <line x1="2.8" y1="20" x2="21.2" y2="20" />
      <line x1="7.4" y1="9.2" x2="9.6" y2="9.2" />
      <line x1="7.4" y1="12.6" x2="9.6" y2="12.6" />
      <line x1="7.4" y1="16" x2="9.6" y2="16" />
      <line x1="15.6" y1="13.4" x2="16.8" y2="13.4" />
      <line x1="15.6" y1="16.4" x2="16.8" y2="16.4" />
    </>
  ),
  // 문서 — 요구사항 한 줄.
  req: (
    <>
      <path d="M6.5 3.8h7L18 8.3V20.2H6.5Z" />
      <polyline points="13.5 3.8 13.5 8.3 18 8.3" />
      <line x1="9.2" y1="13" x2="15.2" y2="13" />
      <line x1="9.2" y1="16.4" x2="13.2" y2="16.4" />
    </>
  ),
  // 저울 — 교차검증. 판정하는 자리다.
  verify: (
    <>
      <line x1="12" y1="5.4" x2="12" y2="20" />
      <line x1="7.6" y1="20" x2="16.4" y2="20" />
      <line x1="5" y1="8" x2="19" y2="8" />
      <circle cx="12" cy="8" r="1.4" />
      <path d="M5 8 2.6 13.4h4.8Z" />
      <path d="M19 8 16.6 13.4h4.8Z" />
    </>
  ),
  // 상자 — 산출물. 파일로 남는다.
  package: (
    <>
      <path d="M12 3.6 20 8v8l-8 4.4L4 16V8Z" />
      <polyline points="4 8 12 12.4 20 8" />
      <line x1="12" y1="12.4" x2="12" y2="20.4" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8.6" r="3.6" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </>
  ),
  plus: (
    <>
      <line x1="12" y1="5.5" x2="12" y2="18.5" />
      <line x1="5.5" y1="12" x2="18.5" y2="12" />
    </>
  ),
  play: <path d="M8 5.5 18.5 12 8 18.5Z" />,
  // 왼쪽 칸이 있는 창 — 레일을 여닫는 버튼
  panel: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <line x1="9.5" y1="4.5" x2="9.5" y2="19.5" />
    </>
  ),
  stop: <rect x="6.5" y="6.5" width="11" height="11" rx="2" />,
  // 톱니 — 시스템이 하는 말. 사람이 한 말과 섞이면 안 된다.
  system: (
    <>
      <circle cx="12" cy="12" r="4" />
      <line x1="17.6" y1="12.0" x2="20.0" y2="12.0" />
      <line x1="16.0" y1="16.0" x2="17.7" y2="17.7" />
      <line x1="12.0" y1="17.6" x2="12.0" y2="20.0" />
      <line x1="8.0" y1="16.0" x2="6.3" y2="17.7" />
      <line x1="6.4" y1="12.0" x2="4.0" y2="12.0" />
      <line x1="8.0" y1="8.0" x2="6.3" y2="6.3" />
      <line x1="12.0" y1="6.4" x2="12.0" y2="4.0" />
      <line x1="16.0" y1="8.0" x2="17.7" y2="6.3" />
    </>
  ),
};

/** SVG 안에 끼워 넣을 때. 좌표계를 옮기는 것은 호출한 쪽 책임이다. */
export function glyph(name: IconName): ReactNode {
  return GLYPHS[name];
}

export function Icon({
  name,
  size = 20,
  className = "",
  strokeWidth = 1.6,
  ...rest
}: {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
} & React.SVGAttributes<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
      {...rest}
    >
      {GLYPHS[name]}
    </svg>
  );
}

/** 발화자 id → 아이콘. 모르는 id 는 사람 모양으로 떨어뜨린다.
 *
 * 서버도 `roster` 에 이모지를 실어 보내지만 화면은 그것을 쓰지 않는다.
 * 그림은 화면의 책임이다 — 백엔드가 이모지를 바꾸면 색 체계가 흔들린다. */
export function iconOfAgent(id: string): IconName {
  if (id === "SYSTEM") return "system";
  if (id === "USER") return "person";
  return (["strategist", "developer", "analyst", "writer", "designer"]
    .includes(id) ? id : "person") as IconName;
}
