"use client";

/**
 * 이 화면이 탭 카드 덱(components/TabDeck) 안의 **카드**로 들어가 있는가,
 * 그리고 지금 가운데 자리인가.
 *
 * 덱은 네 탭을 전부 띄워 두고 한 장만 가운데에 세운다. 옆으로 비켜 있는
 * 카드가 창 전체의 키(←/→)를 들으면 가운데 카드의 키를 뺏는다 — 그래서
 * 창 전체를 듣는 화면은 `active` 일 때만 듣는다.
 *
 * 순환 import 를 피하려고 따로 둔다(TabDeck → 각 페이지 → 여기).
 */
import { createContext, useContext } from "react";

export const StackCtx = createContext<{
  inCard: boolean; active: boolean; wheel?: boolean; preview?: boolean;
  /** 휠로 첫 장 앞 · 끝 장 뒤로 넘기려 했다(-1 · 1). 전체 화면 미리보기가 닫힌다. */
  onEdge?: (dir: 1 | -1) => void;
  /** 폰에서 사무실 카드가 무엇을 보이나 — 평면도(floor)냐 지시창 · 작업 로그(log)냐.
   *  덱 아래 줄의 '사무실' · '작업 로그' 단추가 고른다. */
  officeView?: "floor" | "log";
}>({
  inCard: false,
  active: true,
});
// `wheel: false` — 긴 페이지 안에 박혀 있다(로그인 전 랜딩의 설명 미리보기).
// 휠은 그 페이지를 내려야 한다 — 설명 탭이 휠로 장을 넘기지 않는다.
// `preview: true` — 로그인 전이다. 사무실 · 요금제 · 설정으로 가는 버튼을 숨긴다
// (눌러도 갈 곳이 로그인 화면뿐이다).

export function useStack() {
  return useContext(StackCtx);
}
