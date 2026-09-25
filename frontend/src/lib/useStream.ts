"use client";

/**
 * 실시간 작업 로그 구독 (지시서 §13).
 *
 * ## 왜 훅으로 빼나
 *
 * SSE 는 끊긴다. 프록시가 끊고, 노트북이 잠들고, 탭이 백그라운드로 간다.
 * 재연결·중복 제거·폴백을 화면마다 다시 쓰면 어떤 화면은 빼먹고, 그
 * 화면만 로그가 멈춘 것처럼 보인다.
 *
 * ## 두 겹으로 막는다
 *
 * 1. EventSource 가 끊기면 브라우저가 알아서 재연결하고, 이때 보내는
 *    `Last-Event-ID` 로 서버가 못 받은 것부터 준다.
 * 2. EventSource 자체가 막힌 환경(일부 프록시·확장)에서는 `/api/events`
 *    폴링으로 떨어진다. 한 경로에만 기대면 그 경로가 막혔을 때 화면이
 *    통째로 빈다.
 *
 * ## 이벤트를 무한히 쌓지 않는다
 *
 * 긴 실행은 수천 건을 낸다. 전부 들고 있으면 React 가 매 렌더에서 그걸
 * 훑고, 탭이 느려진다. 최근 것만 남긴다 — 전체는 서버에 있다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import { useLang } from "./i18n";
import type { BusEvent, Roster } from "./types";

const KEEP = 600;
const POLL_MS = 1500;

export interface StreamState {
  events: BusEvent[];
  roster: Roster;
  connected: boolean;
  /** SSE 가 막혀 폴링으로 떨어졌는가. 화면이 조용히 감추면 안 된다. */
  polling: boolean;
  clear: () => void;
}

