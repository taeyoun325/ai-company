"use client";

/**
 * 공개 랜딩 — 도메인에 처음 온 사람이 보는 화면 (DAY 18 · DAY 20 개편).
 *
 * ## 이 화면이 유일한 체험 창구다
 *
 * DAY 19 에 무료 요금제를 없앴다. 이제 계정을 만들어도 결제 전에는
 * 아무것도 돌려볼 수 없다. 그 말은 **로그인 이전의 이 화면이 제품을
 * 보여줄 마지막 자리**라는 뜻이다. 여기서 이해시키지 못하면 결제 버튼은
 * 눌리지 않는다.
 *
 * ## 그래서 움직인다. 다만 장식으로 움직이지는 않는다
 *
 * 히어로의 도형은 코드에 실제로 있는 순서를 그린다 — 테스트가 먼저
 * 쓰이고, 다른 회사 모델이 판정하고, 반려되면 되돌아간다. 움직임이
 * 없으면 이 순서는 글로 읽어야 하고, 글로 읽는 사람은 다섯 줄째에서
 * 떠난다.
 *
 * 나머지 움직임은 **등장**뿐이다. 계속 흔들리는 요소를 두지 않는다 —
 * 읽는 중에 움직이는 것은 읽기를 방해한다.
 *
 * ## 과장하지 않는다
 *
 * 이 제품은 아직 실제 모델로 완주해본 적이 없다(STATUS.md). "AI 가
 * 알아서 다 해줍니다"는 우리가 확인하지 않은 주장이다. 할 수 있는 것만
 * 쓰고, 못 하는 것은 아래 '지금 상태' 에 그대로 적는다. 랜딩에서 부풀린
 * 만큼 첫 결제 다음 날 환불로 돌아온다.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

import { PipelineFigure } from "./PipelineFigure";
import { Button, Panel } from "./ui";
import { api } from "@/lib/api";
import { T, revealFrom, stagger, withScope } from "@/lib/motion";
import type { PlanRow } from "@/lib/types";

const EMPLOYEES = [
  { id: "strategist", icon: "🧭", name: "전략가", what: "요구사항을 인수기준과 작업 목록으로 바꾼다", who: "Claude" },
  { id: "developer", icon: "🛠️", name: "개발자", what: "코드를 쓴다. 테스트는 볼 수 없다", who: "Claude" },
  { id: "analyst", icon: "🔍", name: "분석가", what: "다른 회사 모델로 교차검증한다", who: "Gemini" },
  { id: "writer", icon: "✍️", name: "작가", what: "문서와 카피를 쓴다", who: "GPT" },
  { id: "designer", icon: "🎨", name: "디자이너", what: "화면과 비주얼을 명세한다", who: "Gemini" },
];

const PROOFS = [
  ["순서는 코드가 정한다", "모델이 고르는 것은 태스크별 담당자 하나뿐이고, 그것도 검사 없이 따르지 않는다"],
  ["테스트가 먼저 쓰인다", "구현자는 tests/ 를 읽지도 못한다. 읽을 수 있으면 통과시키는 코드를 쓴다"],
  ["검증은 다른 회사 모델", "같은 회사 모델끼리 보면 같은 실수를 함께 놓친다"],
  ["비용은 호출 전에 막는다", "사후 감지는 상한이 아니라 부고다"],
];

export function Landing({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [plans, setPlans] = useState<Record<string, PlanRow> | null>(null);

  // 가격은 서버가 가진 것 하나뿐이다. 랜딩에 숫자를 적어두면 요금제를
  // 바꾼 날 **여기만 옛날 가격**이 남는다. 못 불러오면 요금제 칸을
  // 통째로 비운다 — 틀린 가격보다 없는 가격이 낫다.
  useEffect(() => {
    let alive = true;
    api
      .plans()
      .then((r) => alive && setPlans(r.plans))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    return withScope(el, () => {
      // 히어로는 스크롤을 기다리지 않는다. 이미 보이는 것이다.
      revealFrom(".hero-line", { y: 18, delay: stagger(90) });
      revealFrom(".hero-figure", { y: 26, delay: 320 });
      revealFrom(".hero-cta", { y: 12, delay: 480 });

      // 아래 구역은 그 자리에 왔을 때 나타난다. 한꺼번에 다 움직이면
      // 어디를 봐야 하는지가 사라진다.
      el.querySelectorAll<HTMLElement>("[data-reveal-group]").forEach((g) => {
        revealFrom(g.querySelectorAll("[data-reveal]"), {
          delay: stagger(T.step),
          scrollRoot: g,
        });
      });
    });
  }, [plans]);

  return (
    <div ref={root} className="mx-auto max-w-5xl px-4 py-10">
      {/* ── 히어로 ─────────────────────────────────────────── */}
      <section className="text-center">
        <p
          className="hero-line inline-flex items-center gap-2 rounded-full border
            border-line bg-panel px-3 py-1 text-[11px] text-muted"
          data-reveal
        >
          <span className="size-1.5 rounded-full" style={{ background: "var(--ok)" }} />
          AI 직원 5명 · 제공자 3사 · 교차검증
        </p>
        <h1
          className="hero-line mt-4 text-3xl font-bold leading-tight tracking-tight sm:text-5xl"
          data-reveal
        >
          AI 직원들이
          <br className="sm:hidden" /> 실제 회사처럼 협업합니다
        </h1>
        <p
          className="hero-line mx-auto mt-4 max-w-2xl text-sm text-muted sm:text-base"
          data-reveal
        >
          당신은 CEO 입니다. 요구사항을 한 줄 적으면 전략가가 일을 쪼개고,
          담당자가 만들고,{" "}
          <strong className="text-fg">다른 회사의 모델</strong>이 검증합니다.
          통과할 때까지 돌고, 상한에 닿으면 멈춥니다.
        </p>
      </section>

      {/* ── 흐름 도형 ──────────────────────────────────────── */}
      <section className="hero-figure mt-8" data-reveal>
        <div className="rounded-2xl border border-line bg-panel p-4 sm:p-6">
          <PipelineFigure />
          <p className="mt-2 text-center text-[11px] text-dim">
            이 그림은 코드에 실제로 있는 순서입니다 — 테스트가 먼저 쓰이고,
            반려되면 되돌아갑니다.
          </p>
        </div>
      </section>

      <div className="hero-cta mt-6 text-center" data-reveal>
        <Button
          tone="primary"
          onClick={() =>
            document.getElementById("start")?.scrollIntoView({ behavior: "smooth" })
          }
        >
          시작하기
        </Button>
      </div>

      {/* ── 우리가 다르게 하는 것 ──────────────────────────── */}
      <section className="mt-16" data-reveal-group>
        <h2 className="text-lg font-semibold" data-reveal>
          왜 이렇게 만들었나
        </h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {PROOFS.map(([title, detail]) => (
            <div
              key={title}
              className="rounded-xl border border-line bg-panel p-4"
              data-reveal
            >
              <p className="text-sm font-semibold">{title}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{detail}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 직원 ──────────────────────────────────────────── */}
      <section className="mt-16" data-reveal-group>
        <h2 className="text-lg font-semibold" data-reveal>
          직원 다섯
        </h2>
        <p className="mt-1 text-xs text-dim" data-reveal>
          구현자와 검증자가 <strong>다른 회사</strong>의 모델입니다. 대체 사슬도
          회사를 건너게 걸었습니다.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {EMPLOYEES.map((e) => (
            <div
              key={e.id}
              className="emp-card rounded-xl border border-line bg-panel p-3
                transition-transform duration-200 hover:-translate-y-0.5"
              data-reveal
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

      {/* ── 요금제 ────────────────────────────────────────── */}
      {plans && (
        <section className="mt-16" data-reveal-group>
          <h2 className="text-lg font-semibold" data-reveal>
            요금제
          </h2>
          <p className="mt-1 text-xs text-dim" data-reveal>
            무료 요금제는 없습니다. Mock 으로 만든 산출물을 체험이라고 부르지
            않기로 했습니다 — 계정을 만든 분께는 실제 모델만 드립니다.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(plans).map(([name, p]) => (
              <div
                key={name}
                className="flex flex-col rounded-xl border border-line bg-panel p-4"
                data-reveal
              >
                <p className="text-xs text-dim">{p.label}</p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  ${p.price_usd}
                  <span className="text-xs font-normal text-dim"> / 월</span>
                </p>
                <p className="mt-2 text-xs text-muted">
                  {p.source === "byok"
                    ? "모델 요금은 내 API 키로 직접"
                    : `월 ${p.credits.toLocaleString()} 크레딧`}
                </p>
                <p className="mt-0.5 text-[11px] text-dim">
                  동시 실행 {p.max_concurrent}건
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-dim" data-reveal>
            자체 키 요금제는 본인 API 키로 돌립니다. 모델 요금을 제공자가 직접
            청구하므로 더 쌉니다.
          </p>
        </section>
      )}

      {/* ── 가입 ──────────────────────────────────────────── */}
      <section className="mt-16 scroll-mt-8" id="start" data-reveal-group>
        <div className="mx-auto max-w-md" data-reveal>
          {children}
        </div>
      </section>

      {/* ── 정직한 항목 ───────────────────────────────────── */}
      <section className="mt-16" data-reveal-group>
        <div data-reveal>
          <Panel title="지금 상태 — 정직하게">
            <ul className="space-y-1.5 text-xs leading-relaxed text-muted">
              <li>
                · 만든 산출물은 파일로 남고, 회차별로 무엇이 바뀌었는지 볼 수
                있습니다.
              </li>
              <li>
                · 프롬프트 주입을 완전히 막지는 못합니다. 대신 설득당한 직원도{" "}
                <strong className="text-fg">권한 밖 파일은 쓰지 못합니다.</strong>
              </li>
              <li style={{ color: "var(--warn)" }}>
                · 아직 실제 모델로 완주한 기록이 없습니다. 키가 없으면 Mock
                직원이 대본대로 움직이고, 화면 곳곳에 <code>MOCK</code> 배지가
                붙습니다.
              </li>
              <li style={{ color: "var(--warn)" }}>
                · 결제 연동이 아직 없습니다. 크레딧은 실제로 줄고 실제로
                막히지만, 충전 버튼은 데모입니다.
              </li>
            </ul>
          </Panel>
        </div>
      </section>

      <p className="mt-10 text-center text-[11px] text-dim">
        움직임을 줄이는 설정(<code>prefers-reduced-motion</code>)을 켜두셨다면
        이 화면은 움직이지 않습니다.
      </p>
    </div>
  );
}
