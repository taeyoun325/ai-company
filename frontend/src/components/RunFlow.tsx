"use client";

/**
 * 일이 도는 순서 — 엔진(backend/app/orchestrator/engine.py)이 **실제로 도는
 * 순서** 그대로 그린다. 랜딩 히어로와 설명서 '흐름' 장이 같이 쓴다.
 *
 * ## 왜 다시 그렸나
 *
 * 처음 그림(PipelineFigure, DAY 20)은 개발자 한 줄만 그렸다. 작가 · 디자이너
 * 슬롯, 동시 실행, 슬롯마다의 pytest, 승인 지점, 최종 검수가 빠져 있었고, 대표가
 * "이대로 작동하지 않는다"고 짚었다(2026-10-08). 숫자도 코드와 같게 적는다:
 * 동시 3(`MAX_PARALLEL_TASKS`), 반려 3번째에 포기(`MAX_REWORK`).
 *
 * 합치는 단계는 그리지 않는다 — 없다. 슬롯이 쓰는 순간 파일이 프로젝트에 들어가고,
 * 포기한 슬롯만 되돌린다.
 *
 * ## 정적이다
 *
 * 움직이는 점이 선을 따라 흐르던 연출은 뺐다. 흐름을 이해시키는 것은 칸의 순서와
 * 글이고, 연출은 잘못된 순서를 그럴듯하게 보이게도 만든다.
 */
import { Icon, type IconName } from "./icons";
import { type Key, useLang } from "@/lib/i18n";

function FlowArrow() {
  return (
    <span aria-hidden className="grid shrink-0 place-items-center text-dim md:px-0.5">
      <span className="hidden md:inline">→</span><span className="md:hidden">↓</span>
    </span>
  );
}

function FlowGate({ label }: { label: string }) {
  const { t } = useLang();
  return (
    <span className="mt-1.5 inline-flex flex-col items-center gap-0.5">
      <span className="whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px]"
        style={{ borderColor: "var(--st-approval)", color: "var(--st-approval)" }}>
        ★ {label}
      </span>
      <span className="text-[9px] text-dim">{t("guide.rf.optional")}</span>
    </span>
  );
}

function FlowNode({ who, title, sub, icon, gate }: {
  who: string; title: string; sub: string; icon: IconName; gate?: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center justify-center rounded-xl border
      border-line bg-panel2 px-1.5 py-2.5 text-center">
      <span className="grid size-8 place-items-center rounded-full border-2"
        style={{ borderColor: `var(--${who}, var(--line-strong))` }}>
        <Icon name={icon} size={15} style={{ color: `var(--${who}, var(--fg))` }} />
      </span>
      <span className="mt-1 text-[12px] font-semibold leading-tight">{title}</span>
      <span className="text-[10px] leading-tight text-dim">{sub}</span>
      {gate && <FlowGate label={gate} />}
    </div>
  );
}

export function RunFlow() {
  const { t } = useLang();
  const lanes: { who: "developer" | "writer" | "designer"; slot: string }[] = [
    { who: "developer", slot: "t1" }, { who: "writer", slot: "t2" },
    { who: "designer", slot: "t3" },
  ];
  return (
    <div data-testid="run-flow"
      className="flex flex-col items-stretch gap-1.5 rounded-2xl border border-line bg-panel p-3
        md:flex-row">
      <FlowNode who="ceo" icon="person" title={t("guide.rf.order")} sub={t("guide.rf.order.sub")} />
      <FlowArrow />
      <FlowNode who="strategist" icon="strategist" title={t("guide.rf.plan")}
        sub={`${t("role.strategist")} · ${t("guide.rf.plan.sub")}`} gate={t("gate.plan")} />
      <FlowArrow />
      <FlowNode who="analyst" icon="analyst" title={t("guide.rf.tests")}
        sub={`${t("role.analyst")} · ${t("guide.rf.tests.sub")}`} />
      <FlowArrow />
      <div className="flex min-w-0 flex-[3.2] flex-col rounded-xl border border-line bg-panel2
        px-2.5 py-2">
        <span className="text-[11px] font-semibold text-muted">{t("guide.rf.lanes")}</span>
        <ul className="mt-1 space-y-1">
          {lanes.map((l) => (
            <li key={l.slot} className="flex items-center gap-1 whitespace-nowrap text-[10.5px]">
              <span className="shrink-0 font-semibold"
                style={{ color: `var(--${l.who})` }}>{l.slot} · {t(`role.${l.who}` as Key)}</span>
              <span className="rounded bg-panel px-1.5 py-0.5">{t("guide.rf.write")}</span>
              <span aria-hidden className="text-dim">→</span>
              <span className="rounded bg-panel px-1.5 py-0.5 font-mono">{t("guide.rf.pytest")}</span>
              <span aria-hidden className="text-dim">→</span>
              <span className="rounded bg-panel px-1.5 py-0.5"
                style={{ color: "var(--analyst)" }}>{t("guide.rf.judge")}</span>
            </li>
          ))}
        </ul>
        <span className="mt-1.5 text-[10px]" style={{ color: "var(--bad)" }}>
          ↺ {t("guide.rf.reject")}
        </span>
        <span><FlowGate label={t("gate.task")} /></span>
      </div>
      <FlowArrow />
      <FlowNode who="strategist" icon="verify" title={t("guide.rf.final")}
        sub={`${t("role.strategist")} · ${t("guide.rf.final.sub")}`} />
      <FlowArrow />
      <FlowNode who="ok" icon="package" title={t("guide.rf.out")} sub={t("guide.rf.out.sub")} />
    </div>
  );
}
