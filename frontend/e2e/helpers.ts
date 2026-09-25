import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const EMPLOYEES = ["한지수", "박도현", "최유나", "이서준", "정하린"];

/** 한 시험이 만든 프로젝트를 다른 시험의 것과 가르는 꼬리표. */
export function unique(base: string): string {
  return `${base} #${Date.now().toString(36)}`;
}

type Project = { slug: string; status: string; requirement: string };

export async function projectOf(request: APIRequestContext,
                                requirement: string): Promise<Project | undefined> {
  const res = await request.get("/api/projects?limit=50");
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { projects: Project[] };
  return body.projects.find((p) => p.requirement === requirement);
}

/** 서버 기록으로 상태를 기다린다 — 화면이 보여주는 것과 따로 확인한다. */
export async function waitStatus(request: APIRequestContext, requirement: string,
                                 status: string, timeout = 60_000): Promise<Project> {
  let last: Project | undefined;
  await expect.poll(async () => {
    last = await projectOf(request, requirement);
    return last?.status;
  }, { timeout, intervals: [250, 500, 1000] }).toBe(status);
  return last!;
}

export async function gotoOffice(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("textbox", { name: "무엇을 만들까요?" })).toBeVisible();
}

/** 화면에서 AUTO 로 일을 맡긴다. `gates` 는 켤 승인 단계의 이름(화면 글자). */
export async function handToAuto(page: Page, requirement: string, gates: string[] = []) {
  await page.getByRole("textbox", { name: "무엇을 만들까요?" }).fill(requirement);
  for (const g of gates) {
    await page.getByRole("checkbox", { name: new RegExp(g) }).check();
  }
  await page.getByRole("button", { name: "AUTO 로 맡기기" }).click();
}

/**
 * 번역표의 키 전부. 화면에 키가 **그대로** 찍히는지 볼 때 쓴다 — DAY 22 에
 * 상태 필터가 `list.done` 을 그리고 있었다. 소스 검사로는 안 잡힌다(`t()` 를
 * 부른 자리가 아니라 키가 든 변수를 그대로 그렸다).
 */
export function i18nKeys(): string[] {
  const src = readFileSync(path.join(__dirname, "..", "src", "lib", "i18n.tsx"), "utf-8");
  const keys = [...src.matchAll(/^\s*"([a-z][a-zA-Z0-9]*(?:\.[a-zA-Z0-9_]+)+)":\s*\{/gm)]
    .map((m) => m[1]);
  expect(keys.length).toBeGreaterThan(100);
  return keys;
}

export async function visibleText(page: Page): Promise<string> {
  return page.evaluate(() => document.body.innerText);
}

/** 가로로 넘치는가 — 폰에서 헤더 오른쪽이 화면 밖 173px 에 있었다(DAY 22). */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() =>
    Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
    - window.innerWidth);
}
