import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const SCREENS = [
  "/",
  "/contract",
  "/validate",
  "/conformance",
  "/blackspots",
  "/lineage",
  "/tasking",
  "/method",
  "/pilot",
];
const BANNER = "Synthetic data. No real crash, traffic or road records are used.";
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const summary = result.violations.map((v) => `${v.id}: ${v.nodes.length} node(s) ${v.help}`);
  expect(summary).toEqual([]);
}

function watchRequests(page: Page): string[] {
  const foreign: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    // blob: and data: URLs are created inside the page (for example the map worker)
    // and never leave the browser; only http(s) requests to other hosts count.
    const network = url.protocol === "http:" || url.protocol === "https:";
    if (network && !["127.0.0.1", "localhost"].includes(url.hostname)) {
      foreign.push(request.url());
    }
  });
  return foreign;
}

for (const path of SCREENS) {
  test(`static ${path}: banner, no foreign requests, no axe violations`, async ({ page }) => {
    const foreign = watchRequests(page);
    await page.goto(`/#${path}`);
    await expect(page.getByTestId("synthetic-banner")).toHaveText(BANNER);
    await expect(page.locator("h1")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await axe(page);
    expect(foreign).toEqual([]);
  });
}

test("validate a broken sample in the static demo", async ({ page }) => {
  const foreign = watchRequests(page);
  await page.goto("/#/validate");
  await expect(page.getByTestId("upload-disabled")).toBeVisible();
  await page.getByLabel("Sample feed").selectOption("broken/crash_records_producer_b.ndjson");
  await page.getByRole("button", { name: "Validate sample" }).click();
  const report = page.getByTestId("report");
  await expect(report).toBeVisible();
  await expect(report.getByText("SK-S008").first()).toBeVisible();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await page.waitForLoadState("networkidle");
  await axe(page);
  expect(foreign).toEqual([]);
});

test("Arabic, right to left, and dark theme stay accessible", async ({ page }) => {
  await page.goto("/#/");
  await page.getByRole("button", { name: "Switch the interface to Arabic" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByTestId("synthetic-banner")).toContainText("بيانات مصطنعة");
  await page.waitForLoadState("networkidle");
  await axe(page);
  await page.getByRole("button", { name: "تبديل المظهر الداكن" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", /dark|light/);
  await axe(page);
});

test("keyboard users reach the main content and see focus", async ({ page }) => {
  await page.goto("/#/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  const outline = await skip.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});
