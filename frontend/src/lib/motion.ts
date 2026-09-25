/**
 * 움직임 한 곳 (DAY 20 · anime.js v4).
 *
 * ## 왜 헬퍼를 두나
 *
 * 애니메이션은 화면마다 따로 쓰기 시작하면 금방 어긋난다 — 여기는 300ms,
 * 저기는 700ms, 어떤 곳은 되감기가 없어서 라우트를 옮기면 반쯤 사라진
 * 요소가 남는다. 시간·가속도·정리를 여기서 한 번만 정한다.
 *
 * ## 안 움직이는 게 기본이다
 *
 * `prefers-reduced-motion` 을 켠 사람에게는 **아무것도 움직이지 않는다.**
 * 이건 취향 설정이 아니라 전정기관 질환자에게는 증상 유발 요인이다.
 * 그래서 "줄인 버전"이 아니라 "없음"이다 — 대신 최종 상태는 그대로 보인다.
 *
 * ## 숨겼으면 반드시 보여준다
 *
 * 등장 애니메이션은 요소를 먼저 숨긴다. 그 상태에서 스크립트가 실패하면
 * **글이 통째로 사라진 화면**이 남는다. 그래서 숨김은 CSS 가 아니라
 * `data-reveal` 로만 걸고, 이 모듈이 어떤 경로로 끝나든(성공·예외·
 * reduced-motion·스크립트 미실행) 마지막에는 항상 드러나게 둔다.
 */
import { animate, createScope, createTimeline, onScroll, stagger, svg,
         utils } from "animejs";
import type { FunctionValue, Scope } from "animejs";

export { animate, createScope, createTimeline, onScroll, stagger, svg, utils };

/** 화면 전체가 같은 리듬을 쓰도록 한 곳에 모은 값. */
export const T = {
  fast: 260,
  base: 460,
  slow: 760,
  /** 줄줄이 등장할 때의 간격. 이보다 길면 기다리는 느낌이 든다. */
  step: 70,
  /** 대부분의 등장에 쓰는 가속도. 끝에서 살짝 눌러준다. */
  ease: "out(3)",
  /** 튀어나오는 느낌이 필요한 곳에만. 남발하면 장난스러워진다. */
  pop: "spring(1, 80, 12, 0)",
} as const;

/**
 * `el` 을 실제로 스크롤하는 조상. 없으면 `document.body`.
 *
 * anime.js 의 `onScroll` 은 container 를 안 주면 **body** 를 본다. 그런데 이
 * 앱은 body 가 스크롤되지 않는다(레이아웃이 창 높이에 고정 · DAY 22) — 화면마다
 * 안쪽 div 가 스크롤된다. 그래서 스크롤에 묶인 움직임이 스크롤을 못 보고,
 * 등장 애니메이션은 4초 안전망이 드러낼 때까지 숨어 있었다(DAY 26 설명 탭을
 * 만들며 찾음). 가까운 스크롤 조상을 찾아 넘긴다.
 */
export function scrollParent(el: Element | null): HTMLElement {
  let cur = el?.parentElement ?? null;
  while (cur && cur !== document.body) {
    const oy = getComputedStyle(cur).overflowY;
    if (oy === "auto" || oy === "scroll") return cur;
    cur = cur.parentElement;
  }
  return document.body;
}

