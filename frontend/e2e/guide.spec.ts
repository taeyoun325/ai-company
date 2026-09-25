/**
 * 설명 탭 (DAY 26) — 헤더에서 닿고, 차례의 절이 다 있고, 말이 사무실과 같다.
 */
import { expect, test } from "./fixtures";

test("헤더의 '설명' 탭에서 열린다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "설명", exact: true }).click();
  await expect(page).toHaveURL(/\/guide$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("AI COMPANY 는 이렇게 일합니다");
});

test("차례의 절이 모두 있고, 누르면 그 절로 간다", async ({ page }) => {
  await page.goto("/guide");
  const toc = page.getByRole("navigation", { name: "이 페이지" });
  const links = toc.getByRole("link");
  await expect(links).toHaveCount(8);
  for (const href of await links.evaluateAll((els) => els.map((e) => e.getAttribute("href")))) {
    await expect(page.locator(href!)).toHaveCount(1);
  }
  await toc.getByRole("link", { name: "대표가 끼어드는 지점" }).click();
  await expect(page.locator("#gates")).toBeInViewport();
});

test("승인 지점·상태·결정은 사무실과 같은 말을 쓴다", async ({ page }) => {
  await page.goto("/guide");
  // 사무실의 승인 토글·결재 버튼·상태 이름과 같은 글자여야 한다.
  for (const word of ["계획 승인", "모든 결과 승인", "코드만 승인", "확신 낮을 때만",
                      "수정 요청", "보류", "폐기", "승인 대기", "연동 대기"]) {
    // 승인 지점 이름 앞에는 ★ 이 붙는다(사무실 토글과 같다).
    await expect(page.getByText(new RegExp(`^(★ )?${word}$`)).first()).toBeVisible();
  }
});

test("시작 버튼이 사무실로 간다", async ({ page }) => {
  await page.goto("/guide");
  await page.getByRole("link", { name: "사무실로 가기" }).click();
  await expect(page.getByRole("textbox", { name: "무엇을 만들까요?" })).toBeVisible();
});

// ── 움직임 (DAY 26) — motion.dev 끌기 · anime.js 등장/튀는 점 ─────────────
test("아래 절은 스크롤해서 그 자리에 와야 올라온다", async ({ page }) => {
  await page.goto("/guide");
  await page.waitForTimeout(600);
  expect(await page.locator("#staff [data-reveal]").count(),
         "스크롤하기 전에 이미 다 나와 있다 — 스크롤 등장이 안 돈다").toBeGreaterThan(0);
  await page.locator("#staff").scrollIntoViewIfNeeded();
  await expect(page.locator("#staff [data-reveal]")).toHaveCount(0);
});

test("카드를 끌면 기울며 따라오고, 놓으면 튕겨 돌아오며 점이 튄다", async ({ page }) => {
  await page.goto("/guide");
  const card = page.locator("#staff li").nth(2).locator("> div");
  await card.scrollIntoViewIfNeeded();
  await expect(page.locator("#staff [data-reveal]")).toHaveCount(0);
  const start = (await card.boundingBox())!;
  const cx = start.x + start.width / 2;
  const cy = start.y + start.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 140, cy + 30, { steps: 12 });
  const moved = (await card.boundingBox())!;
  expect(moved.x - start.x, "카드가 손을 따라오지 않았다").toBeGreaterThan(40);
  const rotate = await card.evaluate((e) => getComputedStyle(e).transform);
  expect(rotate, "끄는 방향으로 기울지 않았다").not.toBe("none");
  await page.mouse.up();
  // 놓는 순간 그 자리에 점이 튄다(anime.js) — 잠깐 있다가 사라진다.
  await expect(page.locator("body > div[aria-hidden=true] > span").first()).toBeAttached();
  // 스프링으로 제자리. (손을 치운다 — 올려 두면 살짝 커진 채로 있다.)
  await page.mouse.move(2, 2);
  await expect.poll(async () => {
    const b = (await card.boundingBox())!;
    return Math.max(Math.abs(b.x - start.x), Math.abs(b.y - start.y));
  }, { timeout: 4000 }).toBeLessThan(2);
  await expect(page.locator("body > div[aria-hidden=true] > span")).toHaveCount(0,
                                                                                { timeout: 3000 });
});

test("제목 낱말도 끌 수 있고 제자리로 돌아온다", async ({ page }) => {
  await page.goto("/guide");
  const word = page.locator("h1 .guide-word").nth(1).locator("> span");
  // 등장(anime.js)이 끝나 제자리에 선 뒤에 잰다 — 도는 중에 재면 "제자리"가 틀린다.
  let last = "";
  await expect.poll(async () => {
    const now = JSON.stringify(await word.boundingBox());
    const same = now === last;
    last = now;
    return same;
  }, { intervals: [250], timeout: 8000 }).toBe(true);
  const start = (await word.boundingBox())!;
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2);
  await page.mouse.down();
  await page.mouse.move(start.x + start.width / 2 + 60, start.y + 80, { steps: 8 });
  expect((await word.boundingBox())!.y - start.y).toBeGreaterThan(20);
  await page.mouse.up();
  await page.mouse.move(2, 2);
  await expect.poll(async () => Math.abs((await word.boundingBox())!.y - start.y),
                    { timeout: 4000 }).toBeLessThan(2);
  await expect(page.getByRole("heading", { level: 1 }))
    .toHaveText("AI COMPANY 는 이렇게 일합니다");
});

test.describe("움직임을 줄인 사람", () => {
  test.use({ reducedMotion: "reduce" });
  test("아무것도 숨기지 않고 끌리지도 않는다", async ({ page }) => {
    await page.goto("/guide");
    await expect(page.locator("[data-reveal]")).toHaveCount(0);
    await expect(page.getByText("카드와 제목 낱말을 끌어 보세요", { exact: false })).toHaveCount(0);
  });
});
