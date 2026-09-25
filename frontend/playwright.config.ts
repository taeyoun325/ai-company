/**
 * 화면 시험 (DAY 26) — `npm run test:e2e`
 *
 * ## 왜 생겼나
 *
 * DAY 25 까지 화면에는 다시 도는 시험이 없었다. 사무실·결재함·지시창은
 * 브라우저로 직접 돌려 확인했고, 번역표만 파이썬이 읽어 검사했다. DAY 22 의
 * 결함 절반(번역 키가 그대로 찍힘 · 폰에서 헤더가 화면 밖 · 마우스로만 쓸 수
 * 있는 자리)은 **소스만 봐서는 안 보이는** 것이었다.
 *
 * ## 무엇 위에서 도나
 *
 * `e2e/serve.mjs` 가 백엔드(Mock · 임시 데이터 폴더)와 프론트(next dev ·
 * `.next-e2e`)를 **따로** 띄운다. 켜둔 개발 서버(3000 · 8000)와 내 프로젝트
 * 목록을 건드리지 않는다.
 *
 * ## 브라우저
 *
 * 기본은 Playwright 가 받아둔 Chromium 이다(`npx playwright install chromium`).
 * 받지 않았으면 `PW_CHANNEL=msedge`(윈도우에 늘 있다) 또는 `chrome` 으로
 * 설치된 브라우저를 쓴다.
 *
 * 실행은 한 줄씩(workers 1). 백엔드 하나를 함께 쓰고, AUTO 실행은 좌석
 * (동시 실행 한도)을 쓰므로 나란히 돌리면 서로의 좌석을 뺏는다.
 */
import { defineConfig, devices } from "@playwright/test";

const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8765);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3765);
const channel = process.env.PW_CHANNEL || undefined;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    locale: "ko-KR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 800 },
    channel,
  },
  webServer: [
    {
      command: "node e2e/serve.mjs backend",
      url: `http://127.0.0.1:${BACKEND_PORT}/api/preflight`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: "node e2e/serve.mjs frontend",
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
