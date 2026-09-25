/**
 * 설명 탭 (DAY 26) — 한 화면에서 장을 넘긴다. 스크롤하지 않는다.
 *
 * 지키는 것: 헤더에서 닿는다 · 여덟 장이 **한 화면에 들어간다** · 탭/키/버튼/끌기로
 * 넘어간다 · 주소(#장)로 바로 열린다 · 새 장의 조각이 올라온다(anime.js) · 말이
 * 사무실과 같다 · 세 언어 모두 새지 않는다 · 움직임을 줄여도 쓸 수 있다.
 */
import { expect, test } from "./fixtures";
import type { Page } from "@playwright/test";

import { EMPLOYEES, i18nKeys } from "./helpers";

const TABS = ["intro", "flow", "staff", "gates", "office", "money", "safety", "honest"];

const selected = (page: Page) => page.locator("[role=tab][aria-selected=true]");
const panel = (page: Page) => page.locator("[role=tabpanel]");

async function open(page: Page, id: string) {
  await page.locator(`#tab-${id}`).click();
  await expect(page.locator(`#panel-${id}`)).toBeVisible();
  // 들어오는 움직임(motion.dev 스프링 · anime.js 조각)이 끝날 때까지.
  await expect(page.locator(`#panel-${id} [data-reveal]`)).toHaveCount(0, { timeout: 5000 });
  await expect(page.locator("[role=tabpanel]")).toHaveCount(1);
}

test("헤더의 '설명' 탭에서 열린다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "설명", exact: true }).click();
  await expect(page).toHaveURL(/\/guide/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("AI COMPANY 는 이렇게 일합니다");
  await expect(page.getByRole("tab")).toHaveCount(TABS.length);
});

test("여덟 장이 모두 한 화면에 들어간다 — 페이지도 장도 스크롤되지 않는다", async ({ page }) => {
  await page.goto("/guide");
  for (const id of TABS) {
    await open(page, id);
    const fit = await panel(page).evaluate((el) => el.scrollHeight - el.clientHeight);
    expect(fit, `'${id}' 장이 화면을 넘친다`).toBeLessThanOrEqual(1);
    const root = await page.evaluate(() => {
      const el = document.querySelector("main > div")!;
      return el.scrollHeight - el.clientHeight;
    });
    expect(root, "페이지가 스크롤된다").toBeLessThanOrEqual(0);
  }
});

test("탭 · ←/→ 키 · 다음/이전 버튼으로 넘기고, 주소에 장이 남는다", async ({ page }) => {
  await page.goto("/guide");
  await open(page, "staff");
  await expect(page).toHaveURL(/#staff$/);
  await page.keyboard.press("ArrowRight");
  await expect(selected(page)).toHaveAttribute("id", "tab-gates");
  await page.keyboard.press("ArrowLeft");
  await expect(selected(page)).toHaveAttribute("id", "tab-staff");
  await page.getByRole("button", { name: /다음/ }).click();
  await expect(selected(page)).toHaveAttribute("id", "tab-gates");
  // 개발 서버에서는 Next 의 왼쪽 아래 배지가 '이전' 버튼 위에 떠 클릭을 가로챈다
  // (개발 모드에만 있다). 키보드로 누른다 — 버튼이 하는 일은 같다.
  await page.getByRole("button", { name: /이전/ }).focus();
  await page.keyboard.press("Enter");
  await expect(selected(page)).toHaveAttribute("id", "tab-staff");
  // 탭 목록 안에서는 ARIA 탭 패턴 — End 로 마지막 장.
  await page.locator("#tab-staff").focus();
  await page.keyboard.press("End");
  await expect(selected(page)).toHaveAttribute("id", "tab-honest");
  await expect(page.locator("#tab-honest")).toBeFocused();
});

test("주소의 #장 으로 바로 열린다", async ({ page }) => {
  await page.goto("/guide#gates");
  await expect(selected(page)).toHaveAttribute("id", "tab-gates");
});

test("옆으로 끌면 다음 장, 반대로 끌면 이전 장 (motion.dev)", async ({ page }) => {
  await page.goto("/guide");
  const box = (await panel(page).boundingBox())!;
  const y = box.y + box.height - 40;              // 버튼·링크가 없는 아래쪽 빈자리
  await page.mouse.move(box.x + box.width * 0.8, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.2, y, { steps: 10 });
  await page.mouse.up();
  await expect(selected(page)).toHaveAttribute("id", "tab-flow");
  await expect(page.locator("#panel-flow")).toBeVisible();
  await page.waitForTimeout(700);
  await page.mouse.move(box.x + box.width * 0.2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.8, y, { steps: 10 });
  await page.mouse.up();
  await expect(selected(page)).toHaveAttribute("id", "tab-intro");
});

test("조금만 끌면 넘어가지 않고 제자리로 돌아온다", async ({ page }) => {
  await page.goto("/guide");
  const box = (await panel(page).boundingBox())!;
  const y = box.y + box.height - 40;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 30, y, { steps: 20 });
  await page.mouse.up();
  await page.waitForTimeout(600);
  await expect(selected(page)).toHaveAttribute("id", "tab-intro");
});

