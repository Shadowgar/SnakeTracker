const { test, expect, chromium } = require("playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const origin = process.env.M66A_ORIGIN || "http://127.0.0.1:8096";
const evidence = path.resolve(
  "docs/evidence/m6.6-species-aware-husbandry/a-universal-directory"
);
const screenshots = path.join(evidence, "screenshots");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

const coverageTargets = [
  ["snake", "ball python", "Python regius", "Ball Python"],
  ["snake", "boa constrictor", "Boa constrictor", "Boa Constrictor"],
  ["snake", "corn snake", "Pantherophis guttatus", "Corn Snake"],
  ["snake", "eastern kingsnake", "Lampropeltis getula", "Kingsnake"],
  ["lizard", "leopard gecko", "Eublepharis macularius", "Leopard Gecko"],
  ["lizard", "crested gecko", "Correlophus ciliatus", "Crested Gecko"],
  ["lizard", "bearded dragon", "Pogona vitticeps", "Bearded Dragon"],
  ["spider", "bold jumping spider", "Phidippus audax", "Bold Jumping Spider"],
  ["spider", "rose hair tarantula", "Grammostola rosea", "Tarantula"],
  ["scorpion", "emperor scorpion", "Pandinus imperator", "Emperor Scorpion"],
];

test("M6.6-A owner visual fidelity and reference image coverage", async () => {
  test.setTimeout(300_000);
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
  const lazyImageNavigationAborts = [];
  const scans = [];
  const captures = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleDiagnostics.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    if (
      request.resourceType() === "image" &&
      request.failure()?.errorText === "net::ERR_ABORTED"
    ) {
      lazyImageNavigationAborts.push(`${request.method()} ${request.url()}`);
      return;
    }
    if (
      new URL(request.url()).pathname === "/static/favicon.svg" &&
      request.failure()?.errorText === "net::ERR_ABORTED"
    ) return;
    requestFailures.push(
      `${request.method()} ${request.url()} · ${request.failure()?.errorText || "unknown"}`
    );
  });

  await page.goto(`${origin}/login`);
  await page.locator('[name="email"]').fill("demo@carekeeper.local");
  await page.locator('[name="password"]').fill("carekeeper-demo-local-only");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(`${origin}/home`);

  const coverage = [];
  for (const [group, query, scientificName, label] of coverageTargets) {
    const item = await page.evaluate(async ({ group, query, scientificName, label }) => {
      const search = await fetch(
        `/api/directory/search?group=${encodeURIComponent(group)}&q=${encodeURIComponent(query)}`
      );
      const payload = await search.json();
      const record = payload.records?.find(
        (candidate) => candidate.scientific_name === scientificName
      );
      if (!record) return { label, scientificName, error: "taxon-not-found" };
      const metadataResponse = await fetch(`/api/directory/${record.taxon_id}/reference-image`);
      const metadata = await metadataResponse.json();
      let mediaType = null;
      let byteCount = 0;
      if (metadata.available) {
        const image = await fetch(metadata.url);
        mediaType = image.headers.get("content-type");
        byteCount = (await image.arrayBuffer()).byteLength;
      }
      return {
        label,
        scientificName,
        taxonId: record.taxon_id,
        searchState: payload.state,
        mediaType,
        byteCount,
        ...metadata,
      };
    }, { group, query, scientificName, label });
    expect(item.error).toBeUndefined();
    expect(item.available).toBe(true);
    expect(item.mediaType).toBe("image/webp");
    expect(item.byteCount).toBeGreaterThan(0);
    coverage.push(item);
  }

  const boaCoverage = coverage.find((item) => item.scientificName === "Boa constrictor");
  expect(boaCoverage.provider).toBe("inaturalist");
  expect(boaCoverage.provider_record_id).toBe("588689904");
  expect(boaCoverage.license_code).toBe("cc-by-nc");

  await page.goto(`${origin}/animals`);
  const existingReferenceAnimal = page.locator("a.animal-card", {
    hasText: "Boa Reference Review",
  }).first();
  let referenceProfile;
  if (await existingReferenceAnimal.count()) {
    referenceProfile = new URL(await existingReferenceAnimal.getAttribute("href"), origin).href;
    await page.goto(referenceProfile);
  } else {
    await page.goto(`${origin}/animals/new`);
    await page.getByLabel("Animal type").selectOption("snake");
    await page.getByLabel("Name").fill("Boa Reference Review");
    const species = page.getByLabel("Species", { exact: true });
    await species.fill("boa constrictor");
    await expect(page.locator('[role="option"]').filter({ hasText: "Boa constrictor" }).first())
      .toBeVisible({ timeout: 15_000 });
    await page.locator('[role="option"]').filter({ hasText: "Boa constrictor" }).first().click();
    await expect(page.locator('[name="taxon_id"]')).not.toHaveValue("");
    await expect(page.locator("[data-reference-photo-image]")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("[data-reference-photo-copy]")).toContainText("Species reference image available");
    await page.getByRole("button", { name: "Create animal" }).click();
    await page.waitForURL(/\/animals\/[0-9a-f-]+$/);
    referenceProfile = page.url();
  }
  await expect(page.locator('.animal-hero-photo[src*="/directory/reference-images/"]'))
    .toBeVisible();
  await expect(page.locator(".reference-attribution")).toContainText("CC BY-NC");
  await expect(page.locator(".reference-attribution")).toContainText("iNaturalist");

  async function capture(viewport, label, route) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const response = await page.goto(route.startsWith("http") ? route : `${origin}${route}`);
    expect(response.status()).toBe(200);
    await page.waitForLoadState("networkidle");
    await page.evaluate(async () => {
      const visibleImages = [...document.images].filter((candidate) => {
        const bounds = candidate.getBoundingClientRect();
        return candidate.currentSrc && bounds.bottom >= 0 && bounds.top <= window.innerHeight;
      });
      await Promise.all(visibleImages.map((candidate) => {
        if (candidate.complete) return Promise.resolve();
        return new Promise((resolve) => {
          candidate.addEventListener("load", resolve, { once: true });
          candidate.addEventListener("error", resolve, { once: true });
        });
      }));
    });
    const csp = response.headers()["content-security-policy"] || "";
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("img-src 'self'");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflow).toBe(false);
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
      }));
    });
    expect(violations).toEqual([]);
    const prefix = `${viewport.name}-${label}`;
    await page.screenshot({ path: path.join(screenshots, `${prefix}.png`), fullPage: false });
    scans.push({ label, viewport: `${viewport.width}x${viewport.height}`, violations });
    captures.push({ label, viewport: `${viewport.width}x${viewport.height}`, overflow, csp });
  }

  const mobile = { width: 390, height: 844, name: "mobile-390x844" };
  const desktop = { width: 1440, height: 900, name: "desktop-1440x900" };
  for (const [label, route] of [
    ["today", "/home"],
    ["animals", "/animals"],
    ["animal-profile-reference", referenceProfile],
    ["calendar", "/calendar"],
    ["quick-log", "/quick-log"],
    ["enclosures", "/enclosures"],
  ]) await capture(mobile, label, route);
  for (const [label, route] of [
    ["today", "/home"],
    ["animals", "/animals"],
    ["animal-profile-reference", referenceProfile],
    ["enclosures", "/enclosures"],
  ]) await capture(desktop, label, route);

  const result = {
    origin,
    coverage,
    captures,
    accessibilityScans: scans,
    consoleDiagnostics,
    pageErrors,
    requestFailures,
    lazyImageNavigationAborts,
  };
  fs.writeFileSync(
    path.join(evidence, "owner-fidelity-qualification.json"),
    JSON.stringify(result, null, 2) + "\n"
  );
  expect(pageErrors).toEqual([]);
  expect(requestFailures).toEqual([]);
  expect(consoleDiagnostics).toEqual([]);
  await browser.close();
});
