/**
 * 번역 — 화면에 **키가 그대로** 찍히지 않고, 영어 화면에 한국어가 새지 않는다.
 *
 * DAY 22 의 결함은 전부 "번역표에 없는 문자열"이 아니라 **번역표를 거치지
 * 않고 화면에 닿는 경로**였다. 소스 검사(`test_i18n_tables.py`)로는 안 보이고,
 * 화면을 열어 글자를 훑어야 보인다 — 그 일을 기계가 한다.
 */
import { expect, test } from "./fixtures";

import { EMPLOYEES, i18nKeys, unique, visibleText, waitStatus } from "./helpers";

const PAGES = ["/", "/guide", "/pricing", "/settings", "/projects"];
const keys = i18nKeys();

// 끝난 프로젝트가 하나는 있어야 점수판·결과 목록 같은 **기록을 그리는 칸**이
// 화면에 나온다. 빈 화면만 훑으면 거기 숨은 한국어(DAY 26 의 "미실행")를 못 본다.
test.beforeAll(async ({ request }) => {
  const requirement = unique("간단한 계산기를 만들어주세요");
  const res = await request.post("/api/runs", { data: { requirement } });
  expect(res.ok(), await res.text()).toBeTruthy();
  await waitStatus(request, requirement, "done");
});

for (const lang of ["ko", "en", "ja"] as const) {
  test.describe(lang, () => {
    test.use({ lang });

    for (const url of PAGES) {
      test(`${url} — 번역 키가 그대로 보이지 않는다`, async ({ page }) => {
        await page.goto(url);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("html")).toHaveAttribute("lang", lang);
        const text = await visibleText(page);
        const leaked = keys.filter((k) => text.includes(k));
        expect(leaked, `화면에 키가 찍혔다: ${leaked.join(", ")}`).toEqual([]);
      });
    }
  });
}

test.describe("en", () => {
  test.use({ lang: "en" });

  for (const url of PAGES) {
    test(`${url} — 영어 화면에 한국어가 새지 않는다`, async ({ page }) => {
      await page.goto(url);
      await page.waitForLoadState("networkidle");
      // 작업 로그는 기록이다 — 만들 때의 언어로 남는다(STATUS "번역"). 뺀다.
      await page.addStyleTag({ content: "[data-record]{display:none!important}" });
      let text = await visibleText(page);
      // 사람 이름·언어 이름·사용자가 쓴 요구사항(다른 시험이 만든 프로젝트)은
      // 번역 대상이 아니다. 그 줄만 뺀다.
      for (const allowed of [...EMPLOYEES, "한국어"]) text = text.replaceAll(allowed, "");
      const hangul = text.split("\n")
        .filter((l) => /[가-힣]/.test(l))
        .filter((l) => !/계산기|만들어주세요/.test(l));
      expect(hangul, "영어 화면에 남은 한국어 줄").toEqual([]);
    });
  }
});
