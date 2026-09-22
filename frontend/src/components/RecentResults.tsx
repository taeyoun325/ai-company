"use client";

/**
 * 로그 칸이 비어 있을 때 채우는 "지난 결과" (DAY 22).
 *
 * ## 왜 만들었나
 *
 * 넓은 화면에서 오른쪽 레일은 작업 로그다. 그런데 실행 전에는 그 칸이
 * **700px 짜리 빈 공간**이고, 가운데에 "일이 시작되면 여기로 흐릅니다"
 * 한 줄만 있었다. 제품을 처음 열었을 때 화면의 3분의 1이 안내문 하나다.
 *
 * ## 왼쪽 레일과 무엇이 다른가
 *
 * 왼쪽은 **무엇을 시켰나**(이름·요구사항)를 보여주고, 여기는 **어떻게
 * 끝났나**(완성도·원가)를 보여준다. 같은 목록을 두 번 그리지 않기 위해
 * 끝난 것만, 그리고 셋만 보여준다.
 *
 * 실행이 시작되면 이 컴포넌트는 언마운트되므로, 일하는 동안은 요청도
 * 렌더도 없다.
 */
import Link from "next/link";

import { api } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { useLoader } from "@/lib/useLoader";
import { clock, money, took, when } from "./ui";

export function RecentResults() {
  const { t, lang } = useLang();
  const { data, loading } = useLoader("recent", () =>
    api.projects({ limit: 8, sort: "recent" }),
  );

  // 끝난 것만. 진행 중·중단은 왼쪽 레일이 이미 맨 위에 올려준다.
  const rows = (data?.projects ?? [])
    .filter((p) => p.status === "done" || p.status === "manual")
    .slice(0, 3);

  if (loading || rows.length === 0) return null;

  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  const today = midnight.getTime() / 1000;

  return (
    <section className="border-t border-line px-3 py-3">
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-dim">
        {t("recent.title")}
      </h2>
      <ul className="mt-2 space-y-1">
        {rows.map((p) => (
          <li key={p.slug}>
            <Link
              href={`/projects/${encodeURIComponent(p.slug)}`}
              aria-label={`${p.name || p.slug} · ${t("recent.score")} ${p.score}%`}
              className="block rounded-lg px-2 py-1.5 transition hover:bg-panel2"
            >
              <span className="flex items-baseline gap-2">
                <span className="min-w-0 flex-1 truncate text-[12px]">
                  {(p.requirement ?? "").trim() || p.name || p.slug}
                </span>
                {/* 완성도는 이 제품의 점수판이다. 숫자를 먼저 읽게 둔다. */}
                <span className="shrink-0 text-[12px] font-semibold tabular-nums"
                      style={{ color: p.score >= 100 ? "var(--ok)" : undefined }}>
                  {p.score}%
                </span>
              </span>
              <span className="mt-0.5 block truncate text-[10px] text-dim">
                {p.created_at >= today
                  ? clock(p.created_at, lang)
                  : when(p.created_at, lang)}
                {p.mock ? " · Mock" : ` · ${money(p.cost)}`}
                {/* 얼마나 걸렸는지는 상세 화면에만 있었다. 지난 결과를
                    훑는 이유 중 하나가 "이런 일은 보통 얼마나 걸리나"다. */}
                {took(p.created_at, p.updated_at)
                  && ` · ${took(p.created_at, p.updated_at)}`}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
