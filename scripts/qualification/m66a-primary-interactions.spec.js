const { test, expect, chromium } = require("playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "https://tracker.theroccos.us";
const evidence = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory/interaction-correction"
);
const screenshots = path.join(evidence, "screenshots");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

test("primary targets and top-layer overflow interactions", async () => {
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
  const results = [];

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

  async function visitPrimary(route, selector) {
    await page.goto(`${origin}${route}`);
    const primary = page.locator(selector).first();
    await expect(primary).toBeVisible();
    const href = await primary.getAttribute("href");
    expect(href).toBeTruthy();
    await primary.click();
    await page.waitForLoadState("domcontentloaded");
    const current = new URL(page.url());
    expect(current.pathname + current.search + current.hash).toBe(href);
    return href;
  }

  async function axe(route) {
    await page.goto(`${origin}${route}`);
    await page.addScriptTag({ path: axePath });
    return page.evaluate(async () => {
      const scan = await window.axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
        },
      });
      return scan.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        nodes: violation.nodes.length,
      }));
    });
  }

  async function auditOverflow(viewportLabel) {
    await page.goto(`${origin}/animals`);
    const initialUrl = page.url();
    const firstTrigger = page.locator(".animal-list .overflow-trigger").first();
    const firstTarget = await firstTrigger.getAttribute("popovertarget");
    const firstMenu = page.locator(`#${firstTarget}`);

    await firstTrigger.click();
    await expect(firstMenu).toBeVisible();
    expect(page.url()).toBe(initialUrl);
    expect(await firstTrigger.getAttribute("aria-expanded")).toBe("true");
    const firstGeometry = await firstMenu.evaluate((menu) => {
      const box = menu.getBoundingClientRect();
      const sample = document.elementFromPoint(box.left + 3, box.top + 3);
      return {
        top: box.top,
        right: box.right,
        bottom: box.bottom,
        left: box.left,
        position: getComputedStyle(menu).position,
        topLayerHit: sample === menu || menu.contains(sample),
      };
    });
    expect(firstGeometry.position).toBe("fixed");
    expect(firstGeometry.topLayerHit).toBe(true);
    expect(firstGeometry.left).toBeGreaterThanOrEqual(0);
    expect(firstGeometry.top).toBeGreaterThanOrEqual(0);
    expect(firstGeometry.right).toBeLessThanOrEqual(page.viewportSize().width);
    expect(firstGeometry.bottom).toBeLessThanOrEqual(page.viewportSize().height);

    await page.keyboard.press("Escape");
    await expect(firstMenu).toBeHidden();
    await expect(firstTrigger).toBeFocused();

    await firstTrigger.press("Enter");
    await expect(firstMenu).toBeVisible();
    expect(await firstMenu.evaluate((menu) => menu.contains(document.activeElement))).toBe(true);
    await page.locator("h1").click();
    await expect(firstMenu).toBeHidden();

    await firstTrigger.click();
    const secondaryAction = firstMenu.locator("a").first();
    const secondaryTarget = await secondaryAction.getAttribute("href");
    await secondaryAction.click();
    await page.waitForLoadState("domcontentloaded");
    const secondaryUrl = new URL(page.url());
    expect(secondaryUrl.pathname + secondaryUrl.search + secondaryUrl.hash).toBe(secondaryTarget);
    await page.goto(`${origin}/animals`);

    const lastTrigger = page.locator(".animal-list .overflow-trigger").last();
    await lastTrigger.scrollIntoViewIfNeeded();
    const lastTarget = await lastTrigger.getAttribute("popovertarget");
    const lastMenu = page.locator(`#${lastTarget}`);
    await lastTrigger.click();
    await expect(lastMenu).toBeVisible();
    expect(page.url()).toBe(initialUrl);
    const edgeGeometry = await lastMenu.evaluate((menu) => {
      const box = menu.getBoundingClientRect();
      return { top: box.top, right: box.right, bottom: box.bottom, left: box.left };
    });
    expect(edgeGeometry.left).toBeGreaterThanOrEqual(0);
    expect(edgeGeometry.top).toBeGreaterThanOrEqual(0);
    expect(edgeGeometry.right).toBeLessThanOrEqual(page.viewportSize().width);
    expect(edgeGeometry.bottom).toBeLessThanOrEqual(page.viewportSize().height);
    await page.screenshot({
      path: path.join(screenshots, `${viewportLabel}-top-layer-overflow.png`),
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    return { firstGeometry, edgeGeometry };
  }

  for (const viewport of [
    { label: "mobile-390x844", width: 390, height: 844 },
    { label: "desktop-1440x900", width: 1440, height: 900 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const todayTarget = await visitPrimary("/home", ".today-care-primary");
    const animalTarget = await visitPrimary("/animals", ".animal-collection-card");
    const enclosureTarget = await visitPrimary("/enclosures", ".enclosure-card");
    const calendarTarget = await visitPrimary("/calendar?view=agenda", ".agenda-primary");

    await page.goto(`${origin}/quick-log`);
    const picker = page.locator("[data-quick-log-selector]");
    await expect(picker).toBeVisible();
    const options = await picker.locator("option").evaluateAll((items) =>
      items.map((option) => option.value)
    );
    expect(options.length).toBeGreaterThan(1);
    await picker.selectOption(options[1]);
    await expect(page.locator(`[data-quick-log-animal="${options[1]}"]`)).toBeVisible();
    await expect(page.locator(`[data-quick-log-animal="${options[0]}"]`)).toBeHidden();

    const overflow = await auditOverflow(viewport.label);
    const violations = {};
    for (const [name, route] of Object.entries({
      today: "/home",
      animals: "/animals",
      enclosures: "/enclosures",
      calendar: "/calendar?view=agenda",
      quickLog: "/quick-log",
    })) {
      violations[name] = await axe(route);
      expect(violations[name]).toEqual([]);
    }
    results.push({
      viewport: `${viewport.width}x${viewport.height}`,
      primaryTargets: { todayTarget, animalTarget, enclosureTarget, calendarTarget },
      quickLogSelectedAnimalId: options[1],
      overflow,
      violations,
    });
  }

  const externalDiagnostics = consoleDiagnostics.filter(({ text }) =>
    /cloudflareinsights|static\.cloudflareinsights\.com|cdn-cgi\/rum|axe/i.test(text)
  );
  const applicationDiagnostics = consoleDiagnostics.filter(
    (entry) => !externalDiagnostics.includes(entry)
  );
  fs.writeFileSync(
    path.join(evidence, "browser-qualification.json"),
    JSON.stringify(
      {
        origin,
        results,
        applicationDiagnostics,
        externalDiagnostics,
        pageErrors,
        requestFailures,
      },
      null,
      2
    ) + "\n"
  );
  expect(applicationDiagnostics).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(requestFailures).toEqual([]);
  await browser.close();
});
