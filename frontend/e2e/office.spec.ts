/**
 * 사무실 화면 — 보이는가 · 키보드로 쓸 수 있는가 · 겹치지 않는가.
 */
import { expect, test } from "./fixtures";

import { EMPLOYEES, gotoOffice } from "./helpers";

test.beforeEach(async ({ page }) => {
  await gotoOffice(page);
});

test("직원 다섯이 자리마다 보이고, 상태와 이유를 이름에 싣는다", async ({ page }) => {
  for (const name of EMPLOYEES) {
    const seat = page.getByRole("button", { name: new RegExp(`^${name}:`) });
    await expect(seat).toBeVisible();
    // 이름표에 상태·이유가 같이 있어야 화면 낭독기가 "왜 멈췄나"를 읽는다.
    await expect(seat).toHaveAccessibleName(/.+: .+ — .+/);
  }
});

test("Mock 으로 돈다는 사실을 숨기지 않는다", async ({ page }) => {
  // 대본을 결과물로 착각하지 않도록 — 무료 요금제를 없앤 이유와 같다.
  await expect(page.getByText(/Mock/).first()).toBeVisible();
});

test("자리는 키보드만으로 고를 수 있다 (DAY 22: 마우스로만 됐다)", async ({ page }) => {
  const seat = page.getByRole("button", { name: /^박도현:/ });
  await seat.focus();
  await expect(seat).toBeFocused();
  await page.keyboard.press("Enter");
  const close = page.getByRole("button", { name: "닫기", exact: true });
  await expect(close).toBeVisible();
  await close.click();
  await expect(close).toBeHidden();
});

for (const width of [1024, 1280, 1600]) {
  test(`${width}px — 자리 말풍선이 옆자리와 겹치지 않는다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await gotoOffice(page);
    await expect(page.locator(".walker > .bubble").first()).toBeVisible();
    // 말풍선이 나타나는 애니메이션(0.25초)이 끝난 뒤 잰다.
    await page.waitForTimeout(400);
    const boxes = await page.locator(".walker > .bubble").evaluateAll((els) =>
      els.map((e) => e.getBoundingClientRect())
        .map((r) => ({ left: r.left, right: r.right, top: r.top })));
    boxes.sort((a, b) => a.left - b.left);
    for (let i = 1; i < boxes.length; i++) {
      if (Math.abs(boxes[i].top - boxes[i - 1].top) > 8) continue;   // 다른 줄
      expect(boxes[i].left, `말풍선 ${i - 1}·${i} 이 겹친다`)
        .toBeGreaterThanOrEqual(boxes[i - 1].right - 0.5);
    }
  });
}

test("지시창 — '현황 보고'가 기록을 읽어 답한다", async ({ page }) => {
  await page.getByRole("button", { name: "현황 보고" }).click();
  const log = page.getByRole("log", { name: "대표 지시창" });
  await expect(log).toContainText("현황 보고");          // 대표가 한 말
  await expect(log.getByText("비서실").first()).toBeVisible();   // 비서실의 답
});
