"use client";

/**
 * 화면 폭을 리액트 상태로 (DAY 22).
 *
 * ## 왜 CSS 만으로 안 되나
 *
 * 폭에 따라 **보이는 것**이 달라지는 것은 CSS 로 충분하다. 그런데 좁은
 * 화면의 프로젝트 레일은 보이는 것만 다른 게 아니라 **동작이 다르다** —
 * 넓을 때는 옆에 붙어 있고(자리를 차지하고), 좁을 때는 위에 겹쳐 뜬다
 * (자리를 차지하지 않고, 배경을 누르면 닫힌다). 열림 상태도 다르게
 * 기억해야 한다: 넓은 화면의 "펼쳐둠"을 폰에서 그대로 쓰면 첫 화면이
 * 목록으로 덮인다.
 *
 * ## 왜 `useSyncExternalStore` 인가
 *
 * `useEffect` 로 `setState` 하면 서버가 그린 화면과 브라우저가 그린 화면이
 * 한 번 어긋난다(하이드레이션 경고). 이건 상태가 아니라 **바깥 값**이므로
 * 바깥 저장소로 읽는다 — `lib/i18n.tsx` · `lib/sticky.ts` 와 같은 방식이다.
 *
 * 서버에는 창이 없다. 서버용 값은 **넓은 화면**으로 둔다 — 첫 그림이
 * 데스크톱 기준으로 나오고, 브라우저에서 좁으면 곧바로 좁은 쪽으로 바뀐다.
 */
import { useSyncExternalStore } from "react";

function subscribe(query: string) {
  return (onChange: () => void) => {
    const mql = window.matchMedia(query);
    // Safari 14 이전에는 addEventListener 가 없다. 그 경우는 조용히
    // 구독하지 않는다 — 첫 값은 맞고, 돌리는 도중 창 크기를 바꾸는
    // 사람만 놓친다.
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  };
}

export function useMedia(query: string, serverValue = true): boolean {
  return useSyncExternalStore(
    subscribe(query),
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}

/** Tailwind 의 `md` 와 같은 기준. 레일이 옆에 붙을 수 있는 폭. */
export function useWide(): boolean {
  return useMedia("(min-width: 768px)");
}
