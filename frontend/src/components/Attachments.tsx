"use client";

/**
 * 작업 지시에 사진 · 영상 · 파일을 붙인다 (DAY 28).
 *
 * 붙이는 길은 셋이다 — 클립 버튼, 끌어다 놓기, 붙여넣기(캡처한 화면을 바로).
 * 고르는 즉시 올린다. 시작 버튼을 누를 때 올리기 시작하면 영상 하나에 몇 초씩
 * 멈춰 있게 되고, 그동안 무엇이 잘못됐는지(형식 · 크기)도 늦게 안다.
 *
 * ## 받는 것 · 못 받는 것
 *
 * 서버(`backend/app/attachments.py`)와 같은 목록을 여기서도 먼저 본다 — 20MB
 * 짜리 영상을 다 올린 뒤에 "형식이 틀렸다"를 듣지 않게. 최종 판단은 서버다.
 *
 * ## 무엇이 실제로 보나
 *
 * 첨부는 기획 단계에서 전략가가 원본을 본다. 영상은 영상을 볼 수 있는 모델
 * (Gemini)이 연결돼 있어야 내용이 닿는다 — 화면에 한 줄로 적는다(과장하지 않는다).
 */
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Icon } from "./icons";
import { api, ApiError } from "@/lib/api";
import { useErrorText, useLang } from "@/lib/i18n";

const IMAGE = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const VIDEO = ["video/mp4", "video/webm", "video/quicktime"];
const TEXT_EXT = [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".tsv"];
const MB = 1024 * 1024;
const MAX_FILE = 12 * MB;
const MAX_VIDEO = 20 * MB;
const MAX_TOTAL = 30 * MB;

/** 파일 고르기 창의 거르개 — 서버가 받는 형식과 같다. */
export const ACCEPT = [...IMAGE, ...VIDEO, "application/pdf", ".mov", ...TEXT_EXT].join(",");

type Kind = "image" | "video" | "document" | "text";

export type Att = {
  key: string;
  name: string;
  size: number;
  kind: Kind;
  /** 미리보기용 — 사진 · 영상만. 지울 때 놓아준다. */
  url: string | null;
  progress: number;
  id: string | null;
  error: string | null;
};

function kindOf(f: File): Kind | null {
  const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
  if (IMAGE.includes(f.type)) return "image";
  if (VIDEO.includes(f.type) || ext === ".mov") return "video";
  if (f.type === "application/pdf" || ext === ".pdf") return "document";
  if (TEXT_EXT.includes(ext) || f.type.startsWith("text/")) return "text";
  return null;
}

const mb = (n: number) => (n / MB).toFixed(n < 10 * MB ? 1 : 0);

/** 첨부 목록을 들고 올리기 · 지우기를 맡는다. */
export function useAttachments() {
  const { t } = useLang();
  const errText = useErrorText();
  const [items, setItems] = useState<Att[]>([]);
  // 콜백이 최신 목록을 읽게 — 렌더 중에 ref 를 쓰지 않고, 그린 뒤에 맞춘다.
  const live = useRef(items);
  useEffect(() => {
    live.current = items;
  }, [items]);

  const patch = (key: string, p: Partial<Att>) =>
    setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x)));

  const add = useCallback((files: Iterable<File>) => {
    let total = live.current.reduce((s, x) => s + (x.error ? 0 : x.size), 0);
    const next: Att[] = [];
    for (const f of files) {
      const kind = kindOf(f);
      const limit = kind === "video" ? MAX_VIDEO : MAX_FILE;
      const error = !kind
        ? t("attach.badType")
        : f.size > limit
          ? t("attach.tooBig", { mb: mb(f.size), max: limit / MB })
          : total + f.size > MAX_TOTAL
            ? t("attach.tooMuch", { max: MAX_TOTAL / MB })
            : null;
      if (!error) total += f.size;
      const a: Att = {
        key: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        name: f.name || "clipboard.png", size: f.size, kind: kind ?? "document",
        url: kind === "image" || kind === "video" ? URL.createObjectURL(f) : null,
        progress: 0, id: null, error,
      };
      next.push(a);
      if (!error) {
        // 붙여넣은 캡처는 이름이 없다 — 서버가 형식을 이름으로 가리므로 붙여준다.
        const named = f.name ? f : new File([f], "clipboard.png", { type: f.type });
        api.uploadAttachment(named, (p) => patch(a.key, { progress: p }))
          .then((m) => patch(a.key, { id: m.id, progress: 1 }))
          .catch((e) => patch(a.key, {
            error: e instanceof ApiError && e.status > 0 ? e.message : errText(e),
          }));
      }
    }
    if (next.length) setItems((xs) => [...xs, ...next]);
  }, [t, errText]);

  const remove = useCallback((key: string) => {
    const a = live.current.find((x) => x.key === key);
    if (!a) return;
    if (a.url) URL.revokeObjectURL(a.url);
    // 서버에 올라간 것은 지운다 — 남겨두면 주인만 볼 수 있는 쓰레기가 쌓인다.
    if (a.id) void api.deleteAttachment(a.id).catch(() => {});
    setItems((xs) => xs.filter((x) => x.key !== key));
  }, []);

  /** 실행을 시작한 뒤 — 화면에서만 비운다. 파일은 그 실행이 쓰므로 지우지 않는다. */
  const clear = useCallback(() => {
    live.current.forEach((a) => a.url && URL.revokeObjectURL(a.url));
    setItems([]);
  }, []);

  useEffect(() => () => live.current.forEach((a) => a.url && URL.revokeObjectURL(a.url)), []);

  const ready = items.filter((a) => a.id && !a.error);
  return {
    items, add, remove, clear,
    ids: ready.map((a) => a.id as string),
    uploading: items.some((a) => !a.id && !a.error),
    hasVideo: ready.some((a) => a.kind === "video"),
  };
}

