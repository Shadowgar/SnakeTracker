"use strict";

const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const manifest = JSON.parse(fs.readFileSync(process.env.M66B_MANIFEST, "utf8"));
const origin = process.env.M66B_ORIGIN || "http://127.0.0.1:8098";
const evidence = path.resolve(process.env.M66B_EVIDENCE || "/tmp/m66b-profile-reference-review");
const axePath = "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";

async function main() {
  const browser = await chromium.launch({
    executablePath: "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    headless: true,
  });
  const captures = [];
  const diagnostics = [];
  const routes = [
    ["animal-with-guide", manifest.animal_urls.with_guide],
    ["animal-disagreement", manifest.animal_urls.disagreement],
    ["animal-linked-no-guide", manifest.animal_urls.linked_without_guide],
    ["animal-unlinked", manifest.animal_urls.unlinked],
    ["species-directory", "/directory"],
    ["full-care-guide", `/directory/${manifest.taxon_ids["Python regius"]}/care-guide`],
  ];
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      const label = viewport.width === 1440 ? "desktop-1440x900" : "mobile-390x844";
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
        const response = await page.goto(`${origin}${route}`, { waitUntil: "networkidle" });
        if (response.status() !== 200) throw new Error(`${label} ${name}: HTTP ${response.status()}`);
        const overflow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth }));
        if (overflow.scrollWidth > overflow.viewportWidth + 1) throw new Error(`${label} ${name}: horizontal overflow`);
        if (name.startsWith("animal-")) {
          const reference = page.locator(".overview-reference");
          if (!await reference.isVisible()) throw new Error(`${label} ${name}: reference card hidden`);
          if (!await page.locator(".overview-identity .page-kicker").getByText("Your records").isVisible()) throw new Error(`${label} ${name}: personal record boundary hidden`);
          const metrics = await page.evaluate(() => {
            const rect = selector => document.querySelector(selector).getBoundingClientRect();
            return { reference: rect(".overview-reference").toJSON(), recent: rect(".overview-recent").toJSON(), care: rect(".overview-care").toJSON() };
          });
          if (viewport.width === 1440 && (Math.abs(metrics.reference.x - metrics.recent.x) > 2 || metrics.reference.y < metrics.recent.bottom || metrics.reference.y - metrics.recent.bottom > 24)) {
            throw new Error(`${label} ${name}: reference not under Recent History ${JSON.stringify(metrics)}`);
          }
          if (viewport.width === 390 && metrics.reference.y < metrics.care.bottom) throw new Error(`${label} ${name}: reference precedes personal care snapshot`);
          const summary = await reference.innerText();
          if (name === "animal-with-guide") {
            for (const expected of ["Reviewed reference guidance", "30–32°C · 86–90°F", "Single source", "View full Care Guide"]) {
              if (!summary.includes(expected)) throw new Error(`${label}: missing profile fact ${expected}`);
            }
            const link = await reference.locator("a").getAttribute("href");
            if (link !== `/directory/${manifest.taxon_ids["Python regius"]}/care-guide`) throw new Error(`${label}: wrong guide target`);
          }
          if (name === "animal-disagreement") {
            if (!summary.includes("Sources differ") || !await reference.locator(".guide-state-differ").count()) throw new Error(`${label}: disagreement state absent`);
            if (summary.includes("35–40°C") || summary.includes("38–42°C")) throw new Error(`${label}: chose one publisher's range`);
          }
          if (name === "animal-linked-no-guide" && (!summary.includes("No reviewed species guidance available yet.") || await reference.locator(".profile-reference-fact").count())) throw new Error(`${label}: no-guide state wrong`);
          if (name === "animal-unlinked" && (!summary.includes("Link a species to see reviewed guidance.") || !summary.includes("Find species reference") || summary.includes("30–32°C"))) throw new Error(`${label}: unlinked state inferred free-text species`);
        }
        if (name === "species-directory" && !await page.locator("main input").count()) throw new Error(`${label}: Directory search missing`);
        await page.addScriptTag({ path: axePath });
        const violations = await page.evaluate(async () => (await window.axe.run(document)).violations.map(v => ({ id: v.id, nodes: v.nodes.length })));
        if (violations.length) throw new Error(`${label} ${name}: axe ${JSON.stringify(violations)}`);
        await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0); });
        await page.mouse.move(0, 0);
        const filename = `${label}-${name}.png`;
        fs.mkdirSync(path.join(evidence, "screenshots"), { recursive: true });
        await page.screenshot({ path: path.join(evidence, "screenshots", filename), fullPage: true });
        captures.push({ viewport: label, name, route, screenshot: `screenshots/${filename}`, axeViolations: 0, overflow: false });
        if (viewport.width === 390 && ["animal-with-guide", "animal-unlinked"].includes(name)) {
          await page.evaluate(() => {
            const reference = document.querySelector(".overview-reference");
            window.scrollTo(0, reference.getBoundingClientRect().top + window.scrollY - 8);
          });
          const focusName = `${label}-${name}-reference.png`;
          await page.screenshot({ path: path.join(evidence, "screenshots", focusName) });
          captures.push({ viewport: label, name: `${name}-reference`, route, screenshot: `screenshots/${focusName}`, axeViolations: 0, overflow: false });
        }
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  fs.mkdirSync(evidence, { recursive: true });
  fs.writeFileSync(path.join(evidence, "browser-qualification.json"), JSON.stringify({ fictionalHouseholdAndPublicReferenceOnly: true, captures, diagnostics }, null, 2));
  if (diagnostics.length) throw new Error(`Browser console errors: ${JSON.stringify(diagnostics)}`);
  console.log(JSON.stringify({ captures: captures.length, consoleErrors: diagnostics.length }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