export function useStream(run?: string): StreamState {
  const { lang } = useLang();
  // 탭이 보일 때만 연결한다 (DAY 22).
  //
  // EventSource 는 **오리진당 연결 하나**를 계속 물고 있는다. HTTP/1.1 에서
  // 브라우저는 오리진당 6개까지만 열 수 있으므로, 같은 앱을 탭 여러 개로
  // 열어두면 남은 자리가 빠르게 없어지고 **새 요청이 줄을 선 채 끝나지
  // 않는다.** 실제로 그 상태를 만들었다: 탭 넷을 띄워두니 "AUTO 로 맡기기"
  // 가 눌러도 아무 일이 없었고, POST /api/runs 가 응답 없이 매달렸다.
  // 같은 요청을 curl 로는 47ms 에 받았다 — 서버가 아니라 연결이 문제였다.
  //
  // 숨은 탭은 어차피 아무도 안 본다. 끊었다가 돌아올 때 다시 붙고,
  // `after`/`Last-Event-ID` 로 그동안의 이벤트를 받아오므로 잃는 것이 없다.
  const [awake, setAwake] = useState(
    typeof document === "undefined" || !document.hidden,
  );
  useEffect(() => {
    const onVisible = () => setAwake(!document.hidden);
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);
  const [events, setEvents] = useState<BusEvent[]>([]);
  const [roster, setRoster] = useState<Roster>({});
  const [connected, setConnected] = useState(false);
  // 서버에는 EventSource 가 없다. 그걸 초기값에 반영하면 서버는 true 로,
  // 브라우저는 false 로 그려서 하이드레이션이 깨진다(실제로 깨뜨려봤다).
  // 그래서 **양쪽이 같은 값**으로 시작하고, 판단은 아래 effect 에서 한다.
  const [polling, setPolling] = useState(false);
  const lastId = useRef(0);

  const push = useCallback((incoming: BusEvent[]) => {
    if (incoming.length === 0) return;
    setEvents((prev) => {
      // 재연결 직후에는 겹쳐 올 수 있다. id 로 거른다 — 안 거르면
      // 같은 말풍선이 두 번 뜨고, 사용자는 직원이 두 번 말했다고 믿는다.
      // 번호만으로 가르지 않고 **번호+시각**으로 가른다 (DAY 25). DAY 24
      // 까지 서버는 재시작할 때마다 번호를 1 부터 다시 셌다 — 그때 남은
      // 트레이스에는 같은 번호의 다른 사건이 섞여 있고, 번호로만 거르면
      // 재시작 뒤의 사건이 "이미 받은 것"으로 버려진다.
      const seen = new Set(prev.map(eventKey));
      const fresh = incoming.filter((e) => !seen.has(eventKey(e)));
      if (fresh.length === 0) return prev;
      const next = [...prev, ...fresh].sort((a, b) => a.ts - b.ts || a.id - b.id);
      return next.length > KEEP ? next.slice(next.length - KEEP) : next;
    });
    lastId.current = Math.max(lastId.current, ...incoming.map((e) => e.id));
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
    lastId.current = 0;
  }, []);

  // 이름·아이콘은 한 번만 받아두면 된다.
  useEffect(() => {
    let alive = true;
    api
      .events(run, 0)
      .then((b) => {
        if (!alive) return;
        setRoster(b.roster);
        push(b.events);
      })
      .catch(() => {
        /* 첫 조회 실패는 아래 연결이 다시 시도한다 */
      });
    return () => {
      alive = false;
    };
  }, [run, push]);

  useEffect(() => {
    if (typeof window === "undefined" || !("EventSource" in window)) {
      // effect 안의 동기 setState 다. 린터가 막는 패턴이지만 여기서는
      // 불가피하다 — 렌더 시점에 판단하면 하이드레이션이 깨지고(위 참조),
      // 이 분기는 EventSource 가 아예 없는 브라우저에서 딱 한 번 돈다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPolling(true);
      return;
    }
    // 언어를 **주소에** 싣는다. EventSource 는 헤더를 보낼 수 없어서
    // `Accept-Language` 가 이 요청에만 빠지고, 서버가 이 요청에서 만드는
    // 것들(직원 로스터의 직함)이 기본값인 한국어로 내려왔다 — 영어 화면의
    // 모든 말풍선에 "(전략가)" 가 붙어 있었다.
    if (!awake) {
      // 숨어 있는 동안에는 연결을 잡고 있지 않는다. 돌아오면 이 effect 가
      // 다시 돌아 새로 붙는다.
      return;
    }
    const url = `/api/stream?after=${lastId.current}&lang=${lang}${
      run ? `&run=${encodeURIComponent(run)}` : ""
    }`;
    const es = new EventSource(url);
    let failures = 0;

    const onMessage = (ev: MessageEvent) => {
      setConnected(true);
      setPolling(false);
      failures = 0;
      try {
        push([JSON.parse(ev.data) as BusEvent]);
      } catch {
        /* 깨진 줄 하나 때문에 스트림을 버리지 않는다 */
      }
    };

    // 서버가 event: <type> 으로 보내므로 기본 'message' 핸들러로는 안 온다.
    const types = [
      "message",
      "phase",
      "state",
      "done",
      "projects",
      "approval",
      "approval_done",
      "handoff",
      // DAY 25 — 승인 게이트 · 모델 호출 시간 · 결재 대기. 여기 빠지면
      // 서버가 보내도 화면이 못 받는다(SSE 는 이름으로 골라 듣는다).
      "gate",
      "awaiting",
      // `call`(모델 호출 시작·끝)은 듣지 않는다. 화면이 쓰지 않는데 받으면
      // 호출마다 두 줄씩 버퍼(KEEP)를 먹어서 정작 말풍선이 밀려난다 —
      // 지금 몇 초째인지는 사무실(/api/office)이 서버에서 접어 준다.
    ];
    types.forEach((t) => es.addEventListener(t, onMessage as EventListener));

    es.onopen = () => {
      setConnected(true);
      setPolling(false);
    };
    es.onerror = () => {
      setConnected(false);
      failures += 1;
      // 브라우저가 알아서 재연결하지만, 거듭 실패하면 이 경로 자체가
      // 막힌 것으로 보고 폴링으로 내려간다.
      if (failures >= 3) setPolling(true);
    };

    return () => {
      types.forEach((t) => es.removeEventListener(t, onMessage as EventListener));
      es.close();
    };
  }, [run, push, lang, awake]);

  useEffect(() => {
    if (!polling) return;
    let alive = true;
    const tick = async () => {
      try {
        const b = await api.events(run, lastId.current);
        if (!alive) return;
        setRoster(b.roster);
        push(b.events);
        setConnected(true);
      } catch {
        setConnected(false);
      }
    };
    const timer = setInterval(tick, POLL_MS);
    void tick();
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [polling, run, push]);

  return { events, roster, connected, polling, clear };
}

/** 사건 하나를 가리키는 열쇠. 번호가 겹친 옛 기록에서도 갈린다. */
export function eventKey(e: BusEvent): string {
  return `${e.id}:${e.ts}`;
}

/** 이벤트 흐름에서 현재 상태를 접어낸다 — 화면마다 다시 접지 않도록. */
export function foldState(events: BusEvent[]) {
  const out: {
    phase: string;
    detail: string;
    tasks: BusEvent["tasks"];
    files: string[];
    score: number | null;
    scoreDetail: BusEvent["score_detail"];
    round: number;
    usage: BusEvent["usage"];
    totals: BusEvent["totals"];
    project: BusEvent["project"];
    done: BusEvent | null;
  } = {
    phase: "",
    detail: "",
    tasks: undefined,
    files: [],
    score: null,
    scoreDetail: undefined,
    round: 0,
    usage: undefined,
    totals: undefined,
    project: undefined,
    done: null,
  };
  for (const e of events) {
    if (e.type === "phase") {
      out.phase = e.name ?? "";
      out.detail = e.detail ?? "";
    } else if (e.type === "state") {
      if (e.tasks) out.tasks = e.tasks;
      if (e.files) out.files = e.files;
      if (typeof e.score === "number") out.score = e.score;
      if (e.score_detail) out.scoreDetail = e.score_detail;
      if (typeof e.round === "number") out.round = e.round;
      if (e.usage) out.usage = e.usage;
      if (e.totals) out.totals = e.totals;
      if (e.project) out.project = e.project;
    } else if (e.type === "done") {
      out.done = e;
    }
  }
  return out;
}
