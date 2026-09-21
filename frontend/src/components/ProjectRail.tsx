"use client";

/**
 * 왼쪽 프로젝트 레일 (DAY 22).
 *
 * ## 왜 탭이 아니라 레일인가
 *
 * 프로젝트 목록은 **일하는 동안 옆에 있어야 하는 것**이지 따로 가서 보는
 * 화면이 아니다. 탭으로 두면 "지금 돌고 있는 저 프로젝트"를 보려고
 * 작업 화면을 떠나야 하고, 돌아오면 어디까지 봤는지 잃는다.
 *
 * ## 돌고 있는 것이 맨 위다
 *
 * 목록을 최신순으로만 두면, 지금 돌고 있는 실행이 어제 만든 것들 사이에
 * 묻힌다. 상태가 `running` 인 것을 먼저 올린다.
 *
 * ## Mock 을 목록에서도 표시한다
 *
 * 산출물 목록에서 진짜와 대본을 구분하지 못하면, 나중에 그 파일을 열어
 * 쓸 때 어느 쪽이었는지 알 방법이 없다.
 */
import Link from "next/link";
import { useEffect } from "react";

import { useLang } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";
import { useSticky } from "@/lib/sticky";
import { Icon } from "./icons";
import { Empty, MockBadge, StatusDot, when } from "./ui";

const STORE_KEY = "ai-company.rail";

export function ProjectRail({
  activeSlug, onNew, refreshKey,
}: {
  activeSlug?: string | null;
  onNew?: () => void;
  /** 실행이 끝나면 목록이 바뀐다. 이 값이 바뀌면 다시 읽는다. */
  refreshKey?: string | number;
}) {
  const { t } = useLang();
  const [open, setOpen] = useSticky(STORE_KEY, true);
  const { data, reload } = useLoader("rail", () =>
    api.projects({ limit: 40, sort: "recent" }),
  );

  useEffect(() => {
    void reload();
  }, [refreshKey, reload]);

  // 접어둔 상태는 기억한다(lib/sticky.ts). 좁은 화면에서 매번 접는 것은
  // 일이고, 기억이 실패해도 화면은 그대로 돈다.
  const toggle = () => setOpen(!open);

  if (!open) {
    // 접었을 때도 **여는 길이 보여야 한다.** 완전히 숨기면 사용자는
    // 프로젝트 목록이 사라졌다고 생각한다.
    return (
      <aside className="flex h-full w-11 shrink-0 flex-col items-center gap-2
        border-r border-line bg-[color:var(--panel)] py-3 backdrop-blur-xl">
        <button
          type="button"
          onClick={toggle}
          title={t("office.projects")}
          className="grid size-7 place-items-center rounded-lg text-muted
            transition hover:bg-panel2 hover:text-fg"
        >
          <Icon name="panel" size={16} />
        </button>
        {onNew && (
          <button
            type="button"
            onClick={onNew}
            title={t("office.newProject")}
            className="grid size-7 place-items-center rounded-lg text-muted
              transition hover:bg-panel2 hover:text-fg"
          >
            <Icon name="plus" size={16} />
          </button>
        )}
        <span className="mt-1 text-[10px] tabular-nums text-dim">
          {data?.projects.length ?? 0}
        </span>
      </aside>
    );
  }

  const rows = [...(data?.projects ?? [])].sort((a, b) => {
    const run = (p: typeof a) => (p.status === "running" ? 0 : 1);
    return run(a) - run(b) || b.created_at - a.created_at;
  });

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-line
      bg-[color:var(--panel)] backdrop-blur-xl">
      <div className="flex items-center gap-1 px-3 py-3">
        <button
          type="button"
          onClick={toggle}
          title={t("office.collapse")}
          className="grid size-7 place-items-center rounded-lg text-muted
            transition hover:bg-panel2 hover:text-fg"
        >
          <Icon name="panel" size={16} />
        </button>
        <span className="flex-1 text-[13px] font-semibold tracking-tight">
          {t("office.projects")}
        </span>
        {onNew && (
          <button
            type="button"
            onClick={onNew}
            title={t("office.newProject")}
            className="grid size-7 place-items-center rounded-lg text-muted
              transition hover:bg-panel2 hover:text-fg"
          >
            <Icon name="plus" size={16} />
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {rows.length === 0 && <Empty>{t("office.empty")}</Empty>}
        <ul className="space-y-0.5">
          {rows.map((p) => {
            const on = p.slug === activeSlug;
            return (
              <li key={p.slug}>
                <Link
                  href={`/projects/${encodeURIComponent(p.slug)}`}
                  className={`block rounded-xl px-2.5 py-2 transition ${
                    on ? "bg-panel2" : "hover:bg-panel2"
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <StatusDot status={p.status} />
                    <span className="min-w-0 flex-1 truncate text-[13px]">
                      {p.name || p.slug}
                    </span>
                    {p.mock && <MockBadge title={t("mock.badge")} />}
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-dim">
                    {when(p.created_at)}
                    {typeof p.file_count === "number" && ` · ${p.file_count}`}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
