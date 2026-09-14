const { test, expect, chromium } = require("playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8096";
const output = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory/autocomplete-performance.json"
);

test("M6.6-A cached autocomplete latency", async () => {
  test.setTimeout(60_000);
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const page = await browser.newPage();
  await page.goto(`${origin}/login`);
  await page.locator('[name="email"]').fill("directory-qualification@example.test");
  await page.locator('[name="password"]').fill("correct horse battery staple");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(`${origin}/home`);

  const samples = await page.evaluate(async () => {
    const values = [];
    for (let index = 0; index < 50; index += 1) {
      const started = performance.now();
      const response = await fetch("/api/directory/search?group=snake&q=ball+p");
      const payload = await response.json();
      if (!response.ok || payload.state !== "cached") throw new Error("cache lookup failed");
      values.push(performance.now() - started);
    }
    return values;
  });
  const ordered = [...samples].sort((left, right) => left - right);
  const result = {
    origin,
    sample_count: samples.length,
    unit: "milliseconds",
    minimum: ordered[0],
    median: ordered[Math.floor(ordered.length * 0.5)],
    p95: ordered[Math.ceil(ordered.length * 0.95) - 1],
    maximum: ordered[ordered.length - 1],
    qualification_limit_p95: 250,
  };
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n");
  expect(result.p95).toBeLessThan(result.qualification_limit_p95);
  await browser.close();
});
