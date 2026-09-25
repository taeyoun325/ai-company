/**
 * 시험마다 화면 언어를 **못박는다.**
 *
 * 이 제품은 브라우저 언어를 따르지 않는다 — 처음 오는 사람에게는 영어, 고른
 * 적이 있으면 저장된 언어(`ai-company.lang`)다(i18n.tsx `detect`). 그래서
 * Playwright 의 `locale` 만으로는 한국어 화면이 안 뜬다. 첫 요청 전에 저장된
 * 값을 넣는다 — 화면이 언어를 읽는 바로 그 자리다.
 *
 *     test.use({ lang: "en" })   // 이 describe 는 영어 화면
 */
import { test as base } from "@playwright/test";

export const test = base.extend<{ lang: "ko" | "en" | "ja" }>({
  lang: ["ko", { option: true }],
  page: async ({ page, lang }, provide) => {
    await page.addInitScript((code) => {
      try {
        // 시험 안에서 언어를 바꾼 뒤(버튼)에는 덮어쓰지 않는다 — 첫 방문에만.
        if (!sessionStorage.getItem("e2e.lang.set")) {
          localStorage.setItem("ai-company.lang", code);
          sessionStorage.setItem("e2e.lang.set", "1");
        }
      } catch { /* 저장소가 막혀 있으면 기본값(영어)으로 뜬다 */ }
    }, lang);
    await provide(page);
  },
});

export { expect } from "@playwright/test";
