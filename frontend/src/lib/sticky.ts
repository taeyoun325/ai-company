"use client";

/**
 * 브라우저에만 있는 작은 설정값 (DAY 22).
 *
 * 레일을 접어뒀는지 같은 것. 서버는 알 수 없고 브라우저만 안다.
 *
 * ## 왜 useState + useEffect 가 아닌가
 *
 * effect 안에서 `setState` 로 읽어오면 그림을 한 번 그린 뒤 다시 그린다
 * (리액트가 경고한다). 그리고 서버가 만든 HTML 과 첫 그림이 달라져
 * 하이드레이션이 어긋난다.
 *
 * 이건 상태가 아니라 **바깥 저장소**다. `useSyncExternalStore` 는 서버용
 * 값과 브라우저용 값을 따로 받으므로 둘 다 해결된다.
 *
 * ## 저장이 실패해도 화면은 돈다
 *
 * 사생활 보호 모드에서는 `localStorage` 가 던진다. 그때는 이번 방문에만
 * 적용되고 다음에 다시 고르면 된다 — 화면이 깨지지는 않는다.
 */
import { useCallback, useSyncExternalStore } from "react";

const cache = new Map<string, boolean>();
const listeners = new Map<string, Set<() => void>>();

function read(key: string, fallback: boolean): boolean {
  if (cache.has(key)) return cache.get(key)!;
  let value = fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "1") value = true;
    else if (raw === "0") value = false;
  } catch {
    /* 못 읽으면 기본값 */
  }
  cache.set(key, value);
  return value;
}

export function useSticky(
  key: string, fallback: boolean,
): [boolean, (v: boolean) => void] {
  const subscribe = useCallback(
    (cb: () => void) => {
      const set = listeners.get(key) ?? new Set();
      set.add(cb);
      listeners.set(key, set);
      return () => {
        set.delete(cb);
      };
    },
    [key],
  );

  const value = useSyncExternalStore(
    subscribe,
    () => read(key, fallback),
    // 서버에는 브라우저 저장소가 없다. 언제나 기본값으로 그린다.
    () => fallback,
  );

  const set = useCallback(
    (next: boolean) => {
      cache.set(key, next);
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* 저장이 안 돼도 이번 방문에는 적용된다 */
      }
      listeners.get(key)?.forEach((fn) => fn());
    },
    [key],
  );

  return [value, set];
}
