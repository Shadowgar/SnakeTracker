const { test, expect, chromium } = require("playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8097";
const evidence = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory/visual-rebuild"
);
const screenshots = path.join(evidence, "screenshots");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

test("M6.6-A Phase 2 visual reconstruction audit", async () => {
  test.setTimeout(180_000);
  fs.mkdirSync(screenshots, { recursive: true });
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const context = await browser.newContext({ bypassCSP: true });
  const page = await context.newPage();
  const consoleDiagnostics = [];
  const pageErrors = [];
  const requestFailures = [];
  const captures = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleDiagnostics.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText === "net::ERR_ABORTED") return;
    requestFailures.push(
      `${request.method()} ${request.url()} · ${request.failure()?.errorText || "unknown"}`
    );
  });

  await page.goto(`${origin}/login`);
  await page.locator('[name="email"]').fill("demo@carekeeper.local");
  await page.locator('[name="password"]').fill("carekeeper-demo-local-only");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(`${origin}/home`);
  await page.goto(`${origin}/animals`);
  const animalHref = await page.locator(".animal-collection-card").first().getAttribute("href");
  expect(animalHref).toMatch(/^\/animals\/[0-9a-f-]+$/);

  async function capture(viewport, label, route) {
    await page.setViewportSize(viewport);
    const response = await page.goto(`${origin}${route}`);
    expect(response.status()).toBe(200);
    await page.waitForLoadState("networkidle");
    await page.locator("img").evaluateAll(async (images) => {
      await Promise.all(images.map((image) => image.decode().catch(() => undefined)));
    });
    const csp = response.headers()["content-security-policy"] || "";
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("img-src 'self'");
    const geometry = await page.evaluate(() => ({
      documentHeight: document.documentElement.scrollHeight,
      horizontalOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth,
      imageCount: document.images.length,
      brokenImages: [...document.images].filter(
        (image) => !image.complete || image.naturalWidth === 0
      ).length,
    }));
    expect(geometry.horizontalOverflow).toBe(false);
    expect(geometry.brokenImages).toBe(0);
    await page.addScriptTag({ path: axePath });
    const violations = await page.evaluate(async () => {
      const result = await window.axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
        },
      });
      return result.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        nodes: violation.nodes.length,
        targets: violation.nodes.map((node) => node.target),
      }));
    });
    expect(violations).toEqual([]);
    await page.screenshot({
      path: path.join(screenshots, `${label}.png`),
      fullPage: false,
    });
    captures.push({
      label,
      viewport: `${viewport.width}x${viewport.height}`,
      route,
      csp,
      violations,
      ...geometry,
    });
  }

  const mobile = { width: 390, height: 844 };
  const desktop = { width: 1440, height: 900 };
  for (const [label, route] of [
    ["mobile-390x844-today", "/home"],
    ["mobile-390x844-animals", "/animals"],
    ["mobile-390x844-animal-profile", animalHref],
    ["mobile-390x844-calendar", "/calendar?view=agenda"],
    ["mobile-390x844-quick-log", "/quick-log"],
    ["mobile-390x844-enclosures", "/enclosures"],
  ]) await capture(mobile, label, route);
  for (const [label, route] of [
    ["desktop-1440x900-today", "/home"],
    ["desktop-1440x900-animals", "/animals"],
    ["desktop-1440x900-animal-profile", animalHref],
    ["desktop-1440x900-enclosures", "/enclosures"],
  ]) await capture(desktop, label, route);

  fs.writeFileSync(
    path.join(evidence, "browser-qualification.json"),
    JSON.stringify(
      { origin, captures, consoleDiagnostics, pageErrors, requestFailures },
      null,
      2
    ) + "\n"
  );
  expect(consoleDiagnostics).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(requestFailures).toEqual([]);
  await browser.close();
});
