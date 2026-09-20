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

import { Button, ErrorBox, Panel, Warning } from "./ui";
import { useAuth } from "@/lib/useAuth";

export function AuthGate({ children }: { children: ReactNode }) {
  const { user, required, loading, connectionError } = useAuth();

  // 첫 조회가 끝나기 전에 로그인 화면을 번쩍 보여주면, 이미 로그인한
  // 사용자가 매번 그 깜빡임을 본다.
  if (loading) {
    return (
      <p className="py-20 text-center text-sm text-dim">불러오는 중…</p>
    );
  }

  // `/api/auth/me` 조차 실패했다면 로그인 문제가 아니라 연결 문제다.
  // 로그인 화면을 띄우면 사용자는 비밀번호를 의심하며 시간을 쓴다.
  if (!user && connectionError) {
    return (
      <div className="mx-auto max-w-md py-16">
        <ErrorBox>
          백엔드에 닿지 못했습니다. 서버가 떠 있는지 확인하세요.
          <span className="mt-1 block text-xs opacity-80">{connectionError}</span>
        </ErrorBox>
      </div>
    );
  }

  if (!user && required) return <LoginScreen />;
  return <>{children}</>;
}

function LoginScreen() {
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
    <div className="mx-auto max-w-md py-12">
      <div className="mb-5 text-center">
        <p className="text-3xl" aria-hidden>
          🏢
        </p>
        <h1 className="mt-1 text-lg font-bold">AI COMPANY</h1>
        <p className="mt-1 text-xs text-dim">
          AI 직원들이 실제 회사처럼 협업합니다. 당신은 CEO 입니다.
        </p>
      </div>

      {firstUser && (
        <div className="mb-3">
          <Warning>
            <strong>이 서버의 첫 계정입니다.</strong> 지금 만드는 계정이
            첫 사용자가 됩니다. 이 문구가 낯선 서버에서 보인다면 뭔가
            잘못된 것입니다.
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
              {m === "login" ? "로그인" : "가입"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <Field
            id="email"
            label="이메일"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
            required
          />
          {mode === "signup" && (
            <Field
              id="name"
              label="표시 이름"
              value={name}
              onChange={setName}
              autoComplete="nickname"
              hint="비워두면 이메일 앞부분을 씁니다."
            />
          )}
          <Field
            id="password"
            label="비밀번호"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            hint={mode === "signup" ? "10자 이상." : undefined}
          />

          {error && <ErrorBox>{error}</ErrorBox>}

          <Button
            type="submit"
            tone="primary"
            className="w-full"
            disabled={busy || !email || !password}
          >
            {busy ? "확인 중…" : mode === "signup" ? "가입하고 시작" : "로그인"}
          </Button>
        </form>
      </Panel>

      <p className="mt-3 text-center text-[11px] text-dim">
        구글 로그인은 아직 없습니다. 계정 구조는 나중에 끼울 수 있게
        만들어져 있습니다.
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
