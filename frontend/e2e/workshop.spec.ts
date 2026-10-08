/**
 * 작업장 — AUTO 실행을 슬롯 · 코드로 보는 화면.
 *
 * 지키려는 것:
 * 1. 작업장의 오더가 **진짜 실행**이 된다 — 서버 기록에 남고, 사무실과 같은 직원이
 *    슬롯을 맡는다(처음엔 화면 안에서만 도는 대본이었다).
 * 2. 검수대가 실제로 반려한 슬롯은 반려 횟수를 달고, 코드 창은 **실제로 쓴 파일**을
 *    보여준다.
 * 3. 버전 선택은 설정의 '직원별 모델'과 같은 값이다(서버 · 이 계정).
 * 4. 폰에서는 슬롯을 누르면 코드가 카드 전체로 올라오고, 닫을 수 있다.
 */
import { expect, test } from "./fixtures";

import { EMPLOYEES, unique, waitStatus } from "./helpers";

async function gotoWorkshop(page: import("@playwright/test").Page) {
  await page.goto("/workshop");
  await expect(page.getByRole("textbox", { name: "대표 오더" })).toBeVisible();
}

test("오더가 실제 실행이 되고, 사무실 직원이 슬롯을 맡아 검수까지 간다", async ({ page, request }) => {
  const req = unique("간단한 계산기를 만들어주세요");
  await gotoWorkshop(page);
  // 자리는 사무실 직원 다섯이다.
  for (const name of EMPLOYEES) {
    await expect(page.getByTestId(/^ws-desk-/).filter({ hasText: name }).first()).toBeVisible();
  }
  await page.getByRole("textbox", { name: "대표 오더" }).fill(req);
  await page.getByRole("button", { name: "오더 내리기" }).click();

  // 서버 기록으로 끝을 확인한다 — 화면만 보면 화면이 거짓말해도 모른다.
  await waitStatus(request, req, "done");

  const board = page.getByTestId("ws-board");
  await expect(page.getByText("통합 · 검수 끝")).toBeVisible();
  const t1 = board.getByRole("button").filter({ hasText: /^t1/ });
  await expect(t1).toContainText("통과");
  // Mock 대본은 첫 구현을 일부러 틀린다(0 나눗셈) — 실제 pytest 가 실패하고
  // 분석가가 반려한다. 그 사실이 슬롯에 남는다.
  await expect(t1).toContainText("반려 1회");

  await t1.click();
  const code = page.getByTestId("ws-code");
  await expect(code).toContainText("def div");
  await expect(code).toContainText("ValueError");
});

test("버전 선택은 설정의 직원별 모델과 같은 서버 값이다", async ({ page, request }) => {
  await gotoWorkshop(page);
  const select = page.getByTestId("ws-desk-developer").getByRole("combobox");
  await expect(select).toBeVisible();
  try {
    await select.selectOption("claude-sonnet-5-5");
    await expect.poll(async () => {
      const st = await (await request.get("/api/state")).json() as {
        employees: { id: string; model: string }[] };
      return st.employees.find((e) => e.id === "developer")?.model;
    }).toBe("claude-sonnet-5-5");
  } finally {
    await request.post("/api/employees/developer/model", { data: { model: "" } });
  }
});

test.describe("폰", () => {
  test.use({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });

  test("슬롯을 누르면 코드가 올라오고 닫힌다", async ({ page, request }) => {
    const req = unique("간단한 계산기를 만들어주세요");
    await gotoWorkshop(page);
    await page.getByRole("textbox", { name: "대표 오더" }).fill(req);
    await page.getByRole("button", { name: "오더 내리기" }).click();
    await waitStatus(request, req, "done");

    await page.getByTestId("ws-board").getByRole("button").filter({ hasText: /^t1/ }).click();
    const code = page.getByTestId("ws-code");
    await expect(code).toContainText("def div");
    await code.getByRole("button", { name: "닫기" }).click();
    await expect(code).toBeHidden();
  });
});
