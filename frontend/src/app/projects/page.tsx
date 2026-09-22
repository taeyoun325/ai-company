"use client";

/**
 * 프로젝트 목록 (지시서 §12).
 *
 * ## Mock 으로 만든 것을 목록에서 구분한다
 *
 * 저장소에 남은 산출물은 나중에 다시 열린다. 그때 Mock 으로 만든 것과
 * 실제 모델이 만든 것이 같아 보이면, 대본을 결과물로 착각한 채 납품한다.
 * 요약 카드에서도 Mock 건수를 따로 센다 — 섞어서 세면 "우리는 N개를
 * 만들었다"가 거짓말이 된다.
 *
 * ## 색인이 깨졌으면 그렇다고 말한다
 *
 * 백엔드는 색인이 깨지면 디스크에서 읽어 `source: "disk"` 로 알려준다.
 * 감추면 왜 느린지 아무도 모르고, 아무도 고치지 않는다.
 */
import { useEffect, useState } from "react";
import Link from "next/link";

import {
  Button, Empty, ErrorBox, MockBadge, money, Panel, Screen, StatusDot, Warning, when,
} from "@/components/ui";
import { api } from "@/lib/api";
import { type Key, useErrorText, useLang } from "@/lib/i18n";
import { useLoader } from "@/lib/useLoader";

/** 상태 → 번역 키. 값이 아니라 **키**를 둔다 — 값을 두면 언어를 바꿔도
 *  이 표만 한국어로 남는다. */
const LABEL: Record<string, Key> = {
  running: "list.running",
  done: "list.done",
  stopped: "list.stopped",
  manual: "list.manual",
};

const PAGE = 20;

export default function ProjectsPage() {
  const { t, lang } = useLang();
  const errText = useErrorText();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("created");
  const [offset, setOffset] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);

  const key = `${q}|${status}|${sort}|${offset}`;
  const { data, error, loading, reload } = useLoader(key, () =>
    api.projects({ q, status, sort, limit: PAGE, offset }),
  );
  const stats = useLoader("project-stats", () => api.projectStats());

  const projects = data?.projects ?? [];
  const total = data?.total ?? 0;

  // 진행 중인 실행이 있으면 목록의 상태가 바뀐다. 스트림을 붙이지 않고
  // 느리게 갱신한다 — 목록은 실시간일 필요가 없다.
  useEffect(() => {
    const t = setInterval(() => {
      void reload();
      void stats.reload();
    }, 5000);
    return () => clearInterval(t);
  }, [reload, stats]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setFailure(null);
      await reload();
      await stats.reload();
    } catch (e) {
      setFailure(errText(e));
    }
  };

  const remove = (slug: string) => {
    if (!window.confirm(t("list.confirmDelete", { slug }))) return;
    void act(() => api.deleteProject(slug));
  };

  return (
    <Screen>
    <div className="space-y-4">
      {(error || failure) && <ErrorBox>{failure ?? error}</ErrorBox>}

      {data?.source === "disk" && (
        <Warning>
          {t("list.fromDisk")}{" "}
          <button
            type="button"
            className="underline"
            onClick={() => void act(() => api.reindex())}
          >
            {t("list.rebuild")}
          </button>
        </Warning>
      )}

      {stats.data && (
        <Panel title={t("list.summary")}>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <Stat k={t("list.projects")} v={String(stats.data.projects)} />
            <Stat k={t("list.done")} v={String(stats.data.done)} />
            <Stat k={t("list.stopped")} v={String(stats.data.stopped)} />
            <Stat k={t("list.totalCost")} v={money(stats.data.cost)} />
            <Stat
              k={t("list.mockOutput")}
              v={String(stats.data.mock)}
              tone={stats.data.mock > 0 ? "mock" : undefined}
            />
          </dl>
        </Panel>
      )}

      <Panel
        title={t("list.projects")}
        right={
          <span className="text-xs text-dim">
            {t("list.countOf", { total, shown: projects.length })}
          </span>
        }
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
            placeholder={t("list.search")}
            className="min-w-0 flex-1 rounded-lg border border-line bg-panel2 px-3 py-1.5
              text-sm outline-none placeholder:text-dim focus:border-accent"
          />
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
            className="rounded-lg border border-line bg-panel2 px-2 py-1.5 text-sm"
          >
            <option value="">{t("list.allStatus")}</option>
            {Object.entries(LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="rounded-lg border border-line bg-panel2 px-2 py-1.5 text-sm"
          >
            <option value="created">{t("list.sortCreated")}</option>
            <option value="updated">{t("list.sortUpdated")}</option>
            <option value="cost">{t("list.sortCost")}</option>
            <option value="score">{t("list.sortScore")}</option>
          </select>
        </div>

        {loading && projects.length === 0 ? (
          <Empty>{t("proj.loading")}</Empty>
        ) : projects.length === 0 ? (
          <Empty>
            {q || status
              ? t("list.noMatch")
              : t("list.none")}
          </Empty>
        ) : (
          <ul className="divide-y divide-line">
            {projects.map((p) => (
              <li key={p.slug} className="flex items-center gap-3 py-2.5">
                <StatusDot status={p.status} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Link
                      href={
                        p.mode === "manual" ? `/manual/${p.slug}` : `/projects/${p.slug}`
                      }
                      className="truncate text-sm font-medium hover:underline"
                    >
                      {p.name || p.slug}
                    </Link>
                    {p.mock && <MockBadge title={t("mock.badge")} />}
                    <span className="text-[11px] text-dim">
                      {LABEL[p.status] ? t(LABEL[p.status]) : p.status}
                    </span>
                  </div>
                  <p className="truncate text-xs text-dim" title={p.requirement}>
                    {p.requirement}
                  </p>
                </div>
                <div className="hidden shrink-0 text-right sm:block">
                  <p className="text-sm font-semibold tabular-nums">
                    {p.status === "done" ? `${p.score}%` : "—"}
                  </p>
                  <p className="text-[11px] text-dim">{money(p.cost)}</p>
                </div>
                <span className="hidden w-28 shrink-0 text-right text-[11px] text-dim md:block">
                  {when(p.created_at, lang)}
                </span>
                <Button
                  tone="ghost"
                  onClick={() => remove(p.slug)}
                  title={t("list.delete")}
                  disabled={p.status === "running"}
                >
                  ✕
                </Button>
              </li>
            ))}
          </ul>
        )}

        {total > PAGE && (
          <div className="mt-3 flex items-center justify-between text-xs">
            <Button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              {t("list.prev")}
            </Button>
            <span className="text-dim">
              {offset + 1}–{Math.min(offset + PAGE, total)} / {total}
            </span>
            <Button
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              {t("list.next")}
            </Button>
          </div>
        )}
      </Panel>
    </div>
    </Screen>
  );
}

function Stat({ k, v, tone }: { k: string; v: string; tone?: "mock" }) {
  return (
    <div className="rounded-lg bg-panel2 px-3 py-2">
      <dt className="text-[11px] text-dim">{k}</dt>
      <dd
        className="text-lg font-semibold tabular-nums"
        style={tone === "mock" ? { color: "var(--mock)" } : undefined}
      >
        {v}
      </dd>
    </div>
  );
}
