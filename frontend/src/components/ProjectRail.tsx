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


import { type Key, useLang } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useLoader, useReloadOn } from "@/lib/useLoader";
import { useSticky } from "@/lib/sticky";
import { Icon } from "./icons";
import { Empty, MockBadge, Skeleton, StatusDot, clock, when } from "./ui";

const STORE_KEY = "ai-company.rail";

export function ProjectRail({
  activeSlug, onNew, refreshKey, phase,
}: {
  activeSlug?: string | null;
  onNew?: () => void;
  /** 지금 돌고 있는 실행의 단계. 사무실에만 있던 정보를 목록에도 둔다 —
   *  다른 프로젝트를 보는 동안에도 "어디까지 왔나"가 보여야 한다. */
  phase?: string | null;
  /** 실행이 끝나면 목록이 바뀐다. 이 값이 바뀌면 다시 읽는다. */
  refreshKey?: string | number;
}) {
  const { t, lang } = useLang();
  const [open, setOpen] = useSticky(STORE_KEY, true);
  const { data, error, loading, reload } = useLoader("rail", () =>
    api.projects({ limit: 40, sort: "recent" }),
  );

  // 마운트 때는 `useLoader` 가 이미 읽었다. 여기서 또 읽으면 목록을
  // 두 번 가져온다 — 프로덕션 빌드로 확인한 실제 중복이었다.
  useReloadOn(refreshKey, reload);

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

  // 같은 날짜가 줄마다 반복되고 있었다 — 다섯 줄이 전부 "09. 22. 오전
  // 08:23" 이면 그 줄은 아무것도 구분해주지 않으면서 자리만 먹는다.
  // 날짜는 묶음 제목이 한 번 말하고, 줄에는 시:분과 파일 수만 남긴다.
  const groups: { key: string; label: string; items: typeof rows }[] = [];
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  const today = midnight.getTime() / 1000;
  const bucket = (p: (typeof rows)[number]) =>
    p.status === "running" ? "running"
      : p.created_at >= today ? "today"
        : p.created_at >= today - 86400 ? "yesterday"
          : "earlier";
  for (const p of rows) {
    const key = bucket(p);
    const last = groups[groups.length - 1];
    if (last?.key === key) last.items.push(p);
    else groups.push({ key, label: t(`rail.${key}` as Key), items: [p] });
  }

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
        {/* 세 가지 상태를 다 그린다. 불러오는 중을 안 그리면 느린 연결에서
            빈 목록이 보이고, 그건 "내 프로젝트가 사라졌다"로 읽힌다. */}
        {loading && rows.length === 0 && (
          <div className="px-1 py-2">
            <Skeleton lines={5} />
          </div>
        )}
        {error && !loading && (
          <p className="px-2 py-3 text-[11px]" style={{ color: "var(--bad)" }}>
            {error}
          </p>
        )}
        {!loading && !error && rows.length === 0 && (
          <Empty>{t("office.empty")}</Empty>
        )}
        {groups.map((g) => (
        <ul key={g.key} className="space-y-0.5">
          {/* 제목은 스크롤해도 붙어 있다. 긴 목록에서 지금 보고 있는 줄이
              어느 날의 것인지 잃지 않게 한다. */}
          <li className="sticky top-0 z-10 bg-[color:var(--panel)]/85 px-2.5
            pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider
            text-dim backdrop-blur-sm">
            {g.label}
            <span className="ml-1 tabular-nums opacity-70">{g.items.length}</span>
          </li>
          {g.items.map((p) => {
            const on = p.slug === activeSlug;
            // 이름이 요구사항에서 만들어진 경우에는 같은 말을 두 번 쓰지
            // 않는다. 줄이 늘어나기만 하고 알려주는 것은 없다.
            const name = p.name || p.slug;
            const req = (p.requirement ?? "").trim();
            const same = !req || name.replace(/-/g, " ") === req;
            return (
              <li key={p.slug}>
                <Link
                  href={`/projects/${encodeURIComponent(p.slug)}`}
                  // 이름을 안 주면 스크린리더가 안의 글을 전부 이어 붙여
                  // "mock-projectMOCK09. 22. 오전 08:23 · 4" 로 읽는다.
                  aria-label={`${p.name || p.slug} · ${p.status}${
                    p.mock ? " · Mock" : ""
                  }`}
                  aria-current={on ? "page" : undefined}
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
                  {/* 이름만으로는 구분이 안 된다 — 자동으로 붙는 이름은
                      "mock-project" 처럼 겹치고, 다섯 줄이 같은 글자가
                      된다. 무엇을 시켰는지가 그 줄의 진짜 이름이다. */}
                  {!same && (
                    <span className="mt-0.5 block truncate text-[11px]
                      text-muted" aria-hidden>
                      {req}
                    </span>
                  )}
                  {/* 돌고 있는 줄에는 단계를 적는다. 시각·파일 수는 끝난
                      것에나 의미가 있고, 지금 돌는 것에 필요한 것은
                      "어디까지 왔나"다. */}
                  {p.status === "running" && phase ? (
                    <span className="mt-0.5 flex items-center gap-1
                      text-[11px] font-medium" style={{ color: "var(--accent)" }}>
                      <span className="size-1 animate-pulse rounded-full"
                            style={{ background: "var(--accent)" }} aria-hidden />
                      {phase}
                    </span>
                  ) : (
                  <span className="mt-0.5 block truncate text-[11px] text-dim"
                        aria-hidden>
                    {g.key === "earlier"
                      ? when(p.created_at, lang)
                      : clock(p.created_at, lang)}
                    {typeof p.file_count === "number"
                      && ` · ${p.file_count === 1
                        ? t("rail.file1")
                        : t("rail.files", { n: p.file_count })}`}
                    {!p.mock && typeof p.credits === "number" && p.credits > 0
                      && ` · ${t("rail.credits", { n: p.credits })}`}
                  </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
        ))}
      </div>
    </aside>
  );
}