/** 끌어다 놓는 자리. 파일을 끌고 들어오면 테두리가 밝아지고 안내가 뜬다. */
export function DropZone({ onFiles, children }: {
  onFiles: (files: File[]) => void;
  children: ReactNode;
}) {
  const { t } = useLang();
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e: React.DragEvent) => e.dataTransfer.types.includes("Files");
  return (
    <div
      className="relative"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => {
        if (hasFiles(e)) e.preventDefault();
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        onFiles([...e.dataTransfer.files]);
      }}
    >
      {children}
      <AnimatePresence>
        {over && (
          <motion.div
            className="pointer-events-none absolute inset-0 z-10 grid place-items-center
              rounded-xl border-2 border-dashed text-sm font-medium backdrop-blur-sm"
            style={{ borderColor: "var(--accent)", color: "var(--accent)",
                     background: "color-mix(in srgb, var(--accent) 10%, transparent)" }}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {t("attach.drop")}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** 클립 버튼 — 숨은 파일 입력을 연다. */
export function AttachButton({ onFiles, disabled }: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const { t } = useLang();
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1
          text-[12px] text-muted transition hover:border-accent hover:text-fg
          disabled:opacity-40"
        title={t("attach.hint")}
      >
        <Icon name="clip" size={14} />
        {t("attach.add")}
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        aria-label={t("attach.add")}
        onChange={(e) => {
          if (e.target.files?.length) onFiles([...e.target.files]);
          e.target.value = "";          // 같은 파일을 다시 고를 수 있게
        }}
      />
    </>
  );
}

/** 붙인 것들 — 미리보기 · 올리는 중 · 오류 · 빼기. */
export function AttachTray({ items, onRemove }: {
  items: Att[];
  onRemove: (key: string) => void;
}) {
  const { t } = useLang();
  if (!items.length) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-2" aria-label={t("attach.list")}>
      <AnimatePresence initial={false}>
        {items.map((a) => (
          <motion.li
            key={a.key}
            layout
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.18 }}
            className={`relative flex w-[176px] items-center gap-2 overflow-hidden rounded-xl
              border bg-[color:var(--panel-2)] p-1.5 pr-7 text-[11px]
              ${a.error ? "border-[color:var(--bad)]" : "border-line"}`}
            title={a.error ?? a.name}
          >
            <Thumb a={a} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-fg">{a.name}</span>
              <span className={`block truncate ${a.error ? "text-[color:var(--bad)]" : "text-dim"}`}>
                {a.error
                  ? a.error
                  : a.id
                    ? `${t(`attach.kind.${a.kind}`)} · ${mb(a.size)}MB`
                    : t("attach.uploading", { p: Math.round(a.progress * 100) })}
              </span>
            </span>
            <button
              type="button"
              onClick={() => onRemove(a.key)}
              aria-label={t("attach.remove", { name: a.name })}
              className="absolute right-1 top-1 grid size-5 place-items-center rounded-full
                text-dim transition hover:bg-panel2 hover:text-fg"
            >
              ×
            </button>
            {!a.id && !a.error && (
              <motion.span
                className="absolute inset-x-0 bottom-0 h-0.5 origin-left"
                style={{ background: "var(--accent)" }}
                animate={{ scaleX: Math.max(0.04, a.progress) }}
                transition={{ ease: "easeOut", duration: 0.2 }}
              />
            )}
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  );
}

function Thumb({ a }: { a: Att }) {
  const box = "grid size-9 shrink-0 place-items-center overflow-hidden rounded-lg bg-panel2";
  if (a.kind === "image" && a.url) {
    // eslint-disable-next-line @next/next/no-img-element -- 로컬 object URL 미리보기
    return <img src={a.url} alt="" className={`${box} object-cover`} />;
  }
  if (a.kind === "video" && a.url) {
    return (
      <span className={`${box} relative`}>
        <video src={a.url} muted preload="metadata" className="size-full object-cover" />
        <span className="absolute inset-0 grid place-items-center text-[10px] text-white
          [text-shadow:0_1px_3px_rgba(0,0,0,0.8)]">▶</span>
      </span>
    );
  }
  const ext = a.name.slice(a.name.lastIndexOf(".") + 1).toUpperCase().slice(0, 4);
  return <span className={`${box} text-[9px] font-semibold text-muted`}>{ext || "FILE"}</span>;
}
