const { test, expect, chromium } = require("playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8096";
const evidence = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory"
);
const screenshots = path.join(evidence, "screenshots");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

test("M6.6-A owner flows and evidence", async () => {
  test.setTimeout(180_000);
  fs.mkdirSync(screenshots, { recursive: true });
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const context = await browser.newContext({ bypassCSP: true });
  const page = await context.newPage();
  const diagnostics = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) diagnostics.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()}`));
  const scans = [];
  const captures = [];

  async function capture(label) {
    for (const viewport of [
      { width: 390, height: 844, prefix: "mobile-390x844" },
      { width: 1440, height: 900, prefix: "desktop-1440x900" },
    ]) {
      await page.setViewportSize(viewport);
      await page.screenshot({
        path: path.join(screenshots, `${viewport.prefix}-${label}.png`),
        fullPage: false,
      });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth
      );
      const axeAvailable = await page.evaluate(() => Boolean(window.axe));
      if (!axeAvailable) {
        await page.addScriptTag({ path: axePath });
      }
      const violations = await page.evaluate(async () => {
        const result = await window.axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
        });
        return result.violations.map((item) => ({ id: item.id, impact: item.impact, nodes: item.nodes.length }));
      });
      captures.push({ label, viewport: `${viewport.width}x${viewport.height}`, overflow });
      scans.push({ label, viewport: `${viewport.width}x${viewport.height}`, violations });
      expect(overflow).toBe(false);
      expect(violations).toEqual([]);
    }
  }

  await page.goto(`${origin}/setup`);
  if (new URL(page.url()).pathname === "/setup") {
    await page.locator('[name="household_name"]').fill("M6.6 Directory Qualification");
    await page.locator('[name="timezone"]').fill("America/New_York");
    await page.locator('[name="display_name"]').fill("Directory Keeper");
    await page.locator('[name="email"]').fill("directory-qualification@example.test");
    await page.locator('[name="password"]').fill("correct horse battery staple");
    await page.locator('[name="password_confirmation"]').fill("correct horse battery staple");
    await page.getByRole("button", { name: /create household/i }).click();
  } else {
    await page.locator('[name="email"]').fill("directory-qualification@example.test");
    await page.locator('[name="password"]').fill("correct horse battery staple");
    await page.getByRole("button", { name: /sign in/i }).click();
  }
  await page.waitForURL(`${origin}/home`);

  const profiles = {};
  async function addAnimal(group, query, name) {
    await page.goto(`${origin}/animals/new`);
    await page.getByLabel("Animal type").selectOption(group);
    await page.getByLabel("Name").fill(name);
    const species = page.getByLabel("Species");
    await species.fill(query);
    await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
    await capture(`${group}-autocomplete`);
    await species.press("ArrowDown");
    await species.press("Enter");
    await expect(page.locator('[name="taxon_id"]')).not.toHaveValue("");
    await page.getByRole("button", { name: "Create animal" }).click();
    await page.waitForURL(/\/animals\/[0-9a-f-]+$/);
    profiles[group] = page.url();
  }

  await addAnimal("snake", "ball p", "Atlas");
  await addAnimal("lizard", "leopard gecko", "Lumen");
  await addAnimal("spider", "rose hair tarantula", "Rosie");
  await addAnimal("scorpion", "emperor scorpion", "Onyx");

  await page.goto(`${origin}/animals/new`);
  await page.getByLabel("Animal type").selectOption("snake");
  await page.getByLabel("Name").fill("Field Note");
  await page.getByLabel("Species").fill("Uncatalogued field snake");
  await expect(page.locator("[data-taxon-status]")).toContainText(/No matching|temporarily unavailable/, { timeout: 12000 });
  await capture("manual-fallback");
  await page.getByRole("button", { name: "Create animal" }).click();
  await page.waitForURL(/\/animals\/[0-9a-f-]+$/);
  const legacyProfile = page.url();

  await page.goto(profiles.snake);
  await expect(page.getByText("Python regius").first()).toBeVisible();
  await capture("linked-animal-profile");

  await page.goto(`${legacyProfile}/species`);
  const legacySearch = page.getByRole("combobox");
  await legacySearch.fill("ball p");
  await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
  await capture("legacy-link-species");
  await legacySearch.press("ArrowDown");
  await legacySearch.press("Enter");
  await page.getByRole("button", { name: "Save species link" }).click();
  await page.waitForURL(legacyProfile);
  await expect(page.getByText("Python regius").first()).toBeVisible();

  await page.goto(`${origin}/directory?group=plant&q=pothos`);
  await expect(page.getByText("Golden Pothos", { exact: true })).toBeVisible({ timeout: 12000 });
  await capture("plant-search");
  await page.getByText("Golden Pothos", { exact: true }).click();
  await expect(page.getByText("Epipremnum aureum", { exact: true }).first()).toBeVisible({ timeout: 12000 });
  await capture("plant-detail");

  await page.goto(`${origin}/directory?group=plant&q=zzzzqwertynotataxon`);
  await expect(page.getByRole("heading", { name: "No matching species" })).toBeVisible({ timeout: 12000 });
  await capture("no-results");

  fs.writeFileSync(
    path.join(evidence, "browser-qualification.partial.json"),
    JSON.stringify({ origin, captures, scans, diagnostics, pageErrors, failedRequests }, null, 2) + "\n"
  );
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  await browser.close();
});
