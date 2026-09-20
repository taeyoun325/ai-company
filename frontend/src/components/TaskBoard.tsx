"use client";

/**
 * 태스크 보드 · 완성도 · 비용 (지시서 §9 · §14).
 *
 * ## 완성도 옆에 근거를 붙이는 이유
 *
 * "87%"만 보여주면 그 숫자가 무엇을 센 것인지 알 수 없고, 사용자는
 * 그것을 품질로 읽는다. 태스크 몇 개, 테스트 몇 개, 인수기준 몇 개인지
 * 같이 보여준다. 최종 점수는 인수기준 충족률이고, 중간 점수는 진행률이다 —
 * 그 차이도 표시한다.
 *
 * ## 비용을 크게 보여주는 이유
 *
 * 상한이 있어도 사용자는 자기가 얼마를 쓰고 있는지 알아야 한다. 상한은
 * 사고를 막는 장치이지, 사용자에게 알려주는 장치가 아니다.
 */
import type { BusEvent, TaskRow } from "@/lib/types";
import { Empty, money } from "./ui";

export function TaskBoard({ tasks }: { tasks?: TaskRow[] }) {
  if (!tasks || tasks.length === 0) {
    return <Empty>아직 계획이 없습니다.</Empty>;
  }
  return (
    <ol className="space-y-1.5">
      {tasks.map((t) => (
        <li
          key={t.id}
          className="flex items-center gap-2 rounded-lg bg-panel2 px-2.5 py-1.5 text-sm"
        >
          <Mark status={t.status} />
          <span
            className={`min-w-0 flex-1 truncate ${
              t.status === "done" ? "text-muted line-through" : ""
            }`}
            title={t.title}
          >
            {t.title}
          </span>
          <span
            className="shrink-0 text-[11px]"
            style={{ color: `var(--${t.assignee}, var(--dim))` }}
          >
            {t.assignee}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Mark({ status }: { status: TaskRow["status"] }) {
  if (status === "done")
    return (
      <span aria-label="완료" style={{ color: "var(--ok)" }}>
        ✓
      </span>
    );
  if (status === "doing")
    return (
      <span aria-label="진행 중" className="working" style={{ ["--c" as string]: "var(--accent)", color: "var(--accent)" }}>
        ●
      </span>
    );
  return (
    <span aria-label="대기" className="text-dim">
      ○
    </span>
  );
}

export function ScorePanel({
  score,
  detail,
  cost,
  round,
}: {
  score: number | null;
  detail?: BusEvent["score_detail"];
  cost?: number;
  round?: number;
}) {
  const final = detail?.final === true;
  return (
    <div className="space-y-3">
      <div className="flex items-end gap-3">
        <div>
          <p className="text-3xl font-bold tabular-nums">
            {score === null ? "—" : `${score}%`}
          </p>
          <p className="text-[11px] text-dim">
            {final ? "인수기준 충족률 (최종)" : "진행률 (중간 집계)"}
          </p>
        </div>
        <div className="ml-auto text-right">
          <p className="text-xl font-semibold tabular-nums">{money(cost)}</p>
          <p className="text-[11px] text-dim">
            이번 프로젝트 비용{round ? ` · ${round}라운드` : ""}
          </p>
        </div>
      </div>

      {detail && (
        <dl className="grid grid-cols-2 gap-1.5 text-[11px]">
          <Item k="태스크" v={String(detail.tasks ?? "—")} />
          <Item k="테스트" v={String(detail.tests ?? "—")} />
          <Item k="기준 커버리지" v={String(detail.ac_coverage ?? "—")} />
          <Item k="인수기준" v={String(detail.criteria ?? "—")} />
          <Item k="반려" v={String(detail.reworks ?? 0)} />
          <Item k="재기획" v={String(detail.replans ?? 0)} />
        </dl>
      )}
    </div>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between rounded-md bg-panel2 px-2 py-1">
      <dt className="text-dim">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}
