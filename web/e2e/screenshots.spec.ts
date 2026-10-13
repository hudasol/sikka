import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test } from "@playwright/test";

// Review screenshots of every screen in English and Arabic, light and dark.
// Runs only when SIKKA_SCREENSHOTS=1; images go to the private .sikka folder.
const SCREENS = [
  "overview",
  "contract",
  "validate",
  "conformance",
  "blackspots",
  "lineage",
  "tasking",
  "method",
  "pilot",
];
const OUT = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../.sikka/screenshots");

for (const lang of ["en", "ar"] as const) {
  for (const theme of ["light", "dark"] as const) {
    test(`screenshots ${lang} ${theme}`, async ({ page }) => {
      test.skip(process.env.SIKKA_SCREENSHOTS !== "1", "set SIKKA_SCREENSHOTS=1 to capture");
      test.setTimeout(180_000);
      await page.addInitScript(
        (settings: { lang: string; theme: string }) => {
          window.localStorage.setItem("sikka.lang", settings.lang);
          window.localStorage.setItem("sikka.theme", settings.theme);
        },
        { lang, theme },
      );
      for (const screen of SCREENS) {
        await page.goto(`/#/${screen === "overview" ? "" : screen}`);
        await page.waitForFunction(
          () => document.querySelectorAll('[role="status"]').length === 0,
          null,
          { timeout: 30_000 },
        );
        if (screen === "validate") {
          await page
            .locator("#sample-select")
            .selectOption("broken/crash_records_producer_b.ndjson");
          await page.locator("button.primary").first().click();
          await page.getByTestId("report").waitFor();
        }
        await page.waitForTimeout(800);
        await page.screenshot({ path: `${OUT}/${screen}-${lang}-${theme}.png`, fullPage: true });
      }
    });
  }
}
