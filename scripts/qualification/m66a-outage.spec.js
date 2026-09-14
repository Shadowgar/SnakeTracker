const { test, expect, chromium } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8096";
const evidence = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory"
);
const screenshots = path.join(evidence, "screenshots");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

test("M6.6-A cached provider-outage fallback", async () => {
  test.setTimeout(60_000);
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const context = await browser.newContext({ bypassCSP: true });
  const page = await context.newPage();
  const diagnostics = [];
  const pageErrors = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) diagnostics.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(`${origin}/login`);
  await page.locator('[name="email"]').fill("directory-qualification@example.test");
  await page.locator('[name="password"]').fill("correct horse battery staple");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(`${origin}/home`);
  await page.goto(`${origin}/directory?group=snake&q=ball+p`);
  await expect(page.getByText("Live species search is unavailable. Showing saved results.")).toBeVisible();

  const results = [];
  for (const viewport of [
    { width: 390, height: 844, prefix: "mobile-390x844" },
    { width: 1440, height: 900, prefix: "desktop-1440x900" },
  ]) {
    await page.setViewportSize(viewport);
    await page.screenshot({
      path: path.join(screenshots, `${viewport.prefix}-cached-provider-outage.png`),
      fullPage: false,
    });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    await page.addScriptTag({ path: axePath });
    const violations = await page.evaluate(async () => {
      const scan = await window.axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
      });
      return scan.violations.map((item) => ({ id: item.id, impact: item.impact, nodes: item.nodes.length }));
    });
    results.push({ viewport: `${viewport.width}x${viewport.height}`, overflow, violations });
    expect(overflow).toBe(false);
    expect(violations).toEqual([]);
  }
  fs.writeFileSync(
    path.join(evidence, "browser-outage-qualification.json"),
    JSON.stringify({ origin, results, diagnostics, pageErrors }, null, 2) + "\n"
  );
  expect(pageErrors).toEqual([]);
  await browser.close();
});
