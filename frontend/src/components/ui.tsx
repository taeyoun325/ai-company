/**
 * 작은 공통 조각들. 화면마다 다시 만들면 같은 뜻이 다르게 보인다.
 */
import Link from "next/link";
import type { ReactNode } from "react";

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-line bg-panel ${className}`}
    >
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  tone = "default",
  type = "button",
  className = "",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "primary" | "danger" | "ghost";
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  const tones: Record<string, string> = {
    default: "border-line bg-panel2 hover:border-dim",
    primary: "border-transparent bg-accent text-white hover:brightness-110",
    danger: "border-transparent bg-bad text-white hover:brightness-110",
    ghost: "border-transparent bg-transparent text-muted hover:text-fg",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition
        disabled:cursor-not-allowed disabled:opacity-45 ${tones[tone]} ${className}`}
    >
      {children}
    </button>
  );
}

/**
 * Mock 배지 (§1 · §7).
 *
 * 이 배지가 화면에서 빠지면 사용자는 Mock 이 지어낸 글을 AI 의 작업
 * 결과로 믿는다. 그건 버그가 아니라 사고다. 그래서 눈에 띄는 전용 색을
 * 쓰고, 어디에도 그 색을 재사용하지 않는다.
 */
export function MockBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5
        text-[11px] font-semibold ${className}`}
      style={{
        color: "var(--mock)",
        borderColor: "color-mix(in srgb, var(--mock) 45%, transparent)",
        background: "color-mix(in srgb, var(--mock) 12%, transparent)",
      }}
      title="실제 모델이 아니라 Mock 제공자가 만든 결과입니다"
    >
      MOCK
    </span>
  );
}

export function Warning({ children }: { children: ReactNode }) {
  return (
    <div
      className="rounded-lg border px-3 py-2 text-sm"
      style={{
        color: "var(--mock)",
        borderColor: "color-mix(in srgb, var(--mock) 40%, transparent)",
        background: "color-mix(in srgb, var(--mock) 10%, transparent)",
      }}
    >
      {children}
    </div>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-lg border px-3 py-2 text-sm"
      style={{
        color: "var(--bad)",
        borderColor: "color-mix(in srgb, var(--bad) 40%, transparent)",
        background: "color-mix(in srgb, var(--bad) 10%, transparent)",
      }}
    >
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="px-1 py-6 text-center text-sm text-dim">{children}</p>
  );
}

export function StatusDot({ status }: { status: string }) {
  const color =
    status === "done"
      ? "var(--ok)"
      : status === "running"
        ? "var(--accent)"
        : status === "stopped"
          ? "var(--bad)"
          : "var(--dim)";
  return (
    <span
      aria-hidden
      className="inline-block size-2 rounded-full"
      style={{ background: color }}
    />
  );
}

export function NavLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="rounded-lg px-3 py-1.5 text-sm text-muted transition hover:bg-panel2 hover:text-fg"
    >
      {children}
    </Link>
  );
}

export function money(n: number | undefined) {
  if (typeof n !== "number") return "—";
  // 0 을 '$0.00' 으로 보여주면 '공짜'로 읽힌다. Mock 이 아니면서 0 이라면
  // 단가를 모른다는 뜻일 수 있다 — 소수 넷째 자리까지 보여 구분하게 한다.
  return n === 0 ? "$0" : `$${n.toFixed(n < 0.01 ? 4 : 2)}`;
}

export function when(ts: number | undefined) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
