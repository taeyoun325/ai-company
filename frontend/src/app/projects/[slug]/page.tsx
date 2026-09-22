"use client";

/**
 * 프로젝트 상세 (지시서 §12).
 *
 * 저장된 결과와 실시간 로그를 같은 화면에서 본다. 진행 중이면 로그가
 * 흐르고, 끝났으면 저장된 이력이 그대로 보인다 — 두 경우에 다른 화면을
 * 만들면 "끝나자마자 화면이 빈다" 같은 일이 생긴다.
 */
import { use, useEffect, type ReactNode } from "react";

import { ChatLog } from "@/components/ChatLog";
import { ProjectRail } from "@/components/ProjectRail";
import { FileViewer } from "@/components/FileViewer";
import { ScorePanel, TaskBoard } from "@/components/TaskBoard";
import {
  Button, Empty, ErrorBox, MockBadge, money, Panel, took, Warning, when,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import type { Project } from "@/lib/types";
import { useLoader } from "@/lib/useLoader";
import { useSlug } from "@/lib/useSlug";
import { foldState, useStream } from "@/lib/useStream";

export default function ProjectPage({ params }: { params: Promise<{ slug: string }> }) {
  const { t, lang } = useLang();
  const slug = useSlug(use(params));
  const { data: project, error, reload } = useLoader<Project>(slug, () =>
    api.run(slug),
  );
  const stream = useStream(slug);
  const folded = foldState(stream.events);

  // 로그가 움직일 때만 다시 읽는다. 끝난 프로젝트에는 아무 요청도 안 간다.
  useEffect(() => {
    if (project?.running) void reload();
  }, [folded.phase, folded.done, project?.running, reload]);

  if (error) {
    return (
      <Shell slug={slug}>
        <ErrorBox>{error}</ErrorBox>
      </Shell>
    );
  }
  if (!project) {
    return (
      <Shell slug={slug}>
        <Empty>{t("proj.loading")}</Empty>
      </Shell>
    );
  }

  // 진행 중이면 흐르는 값이, 끝났으면 저장된 값이 진실이다.
  const score = project.running ? folded.score : project.score;
  const detail = project.running ? folded.scoreDetail : project.score_detail;
  const tasks = project.running ? (folded.tasks ?? project.tasks) : project.tasks;
  const files = project.running && folded.files.length ? folded.files : (project.files ?? []);

  return (
    <Shell slug={slug}>
      {project.mock && (
        <Warning>
          <strong>{t("proj.mockWarn")}</strong> {t("proj.mockWarnBody")}
        </Warning>
      )}

      <Panel
        title={
          <span className="flex items-center gap-2">
            {project.name || project.slug}
            {project.mock && <MockBadge title={t("mock.badge")} />}
          </span>
        }
        right={
          <span className="flex items-center gap-2 text-xs text-dim">
            {when(project.created_at, lang)}
            {/* "끝났나 · 얼마나 됐나 · 얼마 들었나" 다음으로 묻는 것이
                **얼마나 걸렸나**다. 두 시각의 차이로 이미 알 수 있었다. */}
            {!project.running && took(project.created_at, project.updated_at) && (
              <span className="tabular-nums">
                · {took(project.created_at, project.updated_at)}
              </span>
            )}
            {project.running && (
              <Button tone="danger" onClick={() => void api.cancelRun(slug).then(reload)}>
                {t("proj.stop")}
              </Button>
            )}
          </span>
        }
      >
        <p className="text-sm text-muted">{project.requirement}</p>

        {/* 끝났나 · 얼마나 됐나 · 얼마 들었나. 제일 먼저 묻는 셋이다. */}
        <div className="mt-3">
          <FactBar
            project={project}
            score={score ?? null}
            cost={project.running ? folded.totals?.cost : project.cost}
          />
        </div>
        {project.stopped_reason && (
          <p className="mt-2 text-sm" style={{ color: "var(--bad)" }}>
            {t("proj.stopped")}: {project.stopped_reason}
          </p>
        )}
        {project.report && (
          <div className="mt-3 space-y-1 rounded-lg bg-panel2 p-3 text-sm">
            <p>{project.report.summary}</p>
            {project.report.unmet_criteria.length > 0 && (
              <p style={{ color: "var(--warn)" }}>
                {t("proj.unmet")}: {project.report.unmet_criteria.join(", ")}
              </p>
            )}
          </div>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <Panel title={t("proj.files")}>
            <FileViewer slug={slug} files={files} />
          </Panel>
          <Panel title={t("office.log")} className="flex max-h-[30rem] flex-col overflow-hidden">
            <div className="-m-4 flex min-h-0 flex-1 flex-col">
              <ChatLog
                events={stream.events}
                roster={stream.roster}
                connected={stream.connected}
                polling={stream.polling}
                past={!project.running}
                className="h-[24rem]"
              />
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title={t("proj.score")}>
            <ScorePanel
              score={score ?? null}
              detail={detail}
              cost={project.running ? folded.totals?.cost : project.cost}
              round={folded.round}
            />
          </Panel>
          <Panel title={t("proj.tasks")}>
            <TaskBoard tasks={tasks} />
          </Panel>
          {project.criteria && project.criteria.length > 0 && (
            <Panel title={t("proj.criteria")}>
              <ul className="space-y-1 text-xs">
                {project.criteria.map((c) => {
                  const met = project.report?.met_criteria.includes(c.id);
                  const unmet = project.report?.unmet_criteria.includes(c.id);
                  return (
                    <li key={c.id} className="flex gap-1.5">
                      <span
                        style={{
                          color: met ? "var(--ok)" : unmet ? "var(--bad)" : "var(--dim)",
                        }}
                      >
                        {met ? "✓" : unmet ? "✕" : "·"}
                      </span>
                      <span className="text-muted">{c.text}</span>
                    </li>
                  );
                })}
              </ul>
            </Panel>
          )}
          <Panel title={t("proj.usage")}>
            <ul className="space-y-1 text-xs">
              {Object.entries(project.usage ?? {})
                .filter(([, u]) => u.calls > 0)
                .map(([id, u]) => (
                  <li key={id} className="flex justify-between gap-2">
                    {/* id 를 그대로 보여주고 있었다("developer"). 사람이 읽는
                        이름은 로스터에 있고, 고객이 이름을 바꿔뒀을 수도
                        있다 — 그 이름으로 불러야 같은 사람으로 읽힌다. */}
                    <span className="min-w-0 truncate"
                          style={{ color: `var(--${id}, var(--muted))` }}>
                      {stream.roster[id]?.name ?? id}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted">
                      {u.calls === 1 ? t("proj.calls1") : t("proj.calls", { n: u.calls })} · {money(u.cost)}
                    </span>
                  </li>
                ))}
            </ul>
          </Panel>
        </div>
      </div>
    </Shell>
  );
}

/**
 * 프로젝트 한 줄 요약.
 *
 * 상세 화면에 와서 제일 먼저 묻는 것은 "**끝났나 · 얼마나 됐나 · 얼마
 * 들었나**" 셋이다. 그 셋이 패널 세 개에 흩어져 있으면 눈이 세 번
 * 움직인다. 머리에 붙여 한 줄로 만든다.
 *
 * Mock 은 색을 따로 쓴다 — 이 숫자들이 진짜 작업의 것이 아니라는 사실이
 * 숫자와 같은 자리에 있어야 한다.
 */
function FactBar({ project, score, cost }: {
  project: Project; score: number | null; cost?: number;
}) {
  const { t } = useLang();
  const tone = project.status === "done"
    ? "var(--ok)"
    : project.status === "stopped"
      ? "var(--bad)"
      : project.status === "running"
        ? "var(--accent)"
        : "var(--dim)";
  const label: Record<string, string> = {
    done: t("list.done"),
    stopped: t("list.stopped"),
    running: t("list.running"),
    manual: t("list.manual"),
  };
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Fact k={t("proj.state")}
            v={label[project.status] ?? project.status} tone={tone} />
      <Fact k={t("proj.completeness")} v={score === null ? "—" : `${score}%`} />
      <Fact k={t("office.cost")}
            v={money(cost)}
            tone={project.mock ? "var(--mock)" : undefined} />
      <Fact k={t("proj.fileCount")}
            v={String(project.file_count ?? project.files?.length ?? 0)} />
    </dl>
  );
}

function Fact({ k, v, tone }: { k: string; v: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-[color:var(--panel-2)] px-3 py-2">
      <dt className="text-[11px] text-dim">{k}</dt>
      <dd className="mt-0.5 text-sm font-semibold tabular-nums"
          style={tone ? { color: tone } : undefined}>
        {v}
      </dd>
    </div>
  );
}

/**
 * 상세 화면의 틀.
 *
 * 사무실과 **같은 레일**을 왼쪽에 둔다. 프로젝트를 열었다고 목록이
 * 사라지면, 다음 프로젝트로 건너가려고 매번 뒤로 가야 한다.
 */
function Shell({ slug, children }: { slug: string; children: ReactNode }) {
  return (
    <div className="flex h-full">
      <ProjectRail activeSlug={slug} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl space-y-4 px-4 py-4">{children}</div>
      </div>
    </div>
  );
}
