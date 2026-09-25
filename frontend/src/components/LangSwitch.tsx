"use client";

/**
 * 언어 고르기 (DAY 20).
 *
 * ## 셋뿐이라 펼쳐둔다
 *
 * 드롭다운은 **지금 무엇을 쓰는지**는 보여주지만 **무엇을 고를 수
 * 있는지**는 열어봐야 안다. 언어가 셋이면 그냥 나란히 두는 편이 짧다.
 *
 * ## 반쯤 번역됐다는 사실을 말한다
 *
 * 한국어 외의 언어를 고르면 아직 번역되지 않은 화면이 있다고 한 줄
 * 적는다. 말하지 않으면 사용자는 번역이 깨졌다고 생각한다 — 버그로
 * 읽히는 미완성은 미완성보다 나쁘다.
 */
import { usePathname } from "next/navigation";

import { LANGS, LANG_LABEL, useLang } from "@/lib/i18n";
import { useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { NavLink } from "./ui";

export function LangSwitch({ compact = false }: { compact?: boolean }) {
  const { lang, setLang, t } = useLang();

  return (
    <div
      className="flex items-center gap-0.5 rounded-lg border border-line bg-panel2 p-0.5"
      role="group"
      aria-label={t("nav.language")}
    >
      {LANGS.map((l) => {
        const on = l === lang;
        return (
          <button
            key={l}
            type="button"
            onClick={() => setLang(l)}
            aria-pressed={on}
            title={LANG_LABEL[l]}
            className={`rounded-md px-2 py-1 text-[11px] font-medium transition
              ${on ? "text-bg" : "text-muted hover:text-fg"}`}
            style={on ? { background: "var(--accent)" } : undefined}
          >
            {compact ? l.toUpperCase() : LANG_LABEL[l]}
          </button>
        );
      })}
    </div>
  );
}

/**
 * 이메일이 아직 확인되지 않았다는 알림 (DAY 22).
 *
 * 막지 않고 **말한다.** 확인 전이라고 막으면 메일이 안 나가는 서버에서
 * 아무도 제품을 못 쓴다 — 기본 발송기가 로그이므로 그 서버는 잠긴다.
 */
export function VerifyNote() {
  const { t } = useLang();
  const { user } = useAuth();
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!user || user.email_verified !== false) return null;

  return (
    <p className="flex items-center justify-center gap-2 border-b border-line
      px-4 py-1.5 text-[11px]" style={{ color: "var(--warn)" }}>
      {t("verify.notice")}
      {sent ? (
        <span className="text-dim">{t("verify.sent")}</span>
      ) : (
        <button
          type="button"
          disabled={busy}
          className="underline disabled:opacity-50"
          onClick={() => {
            setBusy(true);
            void api
              .sendVerification()
              .then(() => setSent(true))
              .finally(() => setBusy(false));
          }}
        >
          {t("verify.send")}
        </button>
      )}
    </p>
  );
}

/** 아직 번역되지 않은 화면이 있다는 알림. 한국어에서는 나오지 않는다. */
export function LangPartialNote() {
  const { lang, t } = useLang();
  if (lang === "ko") return null;
  return (
    <p className="border-b border-line px-4 py-1.5 text-center text-[11px] text-dim">
      {t("lang.partial")}
    </p>
  );
}

/**
 * 헤더 메뉴. 레이아웃이 서버 컴포넌트라 번역을 쓰려면 여기로 나와야 한다.
 */
/**
 * 머리말의 탭 — 셋뿐이다 (DAY 22).
 *
 * 프로젝트 목록은 탭에서 뺐다. 목록은 **일하는 동안 옆에 있어야 하는
 * 것**이지 따로 가서 보는 화면이 아니다 — 사무실 왼쪽 레일로 옮겼다.
 * 탭이 넷이면 사용자는 넷 다 한 번씩 눌러보고 나서야 어디가 작업
 * 화면인지 안다.
 */
export function Nav() {
  const { t } = useLang();
  const path = usePathname();
  const at = (href: string) =>
    href === "/" ? path === "/" || path.startsWith("/projects") ||
                   path.startsWith("/manual")
                 : path.startsWith(href);
  return (
    <>
      <NavLink href="/" active={at("/")}>{t("nav.office")}</NavLink>
      <NavLink href="/guide" active={at("/guide")}>{t("nav.guide")}</NavLink>
      <NavLink href="/pricing" active={at("/pricing")}>{t("nav.pricing")}</NavLink>
      <NavLink href="/settings" active={at("/settings")}>{t("nav.settings")}</NavLink>
    </>
  );
}
