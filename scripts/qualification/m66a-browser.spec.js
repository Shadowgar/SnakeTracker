const { test, expect, chromium } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8096";
const evidence = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory"
);
const screenshots = path.join(evidence, "screenshots");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

test("M6.6-A owner flows and evidence", async () => {
  test.setTimeout(300_000);
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
  const navigationArtifacts = [];
  const scans = [];
  const captures = [];
  const cacheUpgrade = {};

  await page.route("**/static/pwa.js*", async (route) => {
    await route.fulfill({ contentType: "application/javascript", body: '"use strict";' });
  });
  await page.goto(`${origin}/setup`);
  cacheUpgrade.before = await page.evaluate(async () => {
    const stale = await caches.open("snaketracker-shell-v5");
    await stale.put(
      "/static/app.css?v=m65-c1",
      new Response(".taxon-results{position:absolute;top:100%}", {
        headers: { "Content-Type": "text/css" },
      })
    );
    return caches.keys();
  });
  await page.unroute("**/static/pwa.js*");
  await page.reload();
  await page.waitForFunction(async () => {
    if (!("serviceWorker" in navigator)) return false;
    const registration = await navigator.serviceWorker.ready;
    const names = await caches.keys();
    return Boolean(
      registration.active?.scriptURL.includes("m66-a-owner-c3")
      && names.includes("snaketracker-shell-m66-a-owner-c3")
      && !names.includes("snaketracker-shell-v5")
    );
  });
  cacheUpgrade.after = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    const stylesheet = document.querySelector('link[rel="stylesheet"][href*="app.css"]');
    const stylesheetUrl = new URL(stylesheet.href);
    const response = await fetch(stylesheet.href, { cache: "reload" });
    const bytes = await response.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return {
      caches: await caches.keys(),
      serviceWorkerUrl: registration.active?.scriptURL || "",
      stylesheetUrl: `${stylesheetUrl.pathname}${stylesheetUrl.search}`,
      stylesheetSha256: Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""),
    };
  });
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) diagnostics.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    const detail = `${request.method()} ${request.url()} · ${request.failure()?.errorText || "unknown"}`;
    if (new URL(request.url()).pathname === "/static/favicon.svg" && request.failure()?.errorText === "net::ERR_ABORTED") {
      navigationArtifacts.push(detail);
      return;
    }
    failedRequests.push(detail);
  });

  async function capture(label, focusSelector = null) {
    for (const viewport of [
      { width: 390, height: 844, prefix: "mobile-390x844" },
      { width: 1440, height: 900, prefix: "desktop-1440x900" },
    ]) {
      await page.setViewportSize(viewport);
      if (focusSelector) {
        await page.locator(focusSelector).evaluate((element) =>
          element.scrollIntoView({ block: "center", inline: "nearest" })
        );
      }
      await page.screenshot({
        path: path.join(screenshots, `${viewport.prefix}-${label}.png`),
        fullPage: false,
      });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth
      );
      const autocompleteGeometry = await page.evaluate(() => {
        const input = document.querySelector('[role="combobox"]');
        const list = document.querySelector('[data-taxon-results]:not([hidden])');
        const next = document.querySelector('[name="sex"]');
        if (!input || !list) return null;
        const inputBox = input.getBoundingClientRect();
        const listBox = list.getBoundingClientRect();
        const nextBox = next?.closest("label")?.getBoundingClientRect();
        const style = getComputedStyle(list);
        return {
          position: style.position,
          inputWidth: inputBox.width,
          listWidth: listBox.width,
          input: { left: inputBox.left, right: inputBox.right, top: inputBox.top, bottom: inputBox.bottom },
          list: { left: listBox.left, right: listBox.right, top: listBox.top, bottom: listBox.bottom },
          topGap: listBox.top - inputBox.bottom,
          clearsNextField: nextBox ? listBox.bottom <= nextBox.top : true,
        };
      });
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
      captures.push({ label, viewport: `${viewport.width}x${viewport.height}`, overflow, autocompleteGeometry });
      scans.push({ label, viewport: `${viewport.width}x${viewport.height}`, violations });
      expect(overflow).toBe(false);
      expect(violations).toEqual([]);
      if (autocompleteGeometry) {
        expect(autocompleteGeometry.position).toBe("static");
        expect(Math.abs(autocompleteGeometry.inputWidth - autocompleteGeometry.listWidth)).toBeLessThan(2);
        expect(autocompleteGeometry.topGap).toBeGreaterThanOrEqual(0);
        expect(autocompleteGeometry.topGap).toBeLessThanOrEqual(8);
        expect(autocompleteGeometry.clearsNextField).toBe(true);
      }
    }
  }

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
  async function addAnimal(group, query, name, options = {}) {
    await page.goto(`${origin}/animals/new`);
    await page.getByLabel("Animal type").selectOption(group);
    await page.getByLabel("Name").fill(name);
    const species = page.getByLabel("Species", { exact: true });
    await species.fill(query);
    await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
    await capture(`${group}-autocomplete`);
    await species.press("ArrowDown");
    await species.press("Enter");
    await expect(page.locator('[name="taxon_id"]')).not.toHaveValue("");
    await expect(page.locator("[data-taxon-results]")).toBeHidden();
    if (options.reference) {
      await expect(page.locator("[data-reference-photo-options]")).toBeVisible();
      await expect(page.locator("[data-reference-photo-copy]")).toContainText("Species reference image available");
      await expect(page.locator("[data-reference-photo-copy]")).toContainText("not your individual animal");
      await capture("selected-species-after-list-closes", "[data-reference-photo]");
      await capture("new-animal-selected-species-reference-option", "[data-reference-photo]");
      await page.locator("details.form-advanced > summary").click();
      await capture("morph-helper-text", "[data-morph-field]");
      await capture("genetics-helper-text", "[data-genetics-field]");
      await capture("more-identity-details", "details.form-advanced");
      await page.getByLabel("Morph / variant").fill(options.morph || "Recorded variant");
      await page.getByLabel("Genetics / lineage").fill(options.genetics || "Known lineage");
      await page.getByLabel("Use species reference image for now").check();
    }
    await page.getByRole("button", { name: "Create animal" }).click();
    await page.waitForURL(/\/animals\/[0-9a-f-]+$/);
    profiles[group] = page.url();
  }

  await addAnimal("spider", "rose hair tarantula", "Rosie", {
    reference: true,
    morph: "Copper locality",
    genetics: "Known captive lineage",
  });

  const referenceProfileResponse = await page.goto(profiles.spider);
  expect(referenceProfileResponse.headers()["content-security-policy"]).toContain("img-src 'self'");
  expect(referenceProfileResponse.headers()["content-security-policy"]).toContain("script-src 'self'");
  await expect(page.getByAltText(/Species reference image for/)).toBeVisible({ timeout: 12000 });
  await expect(page.getByText(/Species reference image/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Add my animal's photo" })).toBeVisible();
  await capture("animal-profile-species-reference");
  await capture("animal-profile-reference-attribution");
  await capture("add-my-animal-photo-action");

  await page.getByRole("link", { name: "Add my animal's photo" }).click();
  const personalPhoto = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 480;
    canvas.height = 360;
    const context = canvas.getContext("2d");
    const gradient = context.createLinearGradient(0, 0, 480, 360);
    gradient.addColorStop(0, "#7c3aed");
    gradient.addColorStop(1, "#f59e0b");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 480, 360);
    context.fillStyle = "#ffffff";
    context.font = "700 42px sans-serif";
    context.fillText("Rosie", 172, 190);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("JPEG, PNG, or WebP image").setInputFiles({
    name: "rosie.png",
    mimeType: "image/png",
    buffer: Buffer.from(personalPhoto, "base64"),
  });
  await page.getByRole("button", { name: "Save photo" }).click();
  await page.waitForURL(profiles.spider);
  await expect(page.getByAltText("Profile photo of Rosie")).toBeVisible();
  await expect(page.getByRole("link", { name: "Change photo" })).toBeVisible();
  await expect(page.locator(".reference-attribution")).toHaveCount(0);
  await capture("animal-profile-personal-photo");

  await page.goto(`${origin}/animals/new`);
  await page.getByLabel("Animal type").selectOption("spider");
  await page.getByLabel("Name").fill("Suggestion Review");
  const suggestionSpecies = page.getByLabel("Species", { exact: true });
  await suggestionSpecies.fill("rose hair tarantula");
  await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
  await suggestionSpecies.press("ArrowDown");
  await suggestionSpecies.press("Enter");
  await page.locator("details.form-advanced > summary").click();
  await expect(page.locator("[data-morph-suggestion-chips]")).toContainText("Copper locality");
  await expect(page.locator("[data-genetics-suggestion-chips]")).toContainText("Known captive lineage");
  await expect(page.getByLabel("Morph / variant")).toHaveValue("");
  await expect(page.getByLabel("Genetics / lineage")).toHaveValue("");
  await capture("morph-and-genetics-suggestions", "[data-morph-suggestion-chips]");

  await page.goto(`${origin}/animals/new`);
  await page.getByLabel("Animal type").selectOption("snake");
  await page.getByLabel("Name").fill("No Reference Review");
  const noReferenceSpecies = page.getByLabel("Species", { exact: true });
  await noReferenceSpecies.fill("Typhlops agoralionis");
  await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
  await noReferenceSpecies.press("ArrowDown");
  await noReferenceSpecies.press("Enter");
  await expect(page.locator("[data-reference-photo-options]")).toBeHidden();
  await expect(page.locator("[data-reference-photo-placeholder]")).toBeVisible();
  await expect(page.locator("[data-reference-photo-placeholder]")).not.toContainText("◇");
  await expect(page.locator("[data-reference-photo-copy]")).toContainText(
    "No licensed species reference image is available for this Directory record"
  );
  await capture("new-animal-no-reference-image", "[data-reference-photo]");

  await addAnimal("snake", "ball p", "Atlas");
  await addAnimal("lizard", "leopard gecko", "Lumen");
  await addAnimal("scorpion", "emperor scorpion", "Onyx");

  await page.goto(`${origin}/animals/new`);
  await page.getByLabel("Animal type").selectOption("snake");
  await page.getByLabel("Name").fill("Field Note");
  await page.getByLabel("Species", { exact: true }).fill("Uncatalogued field snake");
  await expect(page.locator("[data-taxon-status]")).toContainText(/No matching|temporarily unavailable/, { timeout: 12000 });
  await capture("manual-fallback");
  await page.locator("details.form-advanced > summary").click();
  await page.getByLabel("Morph / variant").fill("Legacy Locality / ALPHA");
  await page.getByLabel("Genetics / lineage").fill("legacy het notation ??");
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
  await page.goto(`${legacyProfile}/edit`);
  await page.locator("details.form-advanced > summary").click();
  await expect(page.getByLabel("Morph / variant")).toHaveValue("Legacy Locality / ALPHA");
  await expect(page.getByLabel("Genetics / lineage")).toHaveValue("legacy het notation ??");
  await capture("legacy-animal-edit-preserved-values", '[name="morph"]');

  await page.goto(`${origin}/enclosures/new`);
  await capture("add-enclosure-type-dropdown");
  await page.getByLabel("Name").fill("Tropical Gecko Enclosure");
  await page.locator('[name="enclosure_type_choice"]').selectOption("Glass terrarium");
  await page.getByRole("button", { name: "Create enclosure" }).click();
  await page.waitForURL(/\/enclosures\/[0-9a-f-]+$/);
  const enclosureProfile = page.url();
  await expect(page.getByRole("heading", { name: "No plants added" })).toBeVisible();
  await capture("enclosure-no-plants");

  await page.goto(`${origin}/enclosures/new`);
  await page.getByLabel("Name").fill("Converted Display Habitat");
  await page.locator('[name="enclosure_type_choice"]').selectOption("Custom / other");
  await page.getByLabel("Describe enclosure type").fill("Converted display cabinet");
  await capture("custom-enclosure-type");
  await page.getByRole("button", { name: "Create enclosure" }).click();
  await page.waitForURL(/\/enclosures\/[0-9a-f-]+$/);
  const legacyEnclosure = page.url();
  await page.goto(`${legacyEnclosure}/edit`);
  await expect(page.locator('[name="enclosure_type_choice"]')).toContainText("Keep current: Converted display cabinet");
  await capture("legacy-enclosure-edit");

  await page.goto(`${enclosureProfile}/plants/new`);
  await capture("add-plant");
  const eligiblePlant = await page.evaluate(async () => {
    for (const query of ["golden pothos", "common reed", "monstera", "boston fern"]) {
      const response = await fetch(`/api/directory/search?group=plant&q=${encodeURIComponent(query)}`);
      const payload = await response.json();
      const record = payload.records?.find((candidate) => candidate.reference_image_available);
      if (record) return record;
    }
    return null;
  });
  expect(eligiblePlant).not.toBeNull();
  const plantSearch = page.getByLabel("Plant species or name");
  await plantSearch.fill(eligiblePlant.common_name || eligiblePlant.scientific_name);
  await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
  await capture("plant-autocomplete");
  await page.locator('[role="option"]').filter({ hasText: eligiblePlant.scientific_name }).first().click();
  await page.getByLabel("Keeper label or name (optional)").fill("Pothos by the hide");
  await page.getByLabel("Quantity").fill("2");
  await page.getByLabel("Date added (optional)").fill("2026-09-14");
  await page.getByRole("button", { name: "Add plant" }).click();
  await page.waitForURL(/\/enclosures\/[0-9a-f-]+\/plants\/[0-9a-f-]+$/);
  const linkedPlantDetail = page.url();
  await expect(page.getByAltText(/Species reference image for/)).toBeVisible({ timeout: 12000 });
  await expect(page.getByText("Species reference", { exact: true })).toBeVisible();
  await capture("enclosure-plant-detail-with-reference-image");

  await page.goto(`${enclosureProfile}/plants/new`);
  const manualPlant = page.getByLabel("Plant species or name");
  await manualPlant.fill("zzzzqwertynotaplant");
  await expect(page.locator("[data-taxon-status]")).toContainText(/No matching|temporarily unavailable/, { timeout: 12000 });
  await capture("plant-manual-fallback");
  await manualPlant.fill("Unidentified fern");
  await page.getByRole("button", { name: "Add plant" }).click();
  await page.waitForURL(/\/enclosures\/[0-9a-f-]+\/plants\/[0-9a-f-]+$/);
  await expect(page.locator(".plant-placeholder")).toBeVisible();
  await expect(page.getByAltText(/Species reference image for/)).toHaveCount(0);
  await capture("enclosure-plant-detail-without-linked-image");
  await page.goto(enclosureProfile);
  await expect(page.getByText("Pothos by the hide", { exact: true })).toBeVisible();
  await expect(page.getByText("Unidentified fern", { exact: true }).first()).toBeVisible();
  await expect(page.locator(`a[href="${new URL(linkedPlantDetail).pathname}"] img`)).toBeVisible();
  await expect(page.locator(".plant-roster-media .plant-placeholder")).toBeVisible();
  await capture("enclosure-multiple-plants");

  await page.goto(`${origin}/directory?group=plant&q=${encodeURIComponent(eligiblePlant.scientific_name)}`);
  await expect(page.getByText(eligiblePlant.scientific_name, { exact: true }).first()).toBeVisible({ timeout: 12000 });
  await capture("plant-search");
  await capture("global-animal-plant-directory");
  await page.goto(`${origin}/directory/${eligiblePlant.taxon_id}`);
  await expect(page.getByAltText(/Species reference image for/)).toBeVisible({ timeout: 12000 });
  await expect(page.getByText(/Reference photo/)).toBeVisible();
  await capture("plant-directory-detail-with-reference-image");

  const plantWithoutImage = await page.evaluate(async () => {
    for (const query of ["sphagnum", "duckweed", "air plant", "prickly pear"]) {
      const response = await fetch(`/api/directory/search?group=plant&q=${encodeURIComponent(query)}`);
      const payload = await response.json();
      const record = payload.records?.find((candidate) => !candidate.reference_image_available);
      if (record) return record;
    }
    return null;
  });
  expect(plantWithoutImage).not.toBeNull();
  await page.goto(`${origin}/directory/${plantWithoutImage.taxon_id}`);
  await expect(page.locator(".directory-hero .plant-placeholder")).toBeVisible();
  await expect(page.getByAltText(/Species reference image for/)).toHaveCount(0);
  await capture("plant-directory-detail-without-reference-image");

  await page.goto(`${origin}/animals/new`);
  await page.getByLabel("Animal type").selectOption("spider");
  await page.getByLabel("Name").fill("Cache Upgrade");
  const upgradedSpecies = page.getByLabel("Species", { exact: true });
  await upgradedSpecies.fill("rose hair tarantula");
  await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 12000 });
  await capture("upgraded-service-worker-current-assets");

  await page.goto(`${origin}/directory?group=plant&q=zzzzqwertynotataxon`);
  await expect(page.getByRole("heading", { name: "No matching species" })).toBeVisible({ timeout: 12000 });
  await capture("no-results");

  fs.writeFileSync(
    path.join(evidence, "browser-qualification.partial.json"),
    JSON.stringify({ origin, cacheUpgrade, captures, scans, diagnostics, pageErrors, failedRequests, navigationArtifacts }, null, 2) + "\n"
  );
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  await browser.close();
});
