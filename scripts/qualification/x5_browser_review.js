"use strict";
// Real Chromium, unchanged application CSP and local-only disposable fixture requests.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium } = require(process.env.X5_PLAYWRIGHT || "playwright");
const fixture = fs.realpathSync(process.env.X5_FIXTURE);
assert.match(fixture, /^\/tmp\/carekeeper-x5-browser-[^/]+$/);
const manifest = JSON.parse(fs.readFileSync(path.join(fixture, "manifest.json"), "utf8"));
assert.equal(manifest.fictional, true);
const output = path.join(fixture, "evidence");
fs.mkdirSync(output, { recursive: true });
const report = { viewports: [], externalRequests: [], errors: [], screenshots: [] };
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    await context.route("**/*", async route => {
      const url = route.request().url();
      if (!url.startsWith(manifest.origin + "/")) {
        report.externalRequests.push(url); return route.abort();
      }
      if (url.endsWith("/static/x5-axe.js")) return route.fulfill({
        contentType: "application/javascript", body: fs.readFileSync(process.env.X5_AXE, "utf8")
      });
      return route.continue();
    });
    const page = await context.newPage();
    page.on("pageerror", error => report.errors.push(String(error)));
    await page.goto(manifest.origin + "/login");
    await page.locator('input[name="email"]').fill("owner@example.com");
    await page.locator('input[name="password"]').fill("correct horse battery staple");
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/home$/);
    for (const [width, height] of [[390,844],[320,844],[1440,900]]) {
      await page.setViewportSize({width, height});
      for (const [species, route] of Object.entries(manifest.paths)) {
        const prefix = `${species.split(" ")[0].toLowerCase()}-${width}x${height}`;
        await page.goto(manifest.origin + route + "/reference");
        await page.locator("#reviewed-care-title").waitFor();
        const noGuide = species === "Rana temporaria";
        assert(await page.getByRole("heading", {name:"Species Overview / Natural History"}).isVisible());
        if (noGuide) assert(await page.getByText("No reviewed captive-care guide is available yet.", {exact:true}).isVisible());
        else assert(await page.locator(".profile-reference-cautions").isVisible());
        const snap = async name => {
          const file = `${prefix}-${name}.png`;
          await page.screenshot({path:path.join(output,file), fullPage:name !== "care-summary"});
          report.screenshots.push(file);
        };
        await snap("full-page");
        if (!noGuide) {
          await page.locator("#reviewed-care-title").evaluate(el => el.scrollIntoView({behavior:"instant",block:"start"}));
          await page.waitForFunction(() => {
            const top = document.querySelector("#reviewed-care-title").getBoundingClientRect().top;
            return top >= 0 && top < 150;
          });
          await snap("care-summary");
          // Exercise native disclosure keyboard behavior before expanding the rest.
          const first = page.locator(".profile-reference-sections > details").first();
          await first.locator("summary").first().focus();
          await page.keyboard.press("Enter");
          assert(await first.evaluate(el => el.open));
          await page.keyboard.press("Space");
          assert(!(await first.evaluate(el => el.open)));
          for (const summary of await page.locator(".profile-reference-sections > details > summary").all()) await summary.click();
          for (const summary of await page.locator(".profile-reference-sections .guide-disclosure > summary").all()) await summary.click();
          await page.locator(".profile-reference-sources > summary").click();
          assert(await page.locator(".profile-reference-bibliography").isVisible());
          assert((await page.locator(".profile-reference-bibliography").innerText()).includes("2026-11-02"));
          await snap("expanded-sources");
        }
        await page.addScriptTag({url:manifest.origin + "/static/x5-axe.js"});
        const accessibility = await page.evaluate(async () => await axe.run(document.querySelector("main"), {
          runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa"]}
        }));
        const widthInfo = await page.evaluate(() => ({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));
        report.viewports.push({species,width,height,widthInfo,keyboard:!noGuide,
          violations:accessibility.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))});
        assert(widthInfo.scroll <= widthInfo.viewport, JSON.stringify(widthInfo));
        assert.equal(accessibility.violations.length,0,JSON.stringify(report.viewports.at(-1)));
        await page.getByRole("link",{name:"Overview",exact:true}).click();
        await page.waitForURL(manifest.origin + route);
        await page.getByRole("link",{name:"Guides & Species Reference",exact:true}).click();
        await page.waitForURL(manifest.origin + route + "/reference");
      }
    }
    assert.deepEqual(report.externalRequests,[]);
    assert.deepEqual(report.errors,[]);
    report.status="passed";
  } finally {
    fs.writeFileSync(path.join(output,"browser-results.json"),JSON.stringify(report,null,2)+"\n");
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
