"use client";

/**
 * 백엔드에서 화면 데이터를 불러오는 공통 훅.
 *
 * ## 왜 하나로 모으나
 *
 * 화면마다 `useEffect(() => { fetch... })` 를 다시 쓰면 세 가지를 빼먹는다:
 * 언마운트 후 setState(경고), 오류 표시, 그리고 다시 불러오기. 빼먹은
 * 화면은 "가끔 비어 있는 화면"이 되고, 원인을 찾기 어렵다.
 *
 * ## 왜 `key` 문자열로 의존성을 받나
 *
 * 호출부가 배열을 넘기면 린터가 그 배열을 검사하지 못하고(리터럴이 아니므로),
 * 인라인 `fetcher` 는 매 렌더마다 새 함수라서 그대로 의존성에 넣으면
 * 무한 호출이 된다. 그래서 **무엇이 바뀌면 다시 불러올지**를 문자열 하나로
 * 받는다 — 보통 slug 나 경로다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useErrorText } from "@/lib/i18n";

export interface Loader<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
}

export function useLoader<T>(key: string, fetcher: () => Promise<T>): Loader<T> {
  const errText = useErrorText();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  // 최신 fetcher 를 담아둔다. 의존성에 그대로 넣으면 인라인 함수가 매
  // 렌더마다 새로 만들어져 무한 호출이 된다. 갱신은 렌더 중이 아니라
  // effect 에서 한다 — 렌더 중 ref 쓰기는 동시성 모드에서 안전하지 않다.
  const fn = useRef(fetcher);
  useEffect(() => {
    fn.current = fetcher;
  }, [fetcher]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    try {
      const value = await fn.current();
      // 언마운트된 화면에 값을 넣으면 React 가 경고하고, 그 경고가 쌓이면
      // 진짜 경고가 묻힌다.
      if (!alive.current) return;
      setData(value);
      setError(null);
    } catch (e) {
      if (!alive.current) return;
      // 문장은 화면의 언어로 고른다. 백엔드에 닿지 못한 경우 여기서
      // `e.message` 를 그대로 쓰면 "TypeError: Failed to fetch" 가 목록
      // 자리에 찍힌다 — 사용자가 할 수 있는 일이 없는 문장이다.
      setError(errText(e));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [errText]);

  useEffect(() => {
    void reload();
    // key 가 바뀌면 다시 불러온다 (예: 다른 프로젝트로 이동).
  }, [key, reload]);

  return { data, error, loading, reload };
}