function firstOf(targets: string | Element | Element[] | NodeList): Element | null {
  if (typeof targets === "string") return document.querySelector(targets);
  if (targets instanceof Element) return targets;
  return (targets as ArrayLike<Element>)[0] ?? null;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * 숨겨둔 것들을 전부 드러낸다.
 *
 * 애니메이션이 돌든 안 돌든, 예외가 나든 안 나든 **반드시** 불린다.
 * 이 함수가 안 불리면 사용자는 빈 화면을 본다.
 */
export function revealAll(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>("[data-reveal]").forEach((el) => {
    el.removeAttribute("data-reveal");
  });
}

/**
 * 등장 애니메이션의 공통 설정.
 *
 * `data-reveal` 이 걸린 요소만 대상으로 한다. 애니메이션이 끝나면 그
 * 속성을 떼어낸다 — 남겨두면 나중에 다시 숨겨지는 규칙이 생겼을 때
 * 이미 등장한 요소까지 사라진다.
 */
export function revealFrom(
  targets: string | Element | Element[] | NodeList,
  opts: { y?: number; delay?: number | FunctionValue;
          scrollRoot?: Element | null } = {},
) {
  const { y = 14, delay = 0, scrollRoot = null } = opts;
  return animate(targets, {
    opacity: [0, 1],
    translateY: [y, 0],
    duration: T.base,
    delay,
    ease: T.ease,
    // 스크롤로 들어올 때만 도는 요소들. `repeat: false` 로 둬서 한 번
    // 본 것이 다시 사라졌다 나타나지 않게 한다 — 되풀이되면 읽던 사람이
    // 방해받는다.
    autoplay: scrollRoot
      ? onScroll({ target: scrollRoot as Element, enter: "bottom-=60 top",
                   container: scrollParent(scrollRoot ?? firstOf(targets)),
                   repeat: false })
      : true,
    onComplete: () => {
      const list = typeof targets === "string"
        ? document.querySelectorAll(targets)
        : targets instanceof Element
          ? [targets]
          : (targets as NodeList | Element[]);
      (list as NodeList).forEach?.((el) =>
        (el as HTMLElement).removeAttribute?.("data-reveal"));
    },
  });
}

/**
 * 컴포넌트 하나의 애니메이션 묶음.
 *
 * `createScope` 가 하는 일은 **되감기**다. 라우트를 옮기거나 다시
 * 그려질 때 되감지 않으면, 중간에 멈춘 인라인 스타일이 그대로 남아서
 * 반쯤 투명한 요소나 엉뚱한 위치가 화면에 붙는다.
 */
export function withScope(
  root: HTMLElement,
  build: (scope?: Scope) => void,
): () => void {
  if (prefersReducedMotion()) {
    revealAll(root);
    return () => {};
  }
  let scope: Scope | null = null;
  try {
    scope = createScope({ root }).add((s) => {
      build(s);
    });
  } catch (e) {
    // 애니메이션이 못 돌더라도 **내용은 보여야 한다.** 여기서 조용히
    // 끝내면 사용자는 고장난 화면이 아니라 빈 화면을 본다.
    revealAll(root);
    // 다만 조용히 삼키지는 않는다 — 삼키면 "움직임이 왜 없지"를 아무도 모른다
    // (DAY 26: 스크롤 등장이 통째로 안 돌던 것을 여기서 찾았다).
    console.warn("[motion] 애니메이션을 세우지 못해 내용만 보여줍니다:", e);
  }
  // 어떤 이유로든 타임라인이 끝까지 못 갈 수 있다(탭 전환, 느린 기기).
  // 마지막 안전망 — **화면에 들어와 있는데** 한참 지나도 숨어 있는 것만
  // 드러낸다 (DAY 26).
  //
  // 전에는 4초 뒤 **전부** 드러냈다. 그러면 스크롤해야 보이는 절은 4초가
  // 지나면 이미 다 나와 있어서, "그 자리에 왔을 때 올라온다"가 첫 4초 안에
  // 스크롤한 사람에게만 일어났다. 보는 사람에게 안 보이는 것만 막으면 된다.
  const net = watchStragglers(root);
  pendingReveal.get(root)?.();         // 방금 되감긴 같은 화면을 다시 세운다
  pendingReveal.delete(root);
  return () => {
    net();
    scope?.revert();
    // 되감자마자 **곧바로** 드러내지 않는다. 개발 모드의 리액트는 effect 를
    // 한 번 걷었다가 바로 다시 세우는데(StrictMode), 여기서 드러내면 다시 세울
    // 때 숨길 것이 남지 않아 등장이 통째로 사라졌다(DAY 26). 다음 틱까지
    // 아무도 다시 세우지 않으면 — 진짜로 떠난 것이면 — 그때 드러낸다.
    const t = window.setTimeout(() => {
      pendingReveal.delete(root);
      revealAll(root);
    }, 0);
    pendingReveal.set(root, () => window.clearTimeout(t));
  };
}

/** 되감긴 뒤 "곧 드러낼" 예약. 같은 화면이 다시 세워지면 취소한다. */
const pendingReveal = new WeakMap<HTMLElement, () => void>();

/** 화면 안에 1.8초 넘게 있는데도 숨어 있는 요소를 드러낸다. 끄는 함수를 돌려준다. */
function watchStragglers(root: HTMLElement): () => void {
  if (typeof IntersectionObserver === "undefined") {
    const t = window.setTimeout(() => revealAll(root), 4000);
    return () => window.clearTimeout(t);
  }
  const timers = new Map<Element, number>();
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const el = e.target as HTMLElement;
      if (e.isIntersecting && !timers.has(el)) {
        timers.set(el, window.setTimeout(() => {
          el.removeAttribute("data-reveal");
          io.unobserve(el);
        }, 1800));
      } else if (!e.isIntersecting && timers.has(el)) {
        window.clearTimeout(timers.get(el));
        timers.delete(el);
      }
    }
  });
  root.querySelectorAll("[data-reveal]").forEach((el) => io.observe(el));
  return () => {
    io.disconnect();
    timers.forEach((t) => window.clearTimeout(t));
  };
}
