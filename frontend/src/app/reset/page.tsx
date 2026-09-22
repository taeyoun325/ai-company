"use client";

/**
 * 비밀번호 재설정 (DAY 22).
 *
 * 한 화면이 두 가지 일을 한다:
 *
 * - 토큰이 **없으면** 주소를 받아 링크를 보낸다.
 * - 토큰이 **있으면**(메일의 링크로 들어온 경우) 새 비밀번호를 받는다.
 *
 * 화면을 둘로 나누지 않은 이유: 링크가 만료된 사람이 "다시 요청" 하려면
 * 결국 앞 화면으로 돌아와야 한다. 같은 자리에 있으면 그 왕복이 없다.
 *
 * ## 계정이 있는지 알려주지 않는다
 *
 * 보냈든 안 보냈든 같은 문장을 보여준다. 그 이유까지 화면에 적는다 —
 * 안 적으면 "내 계정이 없어진 건가?" 하고 지원에 문의하게 된다.
 *
 * ## 메일이 안 나갔으면 안 나갔다고 한다
 *
 * 서버가 `delivered: false` 로 답하면 그대로 보여준다. 여기서 "보냈습니다"
 * 로만 적으면 사용자는 오지 않는 메일을 영원히 기다린다.
 */
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button, ErrorBox, Panel, Screen } from "@/components/ui";
import { api } from "@/lib/api";
import { useErrorText, useLang } from "@/lib/i18n";

export default function ResetPage() {
  const { t } = useLang();
  const errText = useErrorText();
  const router = useRouter();
  const token = (useSearchParams().get("token") ?? "").trim();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<{ delivered: boolean } | null>(null);
  const [done, setDone] = useState(false);

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.forgot(email.trim());
      setSent({ delivered: r.delivered });
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <div className="mx-auto max-w-md space-y-3">
        <Panel title={t("reset.title")}>
          {error && <ErrorBox>{error}</ErrorBox>}

          {done ? (
            <>
              <p className="text-sm text-muted">{t("reset.done")}</p>
              <Button
                tone="primary"
                className="mt-3 w-full"
                onClick={() => router.push("/")}
              >
                {t("reset.toOffice")}
              </Button>
            </>
          ) : token ? (
            <>
              <label className="block text-xs text-muted" htmlFor="new-pw">
                {t("reset.newPassword")}
              </label>
              <input
                id="new-pw"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void apply();
                }}
                className="mt-1 w-full rounded-xl border border-line bg-[color:var(--panel-2)]
                  px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <p className="mt-1 text-[11px] text-dim">{t("auth.passwordHint")}</p>
              <Button
                tone="primary"
                className="mt-3 w-full"
                disabled={busy || !password}
                onClick={() => void apply()}
              >
                {busy ? t("auth.working") : t("reset.apply")}
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm text-muted">{t("reset.askEmail")}</p>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void ask();
                }}
                className="mt-2 w-full rounded-xl border border-line bg-[color:var(--panel-2)]
                  px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <Button
                tone="primary"
                className="mt-3 w-full"
                disabled={busy || !email.trim()}
                onClick={() => void ask()}
              >
                {busy ? t("auth.working") : t("reset.send")}
              </Button>
              {sent && (
                <div className="mt-3 space-y-2 text-xs">
                  <p className="text-muted">{t("reset.sentAnyway")}</p>
                  {!sent.delivered && (
                    <p style={{ color: "var(--warn)" }}>
                      {t("reset.notDelivered")}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
    </Screen>
  );
}