test("새 장이 서면 그 안의 조각이 차례로 올라온다 (anime.js)", async ({ page }) => {
  await page.goto("/guide");
  await page.locator("#tab-staff").click();
  // 막 선 순간에는 아직 숨은 조각이 있다 — 곧 전부 올라온다.
  await expect.poll(() => page.locator("#panel-staff [data-reveal]").count(),
                    { intervals: [30, 30, 30] }).toBeGreaterThan(0);
  await expect(page.locator("#panel-staff [data-reveal]")).toHaveCount(0, { timeout: 5000 });
  await expect(page.locator("#panel-staff li")).toHaveCount(6);
});

test("승인 지점·상태·결정은 사무실과 같은 말을 쓴다", async ({ page }) => {
  await page.goto("/guide");
  await open(page, "gates");
  for (const word of ["계획 승인", "모든 결과 승인", "코드만 승인", "확신 낮을 때만",
                      "수정 요청", "보류", "폐기"]) {
    await expect(page.getByText(new RegExp(`^(★ )?${word}$`)).first()).toBeVisible();
  }
  await open(page, "office");
  for (const word of ["승인 대기", "연동 대기", "현황 보고", "왜 늦어져?"]) {
    await expect(page.getByText(word, { exact: true }).first()).toBeVisible();
  }
});

test("마지막 장의 시작 버튼이 사무실로 간다", async ({ page }) => {
  await page.goto("/guide#honest");
  await page.getByRole("link", { name: "사무실로 가기" }).click();
  await expect(page.getByRole("textbox", { name: "무엇을 만들까요?" })).toBeVisible();
});

// 장은 한 번에 하나만 그려지므로, 번역 검사(i18n.spec)는 첫 장만 본다. 여기서
// 장을 전부 넘기며 본다.
const KEYS = i18nKeys();
for (const lang of ["en", "ja"] as const) {
  test.describe(lang, () => {
    test.use({ lang });
    test(`여덟 장 모두 번역 키가 새지 않고 한국어가 남지 않는다`, async ({ page }) => {
      await page.goto("/guide");
      for (const id of TABS) {
        await open(page, id);
        let text = await panel(page).innerText();
        expect(KEYS.filter((k) => text.includes(k)), `'${id}' 장에 키가 찍혔다`).toEqual([]);
        for (const name of EMPLOYEES) text = text.replaceAll(name, "");
        const hangul = text.split("\n").filter((l) => /[가-힣]/.test(l));
        expect(hangul, `'${id}' 장에 한국어가 남았다`).toEqual([]);
      }
    });
  });
}

test.describe("움직임을 줄인 사람", () => {
  test.use({ reducedMotion: "reduce" });
  test("넘기기는 되고, 숨는 조각이 없다", async ({ page }) => {
    await page.goto("/guide");
    await page.waitForLoadState("networkidle");          // 키 처리기가 붙은 뒤에 누른다
    await expect(page.locator("[data-reveal]")).toHaveCount(0);
    await page.keyboard.press("ArrowRight");
    await expect(selected(page)).toHaveAttribute("id", "tab-flow");
    await expect(page.locator("#panel-flow [data-reveal]")).toHaveCount(0);
  });
});
