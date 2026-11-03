"use strict";
// Isolated Chromium journey against the fictional X5 fixture, using only local requests.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium } = require(process.env.CARE_PLAYWRIGHT || "playwright");
const fixture = fs.realpathSync(process.env.CARE_FIXTURE);
assert.match(fixture, /^\/tmp\/carekeeper-x5-browser-[^/]+$/);
const manifest = JSON.parse(fs.readFileSync(path.join(fixture, "manifest.json"), "utf8"));
assert.equal(manifest.fictional, true);
assert.match(manifest.origin, /^http:\/\/127\.0\.0\.1:81\d\d$/);
const output = path.join(fixture, "smart-care-evidence");
fs.mkdirSync(output, {recursive:true});
const report = {screenshots:[], checks:[], externalRequests:[], errors:[]};
const localTime = offset => new Date(Date.now()+offset).toISOString().slice(0,16);
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext({viewport:{width:390,height:844},timezoneId:"UTC"});
    await context.route("**/*", async route => {
      const url = route.request().url();
      if (!url.startsWith(manifest.origin+"/")) {
        report.externalRequests.push(url); return route.abort();
      }
      if (url.endsWith("/static/care-axe.js")) return route.fulfill({
        contentType:"application/javascript", body:fs.readFileSync(process.env.CARE_AXE,"utf8")
      });
      return route.continue();
    });
    const page = await context.newPage();
    page.on("pageerror", error => report.errors.push(String(error)));
    const go = route => page.goto(manifest.origin+route);
    const capture = async name => {
      await page.addScriptTag({url:manifest.origin+"/static/care-axe.js"});
      const a11y = await page.evaluate(async()=>await axe.run(document.querySelector("main"), {
        runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa"]}
      }));
      const width = await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));
      report.checks.push({name,url:page.url(),width,violations:a11y.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))});
      assert(width.scroll<=width.viewport,JSON.stringify(width));
      assert.equal(a11y.violations.length,0,JSON.stringify(report.checks.at(-1)));
      await page.evaluate(() => document.activeElement?.blur());
      await page.mouse.move(0,0);
      await page.screenshot({path:path.join(output,name+".png"),fullPage:true});
      report.screenshots.push(name+".png");
    };
    await go("/login");
    await page.locator('[name="email"]').fill("owner@example.com");
    await page.locator('[name="password"]').fill("correct horse battery staple");
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/\/home$/);
    // Fixture preparation uses the existing household command, with explicit fictional stock.
    await go("/inventory");
    if (!(await page.locator("main").innerText()).includes("Fixture crickets")) {
    await go("/inventory/new");
    const stock = await context.request.post(manifest.origin+"/inventory", {form:{
      csrf_token:await page.locator('main [name="csrf_token"]').inputValue(),
      idempotency_key:"smart-care-browser-crickets", inventory_type:"food", name:"Fixture crickets",
      food_category:"insect", food_type:"cricket", size_stage:"small", preparation_method:"live",
      unit_code:"each", starting_quantity:"20", reorder_threshold:"1"
    }});
    assert(stock.ok(),await stock.text());
    }
    const animal = manifest.paths["Pelodryas caerulea"];
    await go(animal+"/care");
    await page.getByRole("link",{name:/smart care setup/i}).click();
    await page.waitForURL(manifest.origin+animal+"/smart-care");
    assert((await page.locator("main").innerText()).includes("Juvenile"));
    assert((await page.locator("main").innerText()).includes("Adult"));
    assert.match(await page.locator("main").innerText(),/sources differ/i);
    await capture("setup-390");
    await page.locator('a[href*="choice=rvc-white-2024-feeding_interval-juvenile"]').click();
    await page.locator('[name="interval_days"]').fill("1");
    await page.locator('[name="first_due_at"]').fill(localTime(-3600000));
    await page.locator('[name="applicability"]').check();
    await capture("edit-390");
    await page.locator('form[action$="/preview"] button[type="submit"]').click();
    await page.locator('[name="preview_token"]').waitFor({state:"attached"});
    await capture("confirm-390");
    await page.locator('form[action$="/confirm"] button[type="submit"]').click();
    await page.waitForURL(manifest.origin+animal+"/care");
    assert((await page.locator(".care-schedule-list").innerText()).includes("Every 1 day"));
    for (const route of ["/home","/calendar?view=agenda","/reminders"]) {
      await go(route); assert((await page.locator("main").innerText()).includes("Moss"),route);
    }
    await go(animal+"/feedings/new?return_to=care");
    const food = await page.locator('[name="inventory_item_id"] option').allTextContents();
    const foodIndex = food.findIndex(v=>v.includes("Fixture crickets"));
    assert(foodIndex>0);
    await page.locator('[name="inventory_item_id"]').selectOption({index:foodIndex});
    await page.locator('[name="inventory_quantity"]').fill("2");
    await page.locator('[name="outcome"]').selectOption("accepted");
    await page.locator('[name="occurred_at"]').fill(localTime(-60000));
    await page.locator('form[action$="/feedings"] button[type="submit"]').click();
    await page.waitForURL(manifest.origin+animal+"/care");
    const feedingRow=page.locator(".schedule-row").filter({has:page.getByRole("heading",{name:"Feeding",exact:true})});
    assert.match(await feedingRow.innerText(),/Tomorrow|tomorrow|in 1 day/i);
    await capture("care-after-feeding-390");
    await go("/home");
    assert((await page.locator('section[aria-labelledby="home-upcoming"]').innerText()).includes("Moss"));
    report.checks.push({name:"confirmed-feeding-completes-and-advances",status:"passed"});
    await page.setViewportSize({width:1440,height:900});
    await go(animal+"/smart-care");
    await capture("setup-1440");
    await page.setViewportSize({width:320,height:844});
    await go(manifest.paths["Rana temporaria"]+"/smart-care");
    assert(await page.locator('a[href*="choice=manual"]').count()>0);
    await capture("manual-fallback-320");
    assert.deepEqual(report.externalRequests,[]);
    assert.deepEqual(report.errors,[]);
    report.status="passed";
  } finally {
    fs.writeFileSync(path.join(output,"browser-results.json"),JSON.stringify(report,null,2)+"\n");
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
