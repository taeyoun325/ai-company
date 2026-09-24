"use client";

/**
 * 패널 폭 조절 손잡이 (DAY 24).
 *
 * 작업 로그·프로젝트 레일처럼 고정폭이던 칸의 경계에 붙는다. 드래그하는
 * 동안은 부모가 들고 있는 상태(`width`)만 바꾸고, 저장(localStorage)은
 * 손을 뗀 순간(`onCommit`) 한 번만 한다 — 드래그 중 매 픽셀마다 쓰면
 * 느려지고, 저장도 어차피 마지막 값만 의미가 있다.
 *
 * 마우스가 없는 사용자를 위해 방향키로도 조절할 수 있다.
 */
import { useEffect, useRef } from "react";

export function ResizeHandle({
  width,
  onChange,
  onCommit,
  min,
  max,
  side,
  label,
  className = "",
}: {
  width: number;
  onChange: (w: number) => void;
  onCommit: (w: number) => void;
  min: number;
  max: number;
  /** 이 손잡이가 칸의 **어느 쪽 테두리**인지.
   *  "left" = 칸의 왼쪽 변 (칸이 손잡이 오른쪽에 있다 — 예: 오른쪽
   *  작업 로그). 오른쪽으로 끌면 칸이 좁아진다.
   *  "right" = 칸의 오른쪽 변 (칸이 손잡이 왼쪽에 있다 — 예: 왼쪽
   *  레일). 오른쪽으로 끌면 칸이 넓어진다. */
  side: "left" | "right";
  label: string;
  /** 반응형 표시 여부(`hidden lg:block` 등)를 밖에서 넣는다. 감싸는
   *  div 를 하나 더 두면 그 div 가 flex 스트레치를 가로채서, 안의
   *  손잡이가 높이 0 으로 찌그러진다 — 그래서 감싸지 않고 직접 받는다. */
  className?: string;
}) {
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(width);
  // 드래그 중 마지막으로 계산한 폭. `width` prop 은 리액트가 다시 그려야
  // 갱신되는데, 손을 떼는 pointerup 이 그 전에(같은 틱에) 와버리면 `stop`
  // 이 여전히 **옛 값**을 커밋해서 드래그가 통째로 무효가 된다 — 그래서
  // `onChange` 가 부르는 그 순간의 값을 ref 에도 같이 적어둔다.
  const liveW = useRef(width);
  useEffect(() => {
    liveW.current = width;
  }, [width]);

  const clamp = (w: number) => Math.min(max, Math.max(min, w));

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = width;
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const dx = e.clientX - startX.current;
    const next = clamp(startW.current + (side === "left" ? -dx : dx));
    liveW.current = next;
    onChange(next);
  };

  const stop = () => {
    if (!dragging.current) return;
    dragging.current = false;
    onCommit(liveW.current);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const step = 24;
    if (e.key === "ArrowLeft") {
      onCommit(clamp(width + (side === "left" ? step : -step)));
    } else if (e.key === "ArrowRight") {
      onCommit(clamp(width + (side === "left" ? -step : step)));
    }
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={Math.round(width)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stop}
      onPointerCancel={stop}
      onKeyDown={onKeyDown}
      className={`group relative h-full w-2.5 shrink-0 cursor-col-resize
        touch-none select-none outline-none ${className}`}
    >
      <div
        className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-line
          transition-colors group-hover:bg-accent group-active:bg-accent
          group-focus-visible:bg-accent"
      />
    </div>
  );
}
