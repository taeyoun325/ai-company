"use client";

/**
 * 헤더의 사용자 표시 (DAY 15).
 *
 * 로컬 모드에서는 "{t("auth.localUser")}"라고 **분명히** 적는다. 로그인 없이
 * 동작하는 상태를 감추면, 나중에 배포된 서버에서 같은 화면을 보고
 * "로그인했나?"를 헷갈린다.
 */
import { useState } from "react";

import { Icon } from "./icons";
import { Button } from "./ui";
import { useLang } from "@/lib/i18n";
import { useAuth } from "@/lib/useAuth";

/** `compact`: 탭 카드 덱의 좁은 여백에 들어가는 동그란 사람 아이콘. 누르면
 *  이름과 로그아웃이 옆으로 펼쳐진다(로컬 모드는 "로컬 사용자" 안내만). */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { t } = useLang();
  const { user, required, logOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  if (!user) return null;

  if (compact) {
    const name = required ? user.display_name : t("auth.localUser");
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={name}
          title={required ? user.email : t("auth.localHint")}
          className="grid size-9 place-items-center rounded-full border border-white/40
            bg-black/25 text-white/90 backdrop-blur-md transition-colors hover:bg-white/15"
        >
          <Icon name="person" size={16} />
        </button>
        {open && (
          <div className="absolute bottom-0 right-full mr-2 flex items-center gap-2
            whitespace-nowrap rounded-xl border border-line bg-[color:var(--panel-solid)]
            px-3 py-2 text-xs text-fg shadow-[var(--shadow)]">
            <span className={required ? "" : "text-dim"}>{name}</span>
            {required && (
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
            )}
          </div>
        )}
      </div>
    );
  }

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
