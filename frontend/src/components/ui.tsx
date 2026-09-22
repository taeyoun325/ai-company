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
  ...rest
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  // 등장 애니메이션이 `data-reveal` 로 대상을 고른다(lib/motion.ts).
  // 감싸는 요소를 하나 더 두는 대신 속성을 그대로 통과시킨다 — 껍데기
  // div 가 늘어나면 그리드 간격이 어긋난다.
  // `title` 은 빼고 받는다. HTML 의 title 은 문자열(툴팁)이고 우리 것은
  // 제목 노드다. 그대로 합치면 두 타입이 충돌해서, 제목에 JSX 를 넘기던
  // 기존 화면들이 전부 타입 오류가 난다.
} & Omit<React.HTMLAttributes<HTMLElement>, "title">) {
  return (
    <section
      className={`glass glass-lit ${className}`}
      {...rest}
    >
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

/**
 * 사무실이 아닌 화면의 바깥 틀 (DAY 22).
 *
 * 레이아웃이 창 높이에 고정되면서(`overflow-hidden`) 각 화면이 **자기
 * 스크롤을 스스로 가져야** 한다. 화면마다 따로 적으면 하나를 빠뜨렸을 때
 * 그 화면만 스크롤이 안 되고, 그건 내용이 없는 것처럼 보인다.
 */
export function Screen({
  children, wide = false,
}: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className={`mx-auto px-4 py-5 ${wide ? "max-w-7xl" : "max-w-5xl"}`}>
        {children}
      </div>
    </div>
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
  // 유리 위에 올라가는 버튼이라 테두리와 배경이 둘 다 반투명이다.
  // 강조 버튼만 불투명한 그라데이션을 쓴다 — 누를 것이 하나라는 뜻이고,
  // 한 화면에 그런 버튼이 둘이면 둘 다 안 눌린다.
  const tones: Record<string, string> = {
    default:
      "border-line bg-panel2 hover:border-[color:var(--line-strong)] backdrop-blur",
    primary:
      "grad-accent border-transparent text-white shadow-[0_4px_16px_rgba(109,141,255,0.35)] hover:brightness-110",
    danger: "border-transparent bg-bad text-white hover:brightness-110",
    ghost: "border-transparent bg-transparent text-muted hover:text-fg",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-xl border px-3.5 py-1.5 text-sm font-medium transition
        active:scale-[0.98]
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
export function MockBadge({
  className = "", title = "Mock",
}: { className?: string; title?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5
        text-[11px] font-semibold ${className}`}
      style={{
        color: "var(--mock)",
        borderColor: "color-mix(in srgb, var(--mock) 45%, transparent)",
        background: "color-mix(in srgb, var(--mock) 12%, transparent)",
      }}
      title={title}
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

/**
 * 불러오는 중 자리 (DAY 22).
 *
 * ## 왜 필요한가
 *
 * 우리가 디자이너에게 시키는 규칙이 이것이다 — "상태를 빠뜨리지 마세요:
 * 비어 있을 때 · 불러오는 중 · 실패했을 때. 이 셋을 안 그린 화면은
 * 실제로 만들면 반드시 깨집니다"(roles.py). 정작 우리 화면 여럿이
 * **불러오는 중**을 안 그리고 있었다.
 *
 * 안 그리면 어떻게 되나: 데이터가 오기 전까지 빈 화면이 보이고, 느린
 * 연결에서는 그게 **"프로젝트가 하나도 없다"** 로 읽힌다. 사용자는
 * 자기 것이 사라졌다고 생각한다.
 *
 * ## 왜 빙글빙글 도는 것이 아니라 뼈대인가
 *
 * 회전만 하는 표시는 "뭔가 오고 있다"만 말하고 **무엇이 올지**는 말하지
 * 않는다. 뼈대는 올 것의 모양을 미리 보여주므로, 도착했을 때 눈이
 * 다시 자리를 찾지 않아도 된다.
 *
 * 움직임을 줄인 사람에게는 반짝임을 끈다 — 회색 칸만 남는다.
 */
export function Skeleton({
  lines = 3, className = "",
}: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="skeleton h-3 rounded-md"
          // 줄마다 길이를 다르게 둔다. 전부 같은 길이면 글이 아니라
          // 표처럼 보이고, 도착한 내용과 모양이 어긋난다.
          style={{ width: `${[92, 78, 85, 64, 71][i % 5]}%` }}
        />
      ))}
    </div>
  );
}

/** 카드 여러 장이 올 자리. */
export function SkeletonCards({ n = 3 }: { n?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2" aria-hidden>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="glass p-4">
          <Skeleton lines={3} />
        </div>
      ))}
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

/**
 * 머리말의 탭.
 *
 * 지금 어디에 있는지를 표시한다. 없으면 탭이 셋뿐이어도 "내가 지금 어느
 * 화면이지"를 매번 다시 읽어야 한다.
 */
export function NavLink({
  href, children, active = false,
}: { href: string; children: ReactNode; active?: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-xl px-3.5 py-1.5 text-sm transition ${
        active
          ? "bg-panel2 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
          : "text-muted hover:bg-panel2 hover:text-fg"
      }`}
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

/**
 * 날짜·시각을 **보는 사람의 언어로** 적는다 (DAY 22).
 *
 * 여기가 `"ko-KR"` 로 고정돼 있었다. 화면 글자는 전부 번역해 놓고 날짜만
 * `09. 22. 오전 08:23` 로 나오고 있었다 — 영어로 쓰는 사람에게는 읽히지
 * 않는 한 줄이고, 번역이 끝났다는 우리 주장에 난 구멍이었다.
 *
 * 시간대는 브라우저의 것을 그대로 쓴다. 서버 시간으로 적으면 "방금 만든
 * 것"이 몇 시간 전으로 보인다.
 */
const LOCALE: Record<string, string> = { ko: "ko-KR", en: "en-US", ja: "ja-JP" };

/** 걸린 시간. 초·분·시로만 적는다 — 이 제품의 실행은 그 범위다. */
export function took(from?: number, to?: number) {
  if (!from || !to || to <= from) return "";
  const s = Math.round(to - from);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}


/** 자릿수 구분이 있는 숫자. `98696` 은 한눈에 안 읽힌다. */
export function num(n: number, lang = "ko", digits = 0) {
  return n.toLocaleString(LOCALE[lang] ?? LOCALE.ko, {
    maximumFractionDigits: digits,
  });
}


export function when(ts: number | undefined, lang = "ko") {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(LOCALE[lang] ?? LOCALE.ko, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 같은 날 안의 항목에는 시:분만 적는다. 날짜는 묶음 제목이 말한다. */
export function clock(ts: number | undefined, lang = "ko") {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleTimeString(LOCALE[lang] ?? LOCALE.ko, {
    hour: "2-digit",
    minute: "2-digit",
  });
}
