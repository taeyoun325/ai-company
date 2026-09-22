"use client";

/**
 * 이메일 확인 (DAY 22).
 *
 * 메일의 링크를 열면 이 화면이 뜬다. 여는 즉시 확인하고, 결과만 보여준다.
 *
 * ## 확인 전이라고 막지 않는다
 *
 * 막으면 **메일이 안 나가는 서버에서 아무도 제품을 못 쓴다.** 지금
 * 기본 발송기는 로그이므로, 막는 순간 그 서버는 잠긴다. 대신 화면이
 * 확인되지 않았다고 말한다 — 막는 것과 말하는 것은 다르다.
 */
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button, ErrorBox, Panel, Screen } from "@/components/ui";
import { api } from "@/lib/api";
import { useErrorText, useLang } from "@/lib/i18n";

export default function VerifyPage() {
  const { t } = useLang();
  const errText = useErrorText();
  const router = useRouter();
  const token = (useSearchParams().get("token") ?? "").trim();
  // 토큰이 없다는 것은 **effect 를 돌기 전에 이미 아는 사실**이다.
  // 상태로 만들어 effect 에서 세우면 그림을 한 번 그린 뒤 다시 그린다.
  const [state, setState] = useState<"working" | "done" | "failed" | null>(null);
  // 오류를 **문장이 아니라 값**으로 들고 있는다. 토큰은 1회용이라 언어가
  // 바뀌었다고 확인을 다시 부를 수는 없고, 그렇다고 그때 만든 한 문장을
  // 그대로 두면 언어를 바꿔도 그 줄만 안 바뀐다. 문장은 그릴 때 만든다.
  const [failure, setFailure] = useState<unknown>(null);
  const shown = token ? (state ?? "working") : "failed";

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api
      .verifyEmail(token)
      .then(() => alive && setState("done"))
      .catch((e: unknown) => {
        if (!alive) return;
        setFailure(e);
        setState("failed");
      });
    return () => {
      alive = false;
    };
  }, [token]);

  return (
    <Screen>
      <div className="mx-auto max-w-md">
        <Panel title={t("verify.title")}>
          {shown === "working" && (
            <p className="text-sm text-muted">{t("verify.working")}</p>
          )}
          {shown === "done" && (
            <p className="text-sm" style={{ color: "var(--ok)" }}>
              {t("verify.done")}
            </p>
          )}
          {shown === "failed" && <ErrorBox>{failure ? errText(failure) : t("reset.noToken")}</ErrorBox>}
          <Button
            tone="primary"
            className="mt-3 w-full"
            onClick={() => router.push("/")}
          >
            {t("reset.toOffice")}
          </Button>
        </Panel>
      </div>
    </Screen>
  );
}
