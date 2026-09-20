"use client";

/**
 * 공개 랜딩 — 도메인에 처음 온 사람이 보는 화면 (DAY 18).
 *
 * ## 왜 로그인 창만 띄우지 않나
 *
 * 처음 온 사람에게 이메일 입력칸만 보여주면, 그는 **무엇에 가입하는지
 * 모른 채** 가입하거나 그냥 닫는다. 제품이 무엇인지 먼저 말한다.
 *
 * ## 비주얼 자리
 *
 * `<VisualSlot>` 이 히어로 영상·이미지가 들어갈 자리다. 지금은 회색
 * 박스가 아니라 **무엇이 들어가야 하는지 적힌 박스**다 — 빈 회색 박스는
 * "만들다 만 화면"으로 보이고, 외주로 넘길 때도 무엇을 만들어야 하는지
 * 전달되지 않는다.
 *
 * ## 과장하지 않는다
 *
 * 이 제품은 아직 실제 모델로 완주해본 적이 없다(STATUS.md). 랜딩에
 * "AI 가 알아서 다 해줍니다"라고 쓰면 그건 우리가 확인하지 않은 주장이다.
 * 할 수 있는 것만 쓴다. 나중에 실물로 검증되면 그때 고친다.
 */
import type { ReactNode } from "react";

import { Button, Panel } from "./ui";

const EMPLOYEES = [
  { id: "strategist", icon: "🧭", name: "전략가", what: "요구사항을 인수기준과 작업 목록으로 바꾼다", who: "Claude" },
  { id: "developer", icon: "🛠️", name: "개발자", what: "코드를 쓴다. 테스트는 볼 수 없다", who: "Claude" },
  { id: "analyst", icon: "🔍", name: "분석가", what: "다른 회사 모델로 교차검증한다", who: "Gemini" },
  { id: "writer", icon: "✍️", name: "작가", what: "문서와 카피를 쓴다", who: "GPT" },
  { id: "designer", icon: "🎨", name: "디자이너", what: "화면과 비주얼을 명세한다", who: "Gemini" },
];

const STEPS = [
  ["요구사항 한 줄", "CEO 가 무엇을 만들지 적는다"],
  ["전략가가 쪼갠다", "인수기준과 작업 목록으로"],
  ["분석가가 테스트를 먼저 쓴다", "구현자는 그 파일을 읽지도 못한다"],
  ["담당자가 만든다", "코드 · 문서 · 화면 명세"],
  ["교차검증", "다른 회사 모델이 코드 원문만 보고 판정"],
  ["반려면 다시", "통과할 때까지. 상한에 닿으면 멈춘다"],
];

export function Landing({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-5xl py-8">
      {/* ── 히어로 ── */}
      <section className="mb-10 text-center">
        <p className="text-4xl" aria-hidden>
          🏢
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
          AI 직원들이 실제 회사처럼 협업합니다
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-muted sm:text-base">
          당신은 CEO 입니다. 요구사항을 한 줄 적으면 전략가가 일을 쪼개고,
          담당자가 만들고, <strong className="text-fg">다른 회사의 모델</strong>이
          검증합니다.
        </p>
      </section>

      <VisualSlot
        title="히어로 영상"
        spec="사무실에 직원 다섯이 앉아 일하는 장면. 16:9, 8~12초, 무음 루프."
        note="Higgsfield 등에서 만들 자리입니다. 없어도 화면은 완성입니다."
        className="mb-10 h-56 sm:h-72"
      />

      {/* ── 가입 ── */}
      <section className="mb-12" id="start">
        <div className="mx-auto max-w-md">{children}</div>
      </section>

      {/* ── 직원 ── */}
      <section className="mb-12">
        <h2 className="mb-1 text-lg font-semibold">직원 다섯</h2>
        <p className="mb-4 text-xs text-dim">
          구현자와 검증자가 <strong>다른 회사</strong>의 모델입니다. 같은 모델끼리
          검토하면 같은 실수를 함께 놓칩니다.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EMPLOYEES.map((e) => (
            <div
              key={e.id}
              className="rounded-xl border border-line bg-panel p-3"
              style={{ ["--c" as string]: `var(--${e.id})` }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="grid size-8 place-items-center rounded-lg"
                  style={{
                    background: `color-mix(in srgb, var(--${e.id}) 16%, transparent)`,
                  }}
                  aria-hidden
                >
                  {e.icon}
                </span>
                <span className="text-sm font-semibold">{e.name}</span>
                <span className="ml-auto text-[11px] text-dim">{e.who}</span>
              </div>
              <p className="mt-2 text-xs text-muted">{e.what}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 흐름 ── */}
      <section className="mb-12">
        <h2 className="mb-4 text-lg font-semibold">어떻게 도나</h2>
        <ol className="space-y-2">
          {STEPS.map(([title, detail], i) => (
            <li key={title} className="flex gap-3 rounded-lg bg-panel2 px-3 py-2">
              <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border border-line text-[11px] tabular-nums text-dim">
                {i + 1}
              </span>
              <span className="min-w-0">
                <span className="text-sm font-medium">{title}</span>
                <span className="block text-xs text-dim">{detail}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      {/* ── 정직한 항목 ── */}
      <section className="mb-10">
        <Panel title="지금 상태 — 정직하게">
          <ul className="space-y-1.5 text-xs text-muted">
            <li>
              · 순서는 <strong className="text-fg">코드가</strong> 정합니다. 모델이
              고르는 것은 태스크별 담당자 하나뿐이고, 그것도 검사 없이 따르지
              않습니다.
            </li>
            <li>
              · 비용은 호출 <strong className="text-fg">전에</strong> 막습니다.
              라운드·재작업·예산·크레딧 상한이 각각 있습니다.
            </li>
            <li>
              · 만든 산출물은 파일로 남고, 회차별로 무엇이 바뀌었는지 볼 수
              있습니다.
            </li>
            <li style={{ color: "var(--warn)" }}>
              · 아직 실제 모델로 완주한 기록이 없습니다. API 키가 없으면 Mock
              직원이 대본대로 움직이고, 화면 곳곳에 <code>MOCK</code> 배지가
              붙습니다.
            </li>
          </ul>
        </Panel>
      </section>

      <div className="text-center">
        <Button
          tone="primary"
          onClick={() => {
            document.getElementById("start")?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          시작하기
        </Button>
      </div>
    </div>
  );
}

/**
 * 비주얼이 들어갈 자리.
 *
 * 빈 회색 박스로 두지 않는다 — 그건 "만들다 만 화면"으로 보이고, 외주로
 * 넘길 때 무엇을 만들어야 하는지도 전달되지 않는다. 규격을 적어둔다.
 */
export function VisualSlot({
  title,
  spec,
  note,
  className = "",
}: {
  title: string;
  spec: string;
  note?: string;
  className?: string;
}) {
  return (
    <div
      className={`grid place-items-center rounded-xl border border-dashed px-4 text-center ${className}`}
      style={{
        borderColor: "color-mix(in srgb, var(--accent) 35%, transparent)",
        background: "color-mix(in srgb, var(--accent) 5%, transparent)",
      }}
    >
      <div>
        <p className="text-sm font-medium" style={{ color: "var(--accent)" }}>
          {title}
        </p>
        <p className="mt-1 text-xs text-muted">{spec}</p>
        {note && <p className="mt-1 text-[11px] text-dim">{note}</p>}
      </div>
    </div>
  );
}
