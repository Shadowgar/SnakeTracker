"use strict";
// Real form round trips for a precision bug: Chromium rejects six-digit fractions.
const fs = require("node:fs"), path = require("node:path"), assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const {chromium} = require(process.env.CARE_PLAYWRIGHT || "playwright");
const fixture = fs.realpathSync(process.env.CARE_FIXTURE);
assert.match(fixture, /^\/tmp\/carekeeper-x5-browser-[^/]+$/);
const manifest = JSON.parse(fs.readFileSync(path.join(fixture,"manifest.json"),"utf8"));
assert.equal(manifest.fictional,true);assert.match(manifest.origin,/^http:\/\/127\.0\.0\.1:81\d\d$/);
assert.equal(fs.realpathSync(manifest.database),path.join(fixture,"review.sqlite3"));
const report={sourceRevision:process.env.CARE_SOURCE_REVISION||"working-tree",checks:[],externalRequests:[],errors:[]};
const output=path.join(fixture,"care-precision-results.json");
const exact="2026-11-01T12:00:37.123456+00:00", displayed="2026-11-01T12:00:37.123";
const readSql=(sql,args=[])=>JSON.parse(execFileSync("python3",["-c",
 'import json,sqlite3,sys; c=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); print(json.dumps(c.execute(sys.argv[2],json.loads(sys.argv[3])).fetchall()))',
 manifest.database,sql,JSON.stringify(args)],{encoding:"utf8"}));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},timezoneId:"UTC",serviceWorkers:"block"});
  await context.route("**/*",route=>{const url=route.request().url();if(!url.startsWith(manifest.origin+"/")){report.externalRequests.push(url);return route.abort();}return route.continue();});
  const page=await context.newPage();page.on("pageerror",e=>report.errors.push(String(e)));
  const go=p=>page.goto(manifest.origin+p);
  const csrf=()=>page.locator('main [name="csrf_token"]').first().inputValue();
  const post=async(url,form)=>{const response=await context.request.post(manifest.origin+url,{form:{csrf_token:await csrf(),...form}});assert(response.ok(),await response.text());return response;};
  const validField=async(selector)=>{
   const field=page.locator(selector);assert.equal(await field.inputValue(),displayed);
   assert(await field.evaluate(e=>e.checkValidity()));
  };
  await go("/login");await page.locator('[name="email"]').fill("owner@example.com");await page.locator('[name="password"]').fill("correct horse battery staple");await page.locator('button[type="submit"]').click();await page.waitForURL(/\/home$/);
  // Seed an exact existing override through the authenticated preview and confirmation route.
  const animal=manifest.paths["Pelodryas caerulea"], edit=animal+"/smart-care/feeding/edit?choice=manual";
  await go(edit);
  let response=await post(animal+"/smart-care/feeding/preview",{choice:"manual",interval_days:"2",first_due_at:exact,edit_token:await page.locator('[name="edit_token"]').inputValue()});
  let html=await response.text();let token=html.match(/name="preview_token" value="([^"]+)"/)[1];
  await post(animal+"/smart-care/confirm",{preview_token:token});
  await go(edit);await validField('[name="first_due_at"]');
  await page.locator('[name="interval_days"]').fill("3");await page.locator('form[action$="/preview"] button').click();await page.locator('[name="preview_token"]').waitFor({state:"attached"});
  assert((await page.locator("main").innerText()).includes("12:00:37.123456"));
  await page.getByRole("link",{name:"Edit again",exact:true}).click();await validField('[name="first_due_at"]');
  await page.locator('form[action$="/preview"] button').click();await page.locator('[name="preview_token"]').waitFor({state:"attached"});await page.locator('form[action$="/confirm"] button').click();await page.waitForURL(manifest.origin+animal+"/care");
  assert.equal(readSql("SELECT override_due_at FROM reminder_rule_current WHERE subject_id=? AND reminder_type='feeding'",[animal.split('/').at(-1)])[0][0],exact);
  report.checks.push({name:"smart-care-actual-input-and-edit-again-preserve-microseconds",status:"passed"});
  // Create a separate fictional plant so prior qualification history remains intact.
  await go("/enclosures/new");await page.locator('[name="name"]').fill("Precision habitat");await page.locator('[name="enclosure_type_choice"]').selectOption({index:1});await page.getByRole("button",{name:"Create enclosure",exact:true}).click();await page.waitForURL(/\/enclosures\/[0-9a-f-]+$/);
  const enclosure=new URL(page.url()).pathname;
  await go(enclosure+"/plants/new");await page.locator('[name="manual_species"]').fill("Keeper plant without guidance");await page.locator('[name="label"]').fill("Precision plant");await page.getByRole("button",{name:"Add plant",exact:true}).click();await page.waitForURL(/\/plants\/[0-9a-f-]+$/);
  const plant=new URL(page.url()).pathname, plantId=plant.split('/').at(-1), schedule=enclosure+"/care-schedule/plant_watering", query="?plant_id="+plantId;
  await go(schedule+query);response=await post(schedule+"/preview"+query,{interval_days:"3",first_due_at:exact,enabled:"true"});html=await response.text();token=html.match(/name="preview_token" value="([^"]+)"/)[1];await post(schedule+"/confirm"+query,{preview_token:token});
  await go(schedule+query);await validField('[name="first_due_at"]');await page.locator('[name="interval_days"]').fill("4");await page.getByRole("button",{name:"Preview schedule",exact:true}).click();await page.locator('[name="preview_token"]').waitFor({state:"attached"});assert((await page.locator("main").innerText()).includes("12:00:37.123456"));await page.getByRole("link",{name:"Change choices",exact:true}).click();await validField('[name="first_due_at"]');await page.getByRole("button",{name:"Preview schedule",exact:true}).click();await page.locator('[name="preview_token"]').waitFor({state:"attached"});await page.getByRole("button",{name:"Confirm schedule",exact:true}).click();await page.waitForURL(manifest.origin+plant);
  assert.equal(readSql("SELECT override_due_at FROM reminder_rule_current WHERE subject_id=? AND reminder_type='plant_watering'",[plantId])[0][0],exact);
  report.checks.push({name:"plant-schedule-actual-input-and-change-choices-preserve-microseconds",status:"passed"});
  await post(plant+"/waterings",{idempotency_key:"precision-browser-watering",occurred_at:exact,notes:"Precise fictional watering"});
  await go(enclosure+"/care-history?plant_id="+plantId);await page.getByText("Correct watering",{exact:true}).click();await validField('[name="occurred_at"]');
  const correction=page.locator('form').filter({has:page.locator('[name="action"][value="correct"]')});await correction.locator('[name="notes"]').fill("Only these notes changed");await correction.locator('[name="reason"]').fill("Browser precision regression");await correction.getByRole("button",{name:"Save correction",exact:true}).click();await page.waitForURL(manifest.origin+enclosure+"/care-history");
  const corrected=readSql("SELECT occurred_at FROM domain_events WHERE event_type='enclosure.plant_watering_corrected' AND stream_id=? ORDER BY global_position DESC LIMIT 1",[enclosure.split('/').at(-1)]);
  assert.equal(corrected[0][0],exact);
  report.checks.push({name:"notes-only-watering-actual-input-preserves-microseconds",status:"passed"});
  assert.deepEqual(report.externalRequests,[]);assert.deepEqual(report.errors,[]);report.status="passed";
 }finally{fs.writeFileSync(output,JSON.stringify(report,null,2)+"\n");await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
