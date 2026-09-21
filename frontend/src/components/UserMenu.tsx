"use client";

/**
 * 헤더의 사용자 표시 (DAY 15).
 *
 * 로컬 모드에서는 "{t("auth.localUser")}"라고 **분명히** 적는다. 로그인 없이
 * 동작하는 상태를 감추면, 나중에 배포된 서버에서 같은 화면을 보고
 * "로그인했나?"를 헷갈린다.
 */
import { useState } from "react";

import { Button } from "./ui";
import { useLang } from "@/lib/i18n";
import { useAuth } from "@/lib/useAuth";

export function UserMenu() {
  const { t } = useLang();
  const { user, required, logOut } = useAuth();
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  if (!required) {
    return (
      <span
        className="rounded-md border border-line px-2 py-1 text-[11px] text-dim"
        title={t("auth.localHint")}
      >
        {t("auth.localUser")}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-xs text-muted sm:inline" title={user.email}>
        {user.display_name}
      </span>
      <Button
        tone="ghost"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await logOut();
          } finally {
            setBusy(false);
          }
        }}
      >
        {t("auth.logout")}
      </Button>
    </div>
  );
}
