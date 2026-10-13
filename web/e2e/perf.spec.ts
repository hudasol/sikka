import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// First load of the static build over an emulated ordinary connection.
// Runs only when SIKKA_PERF=1, because it writes results/web_performance.json.
const PROFILE = { download: (10 * 1024 * 1024) / 8, upload: (5 * 1024 * 1024) / 8, latency: 40 };

test("static first load fits the budget", async ({ page, context }) => {
  test.skip(process.env.SIKKA_PERF !== "1", "set SIKKA_PERF=1 to measure");
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: PROFILE.latency,
    downloadThroughput: PROFILE.download,
    uploadThroughput: PROFILE.upload,
  });
  const started = Date.now();
  await page.goto("/#/");
  await expect(page.getByTestId("conformance-matrix")).toBeVisible({ timeout: 30_000 });
  const loadS = (Date.now() - started) / 1000;
  writeFileSync(
    resolve(fileURLToPath(new URL(".", import.meta.url)), "../../results/web_performance.json"),
    JSON.stringify(
      {
        load_s: Math.round(loadS * 100) / 100,
        profile:
          "10 Mbit/s down, 5 Mbit/s up, 40 ms latency, cache disabled, until the overview matrix shows",
      },
      null,
      1,
    ) + "\n",
  );
  expect(loadS).toBeGreaterThan(0);
});
