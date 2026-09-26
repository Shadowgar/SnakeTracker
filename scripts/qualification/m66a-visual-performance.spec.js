const { test, expect, chromium } = require("playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8096";
const output = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory/visual-performance.json"
);

test("M6.6-A representative visual-page performance", async () => {
  test.setTimeout(120_000);
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    serviceWorkers: "block",
  });
  await context.addInitScript(() => {
    window.__careKeeperLayoutShift = 0;
    new PerformanceObserver((entries) => {
      for (const entry of entries.getEntries()) {
        if (!entry.hadRecentInput) window.__careKeeperLayoutShift += entry.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const consoleDiagnostics = [];
  const harnessDiagnostics = [];
  const pageErrors = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      if (message.text() === "Service Worker registration blocked by Playwright") {
        harnessDiagnostics.push({ type: message.type(), text: message.text() });
        return;
      }
      consoleDiagnostics.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(`${origin}/login`);
  await page.locator('[name="email"]').fill("demo@carekeeper.local");
  await page.locator('[name="password"]').fill("carekeeper-demo-local-only");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(`${origin}/home`);
  await page.goto(`${origin}/animals`);
  const profilePath = await page.locator("a.animal-card", { hasText: "Atlas" }).first()
    .getAttribute("href");
  expect(profilePath).toBeTruthy();

  const samples = [];
  for (const [label, route] of [
    ["Today", "/home"],
    ["Animals", "/animals"],
    ["Animal Profile", profilePath],
    ["Enclosures", "/enclosures"],
  ]) {
    await cdp.send("Network.clearBrowserCache");
    const started = performance.now();
    const response = await page.goto(`${origin}${route}`);
    expect(response.status()).toBe(200);
    await page.waitForLoadState("networkidle");
    const elapsedMs = performance.now() - started;
    const metrics = await page.evaluate(() => {
      const navigation = performance.getEntriesByType("navigation")[0];
      const resources = performance.getEntriesByType("resource");
      const images = resources.filter((entry) => entry.initiatorType === "img");
      const visibleImages = [...document.images].filter((candidate) => {
        const bounds = candidate.getBoundingClientRect();
        return bounds.bottom >= 0 && bounds.top <= window.innerHeight;
      });
      return {
        domContentLoadedMs: navigation.domContentLoadedEventEnd,
        loadMs: navigation.loadEventEnd,
        layoutShift: window.__careKeeperLayoutShift,
        imageRequests: images.length,
        imageTransferBytes: images.reduce((total, entry) => total + entry.transferSize, 0),
        largestImageTransferBytes: Math.max(0, ...images.map((entry) => entry.transferSize)),
        visibleImageCount: visibleImages.length,
        incompleteVisibleImages: visibleImages.filter((candidate) => !candidate.complete).length,
      };
    });
    expect(elapsedMs).toBeLessThan(3000);
    expect(metrics.layoutShift).toBeLessThan(0.1);
    expect(metrics.imageTransferBytes).toBeLessThan(5 * 1024 * 1024);
    expect(metrics.largestImageTransferBytes).toBeLessThan(1024 * 1024);
    expect(metrics.incompleteVisibleImages).toBe(0);
    samples.push({ label, route, elapsedMs, ...metrics });
  }

  fs.writeFileSync(
    output,
    JSON.stringify({
      origin,
      viewport: "1440x900",
      limits: {
        elapsedMs: 3000,
        layoutShift: 0.1,
        imageTransferBytes: 5 * 1024 * 1024,
        largestImageTransferBytes: 1024 * 1024,
      },
      samples,
      consoleDiagnostics,
      harnessDiagnostics,
      pageErrors,
    }, null, 2) + "\n"
  );
  expect(consoleDiagnostics).toEqual([]);
  expect(pageErrors).toEqual([]);
  await browser.close();
});
