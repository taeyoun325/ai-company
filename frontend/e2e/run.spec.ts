/**
 * 일을 맡기고 끝까지 — 대표 승인에서 멈추고, 승인하면 이어간다.
 *
 * 서버 기록(`/api/projects`)과 화면을 **따로** 확인한다. 화면만 보면 화면이
 * 거짓말을 해도 모르고, 서버만 보면 화면이 멈춰 있어도 모른다.
 */
import { expect, test } from "./fixtures";

import { gotoOffice, handToAuto, projectOf, unique, waitStatus } from "./helpers";

test("계획 승인을 켜면 멈춰서 기다리고, 승인하면 끝까지 간다", async ({ page, request }) => {
  const req = unique("간단한 계산기를 만들어주세요");
  await gotoOffice(page);
  await handToAuto(page, req, ["계획 승인"]);

  // 1) 멈췄다 — 서버는 `awaiting`, 화면은 결재함에 계획을 띄운다.
  await waitStatus(request, req, "awaiting");
  const desk = page.getByText("대표 결정 필요").first();
  await expect(desk).toBeVisible();
  // 승인 전에는 테스트도 코드도 없다 — 사후 통보가 아니라 승인이다.
  expect((await projectOf(request, req))?.status).toBe("awaiting");

  // 2) 승인 → 끝까지.
  await page.getByRole("button", { name: "승인", exact: true }).click();
  const done = await waitStatus(request, req, "done");
  await expect(page.getByRole("button", { name: /프로젝트 상세/ })).toBeVisible();

  // 3) 상세 화면에 산출물이 있다.
  await page.goto(`/projects/${encodeURIComponent(done.slug)}`);
  await expect(page.getByText("calc.py").first()).toBeVisible();
});

test("작업 로그 칸이 좁아져 글자가 한 자씩 세로로 쌓이지 않는다 (DAY 26)", async ({ page, request }) => {
  const req = unique("간단한 계산기를 만들어주세요");
  await gotoOffice(page);
  await handToAuto(page, req);
  await waitStatus(request, req, "done");
  const log = page.getByTestId("activity-log");
  await expect(log).toBeVisible();
  const width = await log.evaluate((e) => e.getBoundingClientRect().width);
  expect(width).toBeGreaterThan(250);
  // "연결됨" · "N줄" 같은 머리글이 한 줄에 있어야 한다.
  const tall = await log.locator("span.whitespace-nowrap").evaluateAll((els) =>
    els.map((e) => e.getBoundingClientRect().height).filter((h) => h > 24));
  expect(tall, "머리글이 여러 줄로 쪼개졌다").toEqual([]);
});

test("쉬는 실행은 정지 버튼으로 멈춘다", async ({ page, request }) => {
  const req = unique("간단한 계산기를 만들어주세요");
  await gotoOffice(page);
  await handToAuto(page, req, ["계획 승인"]);
  await waitStatus(request, req, "awaiting");
  await page.getByRole("button", { name: "정지", exact: true }).click();
  await waitStatus(request, req, "stopped");
});
