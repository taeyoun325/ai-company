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
import { LANGS, LANG_LABEL, useLang } from "@/lib/i18n";
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
export function Nav() {
  const { t } = useLang();
  return (
    <>
      <NavLink href="/">{t("nav.office")}</NavLink>
      <NavLink href="/projects">{t("nav.projects")}</NavLink>
      <NavLink href="/pricing">{t("nav.pricing")}</NavLink>
      <NavLink href="/settings">{t("nav.settings")}</NavLink>
    </>
  );
}

export function Footer() {
  const { t } = useLang();
  return <>{t("footer.note")}</>;
}
