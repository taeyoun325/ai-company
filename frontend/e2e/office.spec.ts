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


// ── 팀 배치 (DAY 26) ────────────────────────────────────────────────
test.describe("팀 배치", () => {
  async function teamOf(request: import("@playwright/test").APIRequestContext, id: string) {
    const o = await (await request.get("/api/office")).json();
    return (o.employees as { id: string; dept: string }[]).find((e) => e.id === id)?.dept;
  }

  test.afterEach(async ({ request }) => {
    // 다른 시험(말풍선 겹침 등)이 처음 배치를 기대한다 — 되돌린다.
    for (const id of ["writer", "designer", "analyst"]) {
      await request.patch(`/api/employees/${id}`, { data: { team: "" } });
    }
  });

  test("직원을 끌어 다른 팀 칸에 놓으면 그 팀으로 옮긴다", async ({ page, request }) => {
    await gotoOffice(page);
    const seat = page.locator("[data-employee=writer]");
    const room = page.locator("[data-team=dev]");
    await room.scrollIntoViewIfNeeded();
    const s = (await seat.boundingBox())!;
    const r = (await room.boundingBox())!;
    await page.mouse.move(s.x + s.width / 2, s.y + s.height / 2);
    await page.mouse.down();
    await page.mouse.move(r.x + r.width / 2, r.y + r.height * 0.8, { steps: 10 });
    // 놓기 전 — 놓을 칸이 드러난다.
    await expect(room).toContainText("여기로 옮기기");
    await page.mouse.up();
    await expect.poll(() => teamOf(request, "writer")).toBe("dev");
    // 새 자리가 그 칸 안에 있다.
    const after = (await seat.boundingBox())!;
    const cx = after.x + after.width / 2;
    expect(cx).toBeGreaterThan(r.x);
    expect(cx).toBeLessThan(r.x + r.width);
  });

  test("칸 밖에 놓으면 아무 일도 없다", async ({ page, request }) => {
    await gotoOffice(page);
    const seat = page.locator("[data-employee=writer]");
    await seat.scrollIntoViewIfNeeded();
    const s = (await seat.boundingBox())!;
    await page.mouse.move(s.x + s.width / 2, s.y + s.height / 2);
    await page.mouse.down();
    await page.mouse.move(s.x + s.width / 2, s.y - 200, { steps: 8 });   // 회의실 쪽
    await page.mouse.up();
    await page.waitForTimeout(500);
    expect(await teamOf(request, "writer")).toBe("docs");
  });

  test("누르기만 하면 옮기지 않고 고른다", async ({ page, request }) => {
    await gotoOffice(page);
    await page.locator("[data-employee=writer]").click();
    await expect(page.getByRole("button", { name: "닫기", exact: true })).toBeVisible();
    expect(await teamOf(request, "writer")).toBe("docs");
  });

  test("키보드로는 직원 카드의 소속 팀 목록에서 옮긴다", async ({ page, request }) => {
    await gotoOffice(page);
    const seat = page.getByRole("button", { name: /^정하린:/ });
    await seat.focus();
    await page.keyboard.press("Enter");
    await page.getByLabel("소속 팀").selectOption("qa");
    await expect.poll(() => teamOf(request, "designer")).toBe("qa");
  });

  test("한 팀에 넷이 모여도 말풍선·이름이 겹치지 않는다", async ({ page, request }) => {
    for (const id of ["writer", "designer", "analyst"]) {
      await request.patch(`/api/employees/${id}`, { data: { team: "dev" } });
    }
    await gotoOffice(page);
    await page.waitForTimeout(400);
    const boxes = await page.locator(".walker").evaluateAll((els) =>
      els.map((e) => e.getBoundingClientRect())
        .map((r) => ({ l: r.left, r: r.right, t: r.top, b: r.bottom })));
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i];
        const c = boxes[j];
        const overlap = a.l < c.r - 1 && c.l < a.r - 1 && a.t < c.b - 1 && c.t < a.b - 1;
        expect(overlap, `자리 ${i}·${j} 이 겹친다`).toBe(false);
      }
    }
  });
});
