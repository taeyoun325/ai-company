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
  // 배치 폭으로 잰다(offsetWidth). 사무실은 탭 카드 덱 안에서 줄여(CSS zoom)
  // 그려지므로 화면상 폭(getBoundingClientRect)은 배치 폭보다 작다 — 줄바꿈을
  // 가르는 것은 배치 폭이다.
  const width = await log.evaluate((e) => (e as HTMLElement).offsetWidth);
  expect(width).toBeGreaterThan(250);
  // "연결됨" · "N줄" 같은 머리글이 한 줄에 있어야 한다.
  const tall = await log.locator("span.whitespace-nowrap").evaluateAll((els) =>
    els.map((e) => (e as HTMLElement).offsetHeight).filter((h) => h > 24));
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

test("작업 지시에 사진·영상을 붙이면 올라가고, 로그가 무엇이 보였는지 정직하게 말한다 (DAY 28)",
  async ({ page, request }) => {
    const req = unique("간단한 계산기를 만들어주세요");
    await gotoOffice(page);
    await page.getByRole("textbox", { name: "무엇을 만들까요?" }).fill(req);
    const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
    await page.getByLabel("첨부", { exact: true }).setInputFiles([
      { name: "shot.png", mimeType: "image/png", buffer: png },
      { name: "clip.mp4", mimeType: "video/mp4", buffer: Buffer.from("0000001866747970", "hex") },
      { name: "tool.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") },
    ]);
    const tray = page.getByRole("list", { name: "첨부한 자료" });
    await expect(tray.getByText(/^사진 ·/)).toBeVisible();
    await expect(tray.getByText(/^영상 ·/)).toBeVisible();
    // 받지 않는 형식은 올리기 전에 거른다.
    await expect(tray.getByText("받지 않는 형식")).toBeVisible();

    await page.getByRole("button", { name: "AUTO 로 맡기기" }).click();
    await waitStatus(request, req, "done");
    const log = page.getByTestId("activity-log");
    await expect(log.getByText(/shot\.png/).first()).toBeVisible();
    // Mock 은 첨부를 보지 않는다 — 본 척하지 않고 그렇게 적는다.
    await expect(log.getByText(/Mock 직원은 첨부를 읽지 않습니다/)).toBeVisible();
    // 영상을 볼 수 있는 모델이 없으니 이름만 간다고 적는다.
    await expect(log.getByText(/영상은 이름만 전달됩니다/)).toBeVisible();
    // 맡긴 뒤에는 트레이를 비운다.
    await expect(tray).toHaveCount(0);
  });
