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

// ── 이번 탭에서만(DAY 24 — Mock 경고 닫기) ────────────────────────────
//
// `useSticky` 와 같은 모양이지만 `sessionStorage` 를 쓴다 — 탭을 닫았다
// 새로 열면 다시 보여야 하는 값(예: 닫은 경고)은 `localStorage` 에 두면
// 영영 안 보이게 된다.
const sessionCache = new Map<string, boolean>();
const sessionListeners = new Map<string, Set<() => void>>();

function readSession(key: string, fallback: boolean): boolean {
  if (sessionCache.has(key)) return sessionCache.get(key)!;
  let value = fallback;
  try {
    value = window.sessionStorage.getItem(key) === "1";
  } catch {
    /* 못 읽으면 기본값 */
  }
  sessionCache.set(key, value);
  return value;
}

export function useSessionFlag(key: string): [boolean, () => void] {
  const subscribe = useCallback(
    (cb: () => void) => {
      const set = sessionListeners.get(key) ?? new Set();
      set.add(cb);
      sessionListeners.set(key, set);
      return () => {
        set.delete(cb);
      };
    },
    [key],
  );

  const value = useSyncExternalStore(
    subscribe,
    () => readSession(key, false),
    // 서버에는 세션 저장소가 없다. 언제나 "닫지 않음"으로 그린다.
    () => false,
  );

  const setTrue = useCallback(() => {
    sessionCache.set(key, true);
    try {
      window.sessionStorage.setItem(key, "1");
    } catch {
      /* 저장이 안 돼도 이번 화면에서는 닫힌 채로 남는다 */
    }
    sessionListeners.get(key)?.forEach((fn) => fn());
  }, [key]);

  return [value, setTrue];
}

// ── 폭 (DAY 24 — 작업 로그 · 레일 크기 조절) ──────────────────────────
//
// 불리언과 같은 이유로 `useSyncExternalStore` 를 쓴다: 서버는 브라우저가
// 저장해둔 폭을 모르므로 첫 그림은 항상 기본 폭이다.
const numCache = new Map<string, number>();
const numListeners = new Map<string, Set<() => void>>();

function readNumber(key: string, fallback: number): number {
  if (numCache.has(key)) return numCache.get(key)!;
  let value = fallback;
  try {
    const raw = window.localStorage.getItem(key);
    const n = raw === null ? NaN : Number(raw);
    if (Number.isFinite(n)) value = n;
  } catch {
    /* 못 읽으면 기본값 */
  }
  numCache.set(key, value);
  return value;
}

export function useStickyNumber(
  key: string, fallback: number,
): [number, (v: number) => void] {
  const subscribe = useCallback(
    (cb: () => void) => {
      const set = numListeners.get(key) ?? new Set();
      set.add(cb);
      numListeners.set(key, set);
      return () => {
        set.delete(cb);
      };
    },
    [key],
  );

  const value = useSyncExternalStore(
    subscribe,
    () => readNumber(key, fallback),
    () => fallback,
  );

  const set = useCallback(
    (next: number) => {
      numCache.set(key, next);
      try {
        window.localStorage.setItem(key, String(next));
      } catch {
        /* 저장이 안 돼도 이번 방문에는 적용된다 */
      }
      numListeners.get(key)?.forEach((fn) => fn());
    },
    [key],
  );

  return [value, set];
}
