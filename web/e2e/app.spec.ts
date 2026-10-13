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

// Wait until every loading indicator has gone (data rendered), then a short pause.
async function settled(page: Page) {
  await page.waitForFunction(
    () => document.querySelectorAll('[role="status"]').length === 0,
    null,
    {
      timeout: 30_000,
    },
  );
  await page.waitForTimeout(500);
}

async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const summary = result.violations.map((v) => `${v.id}: ${v.nodes.length} node(s) ${v.help}`);
  expect(summary).toEqual([]);
}

function watchRequests(page: Page): string[] {
  const foreign: string[] = [];
  // Console errors (for example a map worker that fails to load) count as failures too.
  page.on("console", (message) => {
    if (message.type() === "error") {
      foreign.push(`console error: ${message.text()}`);
    }
  });
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
    await settled(page);
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
  await settled(page);
  await axe(page);
  expect(foreign).toEqual([]);
});

// Every screen in both languages and both themes. Settings are stored before
// the page loads, so each run starts directly in the chosen language and theme.
for (const lang of ["en", "ar"] as const) {
  for (const theme of ["light", "dark"] as const) {
    if (lang === "en" && theme === "light") {
      continue; // covered by the static screen tests above
    }
    for (const path of SCREENS) {
      test(`${lang} ${theme} ${path}: direction, theme and no axe violations`, async ({ page }) => {
        const foreign = watchRequests(page);
        await page.addInitScript(
          ([l, th]) => {
            window.localStorage.setItem("sikka.lang", l);
            window.localStorage.setItem("sikka.theme", th);
          },
          [lang, theme] as const,
        );
        await page.goto(`/#${path}`);
        await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");
        await expect(page.locator("html")).toHaveAttribute("lang", lang);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        if (lang === "ar") {
          await expect(page.getByTestId("synthetic-banner")).toContainText("بيانات مصطنعة");
        } else {
          await expect(page.getByTestId("synthetic-banner")).toHaveText(BANNER);
        }
        await settled(page);
        await axe(page);
        expect(foreign).toEqual([]);
      });
    }
  }
}

test("switching language and theme with the buttons", async ({ page }) => {
  await page.goto("/#/");
  await page.getByRole("button", { name: "Switch the interface to Arabic" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  const before = await page.locator("html").getAttribute("data-theme");
  await page.getByRole("button", { name: "تبديل المظهر الداكن" }).click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    before === "dark" ? "light" : "dark",
  );
});

test("an unknown address shows the not found screen", async ({ page }) => {
  await page.goto("/#/no-such-screen");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
  await expect(page.getByTestId("synthetic-banner")).toHaveText(BANNER);
  await page.getByRole("link", { name: "Go to the overview" }).click();
  await expect(page).toHaveURL(/#\/$/);
});

test("keyboard users reach the main content and see focus", async ({ page }) => {
  await page.goto("/#/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  const outline = await skip.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});
