"use client";

/**
 * 사무실 한 장을 읽어 온다 (DAY 25 · backend/app/office.py).
 *
 * ## 왜 서버에 묻나
 *
 * 직원 상태 다섯 가지는 **제품의 규칙**이다("Mock 으로 끝낸 일은 완료가
 * 아니다" 같은 것). 화면이 이벤트를 접어 짐작하면 규칙이 두 곳에 살고,
 * 둘이 다르게 말하는 날 대표는 어느 쪽도 믿지 못한다.
 *
 * ## 얼마나 자주
 *
 * 일이 돌 때만 자주 읽는다. 결재를 기다리며 쉬는 실행은 사람이 움직이기
 * 전에는 바뀌지 않고, 아무 일도 없는 사무실은 거의 안 바뀐다. `pulse` 가
 * 바뀌면(로그에 단계·결재 이벤트가 오면) 기다리지 않고 바로 읽는다.
 *
 * 숨은 탭에서는 **주기적으로** 읽지 않는다 — `useStream` 과 같은 이유다
 * (연결 자리가 모자라 앱이 멈췄던 DAY 22). 다만 첫 한 장은 숨었어도
 * 읽는다: 탐색 직후 잠깐 `hidden` 인 브라우저가 있어서, 거기서 건너뛰면
 * 다음 주기(최대 15초)까지 사무실이 빈 칸으로 남았다. 다시 보이면 곧바로
 * 읽는다.
 *
 * ## 다른 실행으로 옮겨 가면
 *
 * 읽는 중인 요청이 있어도 **실행이 바뀌었으면** 새로 읽는다. 옛 실행의
 * 답이 늦게 오면 버린다 — 안 버리면 방금 연 사무실에 다른 프로젝트의
 * 사람들이 앉는다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import { useLang } from "./i18n";
import type { OfficeSnapshot } from "./types";

const FAST = 1500;
const SLOW = 5000;
const IDLE = 15000;

export function useOffice(run: string | null, pulse: unknown) {
  const { lang } = useLang();
  const [data, setData] = useState<OfficeSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  // 지금 읽는 중인 실행. 같은 실행을 겹쳐 읽지 않되, 다른 실행이면 막지 않는다.
  const inflight = useRef<string | null | undefined>(undefined);
  const want = useRef(run);
  const have = useRef(false);

  useEffect(() => {
    want.current = run;
  }, [run]);

  const load = useCallback(async (force = false) => {
    if (inflight.current === run) return;
    if (!force && have.current && typeof document !== "undefined" && document.hidden) {
      return;
    }
    inflight.current = run;
    try {
      const snap = await api.office(run);
      // 그 사이 다른 실행으로 옮겨 갔으면 이 답은 버린다.
      if (alive.current && want.current === run) {
        setData(snap);
        setError(null);
        have.current = true;
      }
    } catch (e) {
      if (alive.current && want.current === run) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (inflight.current === run) inflight.current = undefined;
    }
  }, [run]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // 실행이 바뀌거나 로그가 움직이면 바로. 언어가 바뀌어도 — 이유 문장은
  // 서버가 보는 사람의 언어로 쓴다.
  useEffect(() => {
    // `load` 는 응답을 **기다린 뒤에** 상태를 바꾼다(비동기). 린터는 그걸
    // 구분하지 못한다 — `useLoader` 와 같은 모양이다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(true);
  }, [load, pulse, lang]);

  // 다시 보이면 바로 한 장.
  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden) void load(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load]);

  const status = data?.run?.status;
  const every = !run ? IDLE : status === "running" ? FAST
    : status === "awaiting" ? SLOW : IDLE;
  useEffect(() => {
    const timer = setInterval(() => void load(), every);
    return () => clearInterval(timer);
  }, [load, every]);

  return { data, error, reload: () => load(true) };
}
