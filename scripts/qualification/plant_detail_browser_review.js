"use strict";
// Real rendered geometry regression; the server is a synthetic loopback fixture.
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path");
const { chromium } = require(process.env.CARE_PLAYWRIGHT || "playwright");
const origin = process.env.CARE_PLANT_ORIGIN || "http://127.0.0.1:8193";
assert.match(origin, /^http:\/\/127\.0\.0\.1:81\d\d$/);
const output = path.resolve(process.env.CARE_OUTPUT || "output/plant-detail-layout");
fs.mkdirSync(output, { recursive: true });
const report = { sourceRevision: process.env.CARE_SOURCE_REVISION || "working-tree", checks: [], failures: [], externalRequests: [], pageErrors: [] };
const check = (condition, message) => { if (!condition) report.failures.push(message); };
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ serviceWorkers: "block" });
    await context.route("**/*", route => {
      if (!route.request().url().startsWith(origin + "/")) {
        report.externalRequests.push(route.request().url()); return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on("pageerror", error => report.pageErrors.push(String(error)));
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      for (const variant of ["reference", "long-name", "missing-image"]) {
        await page.goto(origin + "/plant/" + variant);
        const img = page.locator(".plant-profile-identity img");
        if (await img.count()) await img.evaluate(image => image.decode());
        const geometry = await page.evaluate(() => {
          const box = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, bottom: rect.bottom };
          };
          const image = document.querySelector(".plant-profile-identity img");
          return {
            viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
            image: box(".plant-profile-identity img"), header: box(".plant-profile-identity"),
            title: box("#page-title"), details: box(".detail-list"), watering: box("#history"),
            schedule: box('a[href*="/care-schedule/plant_watering"]'),
            naturalImage: image ? { width: image.naturalWidth, height: image.naturalHeight } : null,
            imageStyle: image ? { height: getComputedStyle(image).height, objectFit: getComputedStyle(image).objectFit } : null,
          };
        });
        const name = variant + "-" + width;
        check(geometry.scrollWidth <= width, name + ": horizontal overflow");
        if (geometry.image) {
          // A narrow thumbnail must never retain the markup's 800px height.
          check(geometry.image.height <= 240, name + ": photo exceeds 240px height");
          check(geometry.image.width >= 80, name + ": photo squeezed below 80px");
          check(geometry.image.height < geometry.image.width * 3, name + ": thumbnail became a vertical strip");
          check(Math.abs(geometry.image.width / geometry.image.height - geometry.naturalImage.width / geometry.naturalImage.height) < 0.04, name + ": natural image proportions changed");
          check(["contain", "cover"].includes(geometry.imageStyle.objectFit), name + ": image may distort");
          check(await page.locator(".reference-attribution a").count() === 2, name + ": attribution links missing");
        } else {
          check(await page.locator(".plant-profile-identity .plant-placeholder").count() === 1, name + ": image fallback missing");
        }
        check(geometry.title.y - geometry.header.y < 40, name + ": title pushed down header");
        if (variant !== "long-name") {
          check(geometry.header.height <= 320, name + ": header exceeds 320px");
          check(geometry.details.y < 430, name + ": plant details pushed down");
          check(geometry.watering.y <= 600, name + ": watering section requires excessive scrolling");
          check(geometry.schedule.bottom <= 920, name + ": watering schedule control pushed down");
        }
        for (const label of ["Set watering schedule", "Edit plant", "Remove plant", "Review, correct or void watering history"]) {
          check(await page.getByRole("link", { name: label, exact: true }).count() === 1, name + ": missing " + label);
        }
        check(await page.getByRole("button", { name: "Save watering", exact: true }).count() === 1, name + ": watering control missing");
        check((await page.locator("main").innerText()).includes("Substrate checked and watered."), name + ": history missing");
        await page.addScriptTag({ content: fs.readFileSync(process.env.CARE_AXE, "utf8") });
        const accessibility = await page.evaluate(async () => (await axe.run(document.querySelector("main"), {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        })).violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })));
        check(accessibility.length === 0, name + ": accessibility violations " + JSON.stringify(accessibility));
        await page.screenshot({ path: path.join(output, name + ".png"), fullPage: true });
        await page.getByRole("link", { name: "Watering & history", exact: true }).click();
        await page.waitForFunction(() => {
          const target = document.querySelector("#history").getBoundingClientRect();
          return location.hash === "#history" && target.top >= -1 && target.top < 200;
        });
        const anchor = await page.locator("#history").evaluate(element => {
          const section = element.getBoundingClientRect(), heading = element.querySelector("h2").getBoundingClientRect();
          return { hash: location.hash, sectionTop: section.top, headingBottom: heading.bottom, viewportHeight: innerHeight };
        });
        check(anchor.headingBottom < anchor.viewportHeight, name + ": watering anchor did not expose heading");
        report.checks.push({ name, geometry, accessibility, anchor, screenshot: name + ".png" });
      }
    }
    check(report.externalRequests.length === 0, "Unexpected external network requests");
    check(report.pageErrors.length === 0, "Page errors: " + report.pageErrors.join("; "));
    report.status = report.failures.length ? "failed" : "passed";
  } finally {
    fs.writeFileSync(path.join(output, "browser-results.json"), JSON.stringify(report, null, 2) + "\n");
    await browser.close();
  }
  console.log(JSON.stringify({ status: report.status, checks: report.checks.length, failures: report.failures }, null, 2));
  assert.equal(report.failures.length, 0, "Plant Detail rendered layout regression");
})().catch(error => { console.error(error.message); process.exitCode = 1; });
