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

import { useErrorText, useLang } from "@/lib/i18n";

export interface Loader<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
}

/**
 * 값이 **바뀔 때만** 다시 읽는다 (DAY 22).
 *
 * 이게 없으면 화면마다 이렇게 쓰게 된다:
 *
 *     const { reload } = useLoader("rail", fetch);
 *     useEffect(() => { void reload(); }, [refreshKey, reload]);
 *
 * 그러면 **마운트 때 두 번** 읽는다 — `useLoader` 가 한 번, 이 effect 가
 * 한 번. 개발 모드의 StrictMode 중복과 섞여서 안 보였는데, 프로덕션
 * 빌드로 확인하니 `/api/projects` 만 두 번씩 나가고 있었다.
 *
 * 첫 실행을 건너뛰면 "처음 한 번"은 `useLoader` 가, "바뀔 때마다"는
 * 여기가 맡는다.
 */
export function useReloadOn(value: unknown, reload: () => Promise<void>) {
  const seen = useRef<unknown>(undefined);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      seen.current = value;
      return;
    }
    if (seen.current === value) return;
    seen.current = value;
    void reload();
  }, [value, reload]);
}


export function useLoader<T>(key: string, fetcher: () => Promise<T>): Loader<T> {
  const { lang } = useLang();
  const errText = useErrorText();
  // `errText` 는 언어가 정해지는 순간 신원이 바뀐다. 그걸 `reload` 의
  // 의존성에 그대로 두면 **마운트 직후 한 번 더 읽는다** — 화면이 뜰 때
  // 언어가 서버 기본값에서 저장된 값으로 한 번 바뀌기 때문이다.
  // 프로덕션 빌드로 재보니 `/api/projects` 가 그렇게 두 번씩 나가고
  // 있었다(개발 모드의 StrictMode 중복에 가려 안 보였다).
  const say = useRef(errText);
  useEffect(() => {
    say.current = errText;
  }, [errText]);
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
      setError(say.current(e));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    // key 가 바뀌면 다시 불러온다 (예: 다른 프로젝트로 이동).
  }, [key, reload]);

  // 언어가 **바뀌면** 다시 읽는다. 응답에는 서버가 언어에 맞춰 보낸 글이
  // 섞여 있다(직원 직함·요금제 이름). 첫 실행은 건너뛴다 — 위에서 이미
  // 읽었고, 그걸 안 건너뛰면 방금 고친 중복이 그대로 돌아온다.
  useReloadOn(lang, reload);

  return { data, error, loading, reload };
}
