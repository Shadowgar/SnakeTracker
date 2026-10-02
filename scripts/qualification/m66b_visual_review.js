"use strict";

const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const manifest = JSON.parse(fs.readFileSync(process.env.M66B_MANIFEST, "utf8"));
const origin = process.env.M66B_ORIGIN || "http://127.0.0.1:8098";
const evidence = path.resolve(process.env.M66B_EVIDENCE || "/tmp/m66b-visual-review");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

async function main() {
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const captures = [];
  const ownerCaptures = [];
  const diagnostics = [];
  const routes = [
    ["species-directory-guide", `/directory/${manifest.taxon_ids["Python regius"]}`],
    ["animal-profile-entry", manifest.animal_url],
    ["animal-care-guide", `/directory/${manifest.taxon_ids["Python regius"]}/care-guide`],
    ["lizard-source-disagreement", `/directory/${manifest.taxon_ids["Pogona vitticeps"]}/care-guide`],
    ["plant-directory-guide", `/directory/${manifest.taxon_ids["Monstera deliciosa"]}`],
    ["plant-care-guide", `/directory/${manifest.taxon_ids["Monstera deliciosa"]}/care-guide`],
    ["enclosure-plant-guide", manifest.plant_url],
  ];
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1720, height: 900 }, { width: 390, height: 844 }]) {
      const label = viewport.width === 390 ? "mobile-390x844" : `desktop-${viewport.width}x900`;
      const context = await browser.newContext({ viewport, bypassCSP: true });
      const page = await context.newPage();
      page.on("pageerror", error => diagnostics.push({ viewport: label, type: "pageerror", message: error.message }));
      page.on("console", message => {
        if (message.type() === "error") diagnostics.push({ viewport: label, type: "console", message: message.text() });
      });
      await page.goto(`${origin}/login`, { waitUntil: "networkidle" });
      await page.locator('input[name="email"]').fill("guide-review@example.test");
      await page.locator('input[name="password"]').fill("fictional-guide-review-password");
      await page.locator('button[type="submit"]').click();
      await page.waitForURL(url => url.pathname !== "/login");
      for (const [name, route] of routes) {
        const started = performance.now();
        const response = await page.goto(`${origin}${route}`, { waitUntil: "networkidle" });
        const durationMs = +(performance.now() - started).toFixed(1);
        if (response.status() !== 200) throw new Error(`${label} ${name}: HTTP ${response.status()}`);
        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
        }));
        if (overflow.scrollWidth > overflow.viewportWidth + 1) {
          throw new Error(`${label} ${name}: horizontal overflow ${JSON.stringify(overflow)}`);
        }
        if (name === "species-directory-guide") {
          const hero = await page.locator(".directory-hero").boundingBox();
          const photo = await page.locator(".directory-hero-media img").boundingBox();
          if (!hero || !photo || (viewport.width > 1000 && (hero.width > 1200 || photo.width < 300 || photo.width / hero.width < .35))) {
            throw new Error(`${label}: taxon hero proportions invalid ${JSON.stringify({ hero, photo })}`);
          }
          if (!await page.locator(".directory-guide-entry a").isVisible()) throw new Error(`${label}: Care Guide entry hidden`);
        }
        if (name.endsWith("care-guide") || name === "lizard-source-disagreement") {
          const guide = await page.locator(".care-guide-page").boundingBox();
          const valueFont = await page.locator(".guide-value, .guide-position strong").first().evaluate(el => parseFloat(getComputedStyle(el).fontSize));
          const disclosureHeight = await page.locator(".guide-disclosure summary").first().evaluate(el => el.getBoundingClientRect().height);
          if (!guide || (viewport.width > 1000 && guide.width > 1140) || valueFont < 19 || disclosureHeight < 44) {
            throw new Error(`${label} ${name}: guide reading metrics invalid ${JSON.stringify({ guide, valueFont, disclosureHeight })}`);
          }
          const glance = page.locator(".guide-glance-item").first();
          if (await glance.count()) {
            const anchor = await glance.getAttribute("href");
            if (!anchor || !await page.locator(anchor).count()) throw new Error(`${label}: glance link missing target`);
          }
          await page.locator(".guide-disclosure summary").first().focus();
          await page.keyboard.press("Enter");
          if (!await page.locator(".guide-disclosure[open] a").first().isVisible()) throw new Error(`${label}: source disclosure not usable`);
        }
        await page.addScriptTag({ path: axePath });
        const axe = await page.evaluate(async () => {
          const result = await window.axe.run(document);
          return result.violations.map(item => ({ id: item.id, impact: item.impact, nodes: item.nodes.length }));
        });
        if (axe.length) throw new Error(`${label} ${name}: axe ${JSON.stringify(axe)}`);
        if (name === "lizard-source-disagreement") {
          const text = await page.locator("main").innerText();
          for (const expected of ["Sources differ", "35–40°C", "38–42°C", "Corroborated"]) {
            if (!text.includes(expected)) throw new Error(`${label}: missing ${expected}`);
          }
          if (await page.locator(".guide-state-differ").count() !== 1 || await page.locator(".guide-state-corroborated").count() !== 1 || await page.locator(".guide-state-differ + .guide-positions .guide-position").count() !== 2) {
            throw new Error(`${label}: distinct source positions or support badges missing`);
          }
        }
        if (name === "plant-care-guide") {
          const text = await page.locator("main").innerText();
          if (!text.includes("Cats and dogs only") || !text.includes("not established")) {
            throw new Error(`${label}: plant suitability scope missing`);
          }
          if (!await page.locator(".guide-scope").isVisible()) throw new Error(`${label}: plant suitability boundary missing`);
        }
        await page.evaluate(() => {
          if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
          window.scrollTo(0, 0);
        });
        await page.mouse.move(0, 0);
        const filename = `${label}-${name}.png`;
        const screenshot = path.join(evidence, "screenshots", filename);
        fs.mkdirSync(path.dirname(screenshot), { recursive: true });
        await page.screenshot({ path: screenshot, fullPage: true });
        captures.push({ viewport: label, name, route, durationMs, overflow, axeViolations: 0, screenshot: `screenshots/${filename}` });
        if (viewport.width === 390 && ["animal-care-guide", "lizard-source-disagreement", "plant-care-guide"].includes(name)) {
          const overviewName = `${label}-${name}-viewport.png`;
          await page.screenshot({ path: path.join(evidence, "screenshots", overviewName) });
          ownerCaptures.push(`screenshots/${overviewName}`);
          if (name === "lizard-source-disagreement") {
            await page.locator(".guide-positions").first().scrollIntoViewIfNeeded();
            const positionsName = `${label}-${name}-positions.png`;
            await page.screenshot({ path: path.join(evidence, "screenshots", positionsName) });
            ownerCaptures.push(`screenshots/${positionsName}`);
          }
          if (name === "plant-care-guide") {
            await page.locator(".guide-fact").filter({ hasText: "Cat/dog toxicity" }).first().scrollIntoViewIfNeeded();
            const scopeName = `${label}-${name}-toxicity.png`;
            await page.screenshot({ path: path.join(evidence, "screenshots", scopeName) });
            ownerCaptures.push(`screenshots/${scopeName}`);
          }
        }
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  const result = { fictionalHouseholdAndPublicReferenceOnly: true, captures, ownerCaptures, diagnostics };
  fs.mkdirSync(evidence, { recursive: true });
  fs.writeFileSync(path.join(evidence, "browser-qualification.json"), JSON.stringify(result, null, 2));
  if (diagnostics.length) throw new Error(`Browser console errors: ${JSON.stringify(diagnostics)}`);
  console.log(JSON.stringify({ captures: captures.length, consoleErrors: diagnostics.length }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
