/**
 * 폰 폭 — DAY 22 에 375px 로 줄여보고 셋을 찾았다:
 * 레일이 작업 칸을 130px 로 눌렀고, 헤더 오른쪽(언어·사용자 메뉴)이 화면 밖
 * 173px 에 있었고(= 폰에서는 언어를 못 바꿨다), 사무실 글이 한 단어씩 꺾였다.
 */
import { expect, test } from "./fixtures";

import { horizontalOverflow } from "./helpers";

test.use({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });

for (const url of ["/", "/pricing", "/settings", "/projects"]) {
  test(`${url} — 가로로 넘치지 않는다`, async ({ page }) => {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
  });
}

test("언어 전환이 화면 안에 있고 누를 수 있다", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const en = page.getByRole("button", { name: /^(EN|English)$/ }).first();
  await expect(en).toBeVisible();
  const box = await en.boundingBox();
  expect(box, "언어 전환 버튼이 그려지지 않았다").not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(375);
  await en.click();
  await expect(page.getByRole("textbox", { name: "What should we build?" })).toBeVisible();
});

test("사무실 작업 칸이 레일에 눌리지 않는다", async ({ page }) => {
  await page.goto("/");
  const box = await page.getByRole("textbox", { name: "무엇을 만들까요?" }).boundingBox();
  expect(box).not.toBeNull();
  // DAY 22 에는 130px 이었다. 접힌 레일(44px)과 여백을 빼면 265px 안팎이 정상.
  expect(box!.width).toBeGreaterThan(240);
});
