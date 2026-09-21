"use client";

/**
 * 로그인 관문 (DAY 15).
 *
 * ## 무엇을 막나
 *
 * `saas` 배포에서 로그인하지 않았으면 **화면 자체를 그리지 않는다.**
 * 뒤쪽 화면을 흐릿하게 깔아두고 그 위에 로그인 창을 띄우는 방식은
 * 예쁘지만, 뒤쪽 화면이 이미 데이터를 부르고 401 을 받고 있다는 뜻이다.
 * 그럴 바에야 안 그리는 게 낫다.
 *
 * `local` 배포에서는 아무것도 막지 않는다 — "내 컴퓨터에서 내가 쓴다"가
 * 전제이고, 거기서 로그인을 강제하면 아무도 안 지키는 규칙이 된다.
 *
 * ## 가입과 로그인을 한 화면에 둔다
 *
 * 화면을 나누면 "계정이 없는데 로그인 화면에 왔다"는 흔한 막힘이 생긴다.
 * 탭 하나로 오간다.
 */
import { useState, type FormEvent, type ReactNode } from "react";

import { useLang } from "@/lib/i18n";
import { Landing } from "./Landing";
import { Button, ErrorBox, Panel, Warning } from "./ui";
import { useAuth } from "@/lib/useAuth";

export function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useLang();
  const { user, required, loading, connectionError } = useAuth();

  // 첫 조회가 끝나기 전에 로그인 화면을 번쩍 보여주면, 이미 로그인한
  // 사용자가 매번 그 깜빡임을 본다.
  if (loading) {
    return (
      <p className="py-20 text-center text-sm text-dim">{t("auth.loading")}</p>
    );
  }

  // `/api/auth/me` 조차 실패했다면 로그인 문제가 아니라 연결 문제다.
  // 로그인 화면을 띄우면 사용자는 비밀번호를 의심하며 시간을 쓴다.
  if (!user && connectionError) {
    return (
      <div className="mx-auto max-w-md py-16">
        <ErrorBox>
          {t("auth.noBackend")}
          <span className="mt-1 block text-xs opacity-80">{connectionError}</span>
        </ErrorBox>
      </div>
    );
  }

  // 처음 온 사람에게 이메일 입력칸만 보여주면, 무엇에 가입하는지 모른 채
  // 가입하거나 그냥 닫는다. 제품이 무엇인지 먼저 말한다.
  if (!user && required) {
    // 레이아웃이 창 높이에 고정돼 있다(DAY 22). 랜딩은 긴 화면이라
    // 자기 스크롤을 가져야 한다 — 없으면 아래 절반이 영영 안 보인다.
    return (
      <div className="h-full overflow-y-auto">
        <Landing>
          <LoginScreen />
        </Landing>
      </div>
    );
  }
  return <>{children}</>;
}

function LoginScreen() {
  const { t } = useLang();
  const { signUp, logIn, firstUser, error } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">(
    firstUser ? "signup" : "login",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      if (mode === "signup") await signUp(email, password, name);
      else await logIn(email, password);
    } catch {
      /* 오류 문구는 useAuth 가 들고 있다 */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {firstUser && (
        <div className="mb-3">
          <Warning>
            <strong>{t("auth.firstAccount")}</strong> {t("auth.firstAccountBody")}
          </Warning>
        </div>
      )}

      <Panel>
        <div
          role="tablist"
          className="mb-4 flex rounded-lg border border-line p-0.5"
        >
          {(["login", "signup"] as const).map((m) => (
            <button
              key={m}
              role="tab"
              type="button"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm transition ${
                mode === m ? "bg-panel2 font-medium" : "text-muted hover:text-fg"
              }`}
            >
              {m === "login" ? t("auth.login") : t("auth.signup")}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <Field
            id="email"
            label={t("auth.email")}
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
            required
          />
          {mode === "signup" && (
            <Field
              id="name"
              label={t("auth.displayName")}
              value={name}
              onChange={setName}
              autoComplete="nickname"
              hint={t("auth.displayNameHint")}
            />
          )}
          <Field
            id="password"
            label={t("auth.password")}
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            hint={mode === "signup" ? t("auth.passwordHint") : undefined}
          />

          {error && <ErrorBox>{error}</ErrorBox>}

          <Button
            type="submit"
            tone="primary"
            className="w-full"
            disabled={busy || !email || !password}
          >
            {busy
              ? t("auth.working")
              : mode === "signup"
                ? t("auth.signupCta")
                : t("auth.login")}
          </Button>
        </form>
      </Panel>

      {/* 잊은 사람은 로그인 화면에서 잊었다는 것을 안다. 그 자리에
          길이 없으면 지원에 문의하거나 그냥 떠난다. */}
      {mode === "login" && (
        <p className="mt-3 text-center text-xs">
          <a href="/reset" className="text-muted underline hover:text-fg">
            {t("reset.forgot")}
          </a>
        </p>
      )}

      <p className="mt-3 text-center text-[11px] text-dim">
        {t("auth.noGoogle")}
      </p>
    </div>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
  required,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  autoComplete?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs text-muted">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required={required}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-line bg-panel2 px-3 py-2 text-sm
          outline-none focus:border-accent"
      />
      {hint && <p className="mt-1 text-[11px] text-dim">{hint}</p>}
    </div>
  );
}
