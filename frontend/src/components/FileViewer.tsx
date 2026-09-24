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
import type { FileVersion } from "@/lib/types";
import { useErrorText, useLang } from "@/lib/i18n";
import { useMemo, useState } from "react";

import { api } from "@/lib/api";
import { highlightLine, langOf } from "@/lib/highlight";
import { useLoader } from "@/lib/useLoader";
import { Empty } from "./ui";
import { Icon } from "./icons";

/**
 * 이 파일이 여기까지 온 경위.
 *
 * 구매 기준에 **감사 가능성**이 올라와 있다(docs/market.md). 파일 하나를
 * 짚고 "누가, 몇 라운드에, 어떤 지적을 받고 고쳤나"를 따라갈 수 없으면
 * 그건 "AI 가 만들어줬다"이지 "무엇이 어떻게 만들어졌다"가 아니다.
 *
 * 옛 판본에는 이 정보가 없다. 그때는 **빈 자리로 둔다** — 없는 것을
 * 그럴듯하게 채우면 이력이 거짓말이 된다.
 */
function Trail({ versions }: { versions: FileVersion[] }) {
  const { t } = useLang();
  // 최신이 위. 이력을 볼 때 알고 싶은 것은 "마지막에 무슨 일이 있었나"다.
  const rows = [...versions].reverse();
  if (rows.length <= 1) {
    return <p className="text-[11px] text-dim">{t("file.noHistory")}</p>;
  }
  return (
    <ol className="space-y-1.5">
      {rows.map((v) => (
        <li key={v.version} className="flex gap-2 text-[11px]">
          <span
            className="mt-1 size-1.5 shrink-0 rounded-full"
            style={{
              background: v.current
                ? "var(--ok)"
                : `var(--${v.author}, var(--line-strong))`,
            }}
          />
          <span className="min-w-0 flex-1">
            <span className="text-muted">
              {v.current
                ? t("file.current")
                : `v${v.version}`}
              {v.author && (
                <>
                  {" · "}
                  <span style={{ color: `var(--${v.author}, var(--muted))` }}>
                    {t("file.byAuthor", { who: v.author })}
                  </span>
                </>
              )}
              {v.round ? ` · ${t("file.atRound", { n: v.round })}` : ""}
              {` · ${v.lines}`}
            </span>
            {v.reason && (
              <span className="mt-0.5 block text-dim">
                {t("file.becauseOf")}: {v.reason}
              </span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * 평평한 경로 목록을 폴더 트리로.
 *
 * `src/` `docs/` `design/` 를 매번 접두사 문자열로 반복해 보여주던 것을
 * 한 번만 적고 그 밑에 접는 구조로 바꾼다 — 파일이 늘어날수록 평평한
 * 목록은 같은 접두사가 몇 번이고 반복되는 벽이 된다.
 */
interface TreeNode {
  name: string;
  path: string;
  children: Map<string, TreeNode>;
}

function buildTree(files: string[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: new Map() };
  for (const f of files) {
    let node = root;
    const parts = f.split("/");
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let next = node.children.get(part);
      if (!next) {
        next = { name: part, path, children: new Map() };
        node.children.set(part, next);
      }
      node = next;
    });
  }
  return root;
}

function FileTree({
  node, depth, chosen, onPick, collapsed, onToggle,
}: {
  node: TreeNode; depth: number; chosen: string | null;
  onPick: (f: string) => void;
  collapsed: Set<string>; onToggle: (path: string) => void;
}) {
  const entries = [...node.children.values()].sort((a, b) => {
    const aDir = a.children.size > 0, bDir = b.children.size > 0;
    if (aDir !== bDir) return aDir ? -1 : 1;    // 폴더 먼저
    return a.name.localeCompare(b.name);
  });
  return (
    <>
      {entries.map((n) => {
        const isDir = n.children.size > 0;
        const isClosed = collapsed.has(n.path);
        if (isDir) {
          return (
            <div key={n.path}>
              <button
                type="button"
                onClick={() => onToggle(n.path)}
                className="flex w-full items-center gap-1 rounded-md px-1.5 py-1
                  text-left font-mono text-xs text-dim hover:bg-panel2"
                style={{ paddingLeft: `${depth * 0.75 + 0.375}rem` }}
              >
                <Icon
                  name="chevron"
                  size={11}
                  className={`shrink-0 transition-transform ${isClosed ? "" : "rotate-90"}`}
                />
                {n.name}/
              </button>
              {!isClosed && (
                <FileTree
                  node={n} depth={depth + 1} chosen={chosen} onPick={onPick}
                  collapsed={collapsed} onToggle={onToggle}
                />
              )}
            </div>
          );
        }
        return (
          <button
            key={n.path}
            type="button"
            onClick={() => onPick(n.path)}
            className={`block w-full truncate rounded-md py-1 text-left font-mono
              text-xs ${n.path === chosen ? "bg-panel2 text-fg" : "text-muted hover:bg-panel2"}`}
            style={{ paddingLeft: `${depth * 0.75 + 0.375}rem`, paddingRight: "0.5rem" }}
            title={n.path}
          >
            {n.name}
          </button>
        );
      })}
    </>
  );
}

/** 복사 · 다운로드. 클로드 아티팩트에도 있는 그 두 버튼이다. */
function FileActions({ path, content }: { path: string; content: string }) {
  const { t } = useLang();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 클립보드 권한이 없는 환경도 있다 — 버튼은 조용히 아무 일도 안 한다 */
    }
  };

  const download = () => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = path.split("/").pop() || path;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => void copy()}
        title={t("file.copy")}
        className="rounded-md p-1.5 text-dim hover:bg-panel2 hover:text-fg"
      >
        <Icon name={copied ? "check" : "copy"} size={14}
              style={copied ? { color: "var(--ok)" } : undefined} />
      </button>
      <button
        type="button"
        onClick={download}
        title={t("file.download")}
        className="rounded-md p-1.5 text-dim hover:bg-panel2 hover:text-fg"
      >
        <Icon name="download" size={14} />
      </button>
    </div>
  );
}

/** 줄번호 + 문법 강조. 회색 줄번호 칸은 선택되지 않아 복사할 때 안 딸려온다. */
function CodeLines({ text, lang }: { text: string; lang: string | null }) {
  const lines = text.split("\n");
  return (
    <code className="grid" style={{ gridTemplateColumns: "auto 1fr" }}>
      {lines.map((line, i) => (
        <span key={i} className="contents">
          <span className="select-none pr-3 text-right text-dim">{i + 1}</span>
          <span className="whitespace-pre-wrap break-all">
            {highlightLine(line, lang)}
          </span>
        </span>
      ))}
    </code>
  );
}

export function FileViewer({ slug, files }: { slug: string; files: string[] }) {
  const { t } = useLang();
  const errText = useErrorText();
  // 고른 파일이 없거나 목록에서 사라졌으면 첫 번째를 본다. 상태로 들고
  // 있다가 effect 로 맞추면, 목록이 바뀔 때마다 렌더가 한 번 더 돈다.
  const [chosen, setChosen] = useState<string | null>(null);
  const path = chosen && files.includes(chosen) ? chosen : (files[0] ?? null);
  const tree = useMemo(() => buildTree(files), [files]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggle = (p: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p); else next.add(p);
      return next;
    });

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
      setError(errText(e));
    }
  };

  if (files.length === 0) return <Empty>{t("file.none")}</Empty>;

  // 이전 회차만 비교 대상이다. version 0 은 현재 파일이다.
  const past = versions.filter((v) => v.version !== 0);

  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,13rem)_1fr]">
      <div className="max-h-[28rem] space-y-0.5 overflow-y-auto">
        <FileTree
          node={tree} depth={0} chosen={path} onPick={pick}
          collapsed={collapsed} onToggle={toggle}
        />
      </div>

      <div className="min-w-0">
        {error && <p className="mb-2 text-xs" style={{ color: "var(--bad)" }}>{error}</p>}

        {path && (
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="min-w-0 truncate font-mono text-xs text-dim" title={path}>
              {path}
            </span>
            <FileActions path={path} content={content} />
          </div>
        )}

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

        {versions.length > 1 && (
          <details className="mb-2 rounded-xl border border-line
            bg-[color:var(--panel-2)] px-3 py-2">
            <summary className="cursor-pointer text-[11px] text-muted">
              {t("file.history")}
            </summary>
            <div className="mt-2">
              <Trail versions={versions} />
            </div>
          </details>
        )}

        <pre className="max-h-[28rem] overflow-auto rounded-lg bg-panel2 p-3 font-mono text-xs leading-relaxed">
          {compare === null ? (
            <CodeLines text={content} lang={path ? langOf(path) : null} />
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
