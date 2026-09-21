"use client";

/**
 * 산출물 뷰어와 회차별 diff (지시서 §12).
 *
 * ## 왜 이력을 보여주나
 *
 * 직원이 파일을 덮어쓰기 직전 내용이 저장돼 있다. 반려 → 재작업으로
 * 무엇이 바뀌었는지 CEO 가 직접 볼 수 없으면, "고쳤습니다"라는 말을
 * 믿는 수밖에 없다. 그건 검증이 아니다.
 */
import { useLang } from "@/lib/i18n";
import { useState } from "react";

import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";
import { Empty } from "./ui";

export function FileViewer({ slug, files }: { slug: string; files: string[] }) {
  const { t } = useLang();
  // 고른 파일이 없거나 목록에서 사라졌으면 첫 번째를 본다. 상태로 들고
  // 있다가 effect 로 맞추면, 목록이 바뀔 때마다 렌더가 한 번 더 돈다.
  const [chosen, setChosen] = useState<string | null>(null);
  const path = chosen && files.includes(chosen) ? chosen : (files[0] ?? null);

  const [compare, setCompare] = useState<number | null>(null);
  const [diff, setDiff] = useState<{ kind: string; text: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: file } = useLoader(`${slug}:${path ?? ""}`, () =>
    path ? api.projectFile(slug, path) : Promise.resolve(null),
  );
  const content = file?.content ?? "";
  const versions = file?.versions ?? [];

  const pick = (f: string) => {
    setChosen(f);
    // 다른 파일을 열면 이전 파일의 diff 는 의미가 없다. 남겨두면
    // 지금 보는 파일의 차이로 오해한다.
    setCompare(null);
    setDiff([]);
  };

  const showDiff = async (v: number) => {
    if (!path) return;
    try {
      const b = await api.projectDiff(slug, path, v, 0);
      setDiff(b.diff);
      setCompare(v);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (files.length === 0) return <Empty>{t("file.none")}</Empty>;

  // 이전 회차만 비교 대상이다. version 0 은 현재 파일이다.
  const past = versions.filter((v) => v.version !== 0);

  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,13rem)_1fr]">
      <ul className="max-h-[28rem] space-y-0.5 overflow-y-auto">
        {files.map((f) => (
          <li key={f}>
            <button
              type="button"
              onClick={() => pick(f)}
              className={`w-full truncate rounded-md px-2 py-1 text-left font-mono text-xs
                ${f === path ? "bg-panel2 text-fg" : "text-muted hover:bg-panel2"}`}
              title={f}
            >
              {f}
            </button>
          </li>
        ))}
      </ul>

      <div className="min-w-0">
        {error && <p className="mb-2 text-xs" style={{ color: "var(--bad)" }}>{error}</p>}

        {past.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="text-dim">{t("file.compare")}</span>
            {past.map((v) => (
              <button
                key={v.version}
                type="button"
                onClick={() => void showDiff(v.version)}
                className={`rounded-md border px-1.5 py-0.5 ${
                  compare === v.version
                    ? "border-accent text-accent"
                    : "border-line text-muted hover:text-fg"
                }`}
                title={v.note}
              >
                {t("file.toCurrent", { n: v.version })}
              </button>
            ))}
            {compare !== null && (
              <button
                type="button"
                onClick={() => {
                  setCompare(null);
                  setDiff([]);
                }}
                className="text-dim underline"
              >
                {t("file.raw")}
              </button>
            )}
          </div>
        )}

        <pre className="max-h-[28rem] overflow-auto rounded-lg bg-panel2 p-3 font-mono text-xs leading-relaxed">
          {compare === null ? (
            <code>{content}</code>
          ) : diff.length === 0 ? (
            <code className="text-dim">{t("file.noDiff")}</code>
          ) : (
            diff.map((d, i) => (
              <div
                key={i}
                style={{
                  color:
                    d.kind === "add"
                      ? "var(--ok)"
                      : d.kind === "del"
                        ? "var(--bad)"
                        : d.kind === "hunk"
                          ? "var(--accent)"
                          : "var(--muted)",
                }}
              >
                {d.text}
              </div>
            ))
          )}
        </pre>
      </div>
    </div>
  );
}
