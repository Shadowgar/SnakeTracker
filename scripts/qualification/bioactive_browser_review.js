"use strict";
// Real browser qualification; every write is confined to a declared fictional fixture.
const fs=require("node:fs"), path=require("node:path"), assert=require("node:assert/strict");
const {chromium}=require(process.env.CARE_PLAYWRIGHT||"playwright");
const fixture=fs.realpathSync(process.env.CARE_FIXTURE);
assert.match(fixture,/^\/tmp\/carekeeper-x5-browser-[^/]+$/);
const manifest=JSON.parse(fs.readFileSync(path.join(fixture,"manifest.json"),"utf8"));
assert.equal(manifest.fictional,true);
assert.match(manifest.origin,/^http:\/\/127\.0\.0\.1:81\d\d$/);
const output=path.join(fixture,"bioactive-evidence");fs.mkdirSync(output,{recursive:true});
const report={sourceRevision:process.env.CARE_SOURCE_REVISION||"working-tree",screenshots:[],checks:[],externalRequests:[],errors:[]};
const localTime=offset=>new Date(Date.now()+offset).toISOString().slice(0,16);
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const context=await browser.newContext({viewport:{width:390,height:844},timezoneId:"UTC"});
  await context.route("**/*",async route=>{
   const url=route.request().url();
   if(!url.startsWith(manifest.origin+"/")){report.externalRequests.push(url);return route.abort();}
   if(url.endsWith("/static/care-axe.js"))return route.fulfill({contentType:"application/javascript",body:fs.readFileSync(process.env.CARE_AXE,"utf8")});
   return route.continue();
  });
  const page=await context.newPage();page.on("pageerror",e=>report.errors.push(String(e)));
  const go=route=>page.goto(manifest.origin+route);
  const capture=async name=>{
   await page.addScriptTag({url:manifest.origin+"/static/care-axe.js"});
   const result=await page.evaluate(async()=>await axe.run(document.querySelector("main"),{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa"]}}));
   const width=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));
   report.checks.push({name,url:page.url(),width,violations:result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))});
   assert(width.scroll<=width.viewport,JSON.stringify(width));assert.equal(result.violations.length,0,JSON.stringify(report.checks.at(-1)));
   await page.evaluate(()=>document.activeElement?.blur());await page.mouse.move(0,0);
   await page.screenshot({path:path.join(output,name+".png"),fullPage:true});report.screenshots.push(name+".png");
  };
  await go("/login");await page.locator('[name="email"]').fill("owner@example.com");await page.locator('[name="password"]').fill("correct horse battery staple");await page.locator('button[type="submit"]').click();await page.waitForURL(/\/home$/);
  const enclosure=async name=>{
   await go("/enclosures/new");await page.locator('[name="name"]').fill(name);await page.locator('[name="enclosure_type_choice"]').selectOption({index:1});await page.getByRole("button",{name:"Create enclosure",exact:true}).click();await page.waitForURL(/\/enclosures\/[0-9a-f-]+$/);return new URL(page.url()).pathname;
  };
  const home=await enclosure("Canopy habitat"), destination=await enclosure("Second habitat");
  const animal=manifest.paths["Pelodryas caerulea"];
  const move=async target=>{
   await go(animal+"/enclosure");await page.locator('[name="enclosure_id"]').selectOption(target.split("/").at(-1));await page.locator('[name="occurred_at"]').fill(localTime(-60000));await page.getByRole("button",{name:"Move animal",exact:true}).click();await page.waitForURL(manifest.origin+animal);
  };
  await move(home);
  await go(home);await page.locator('form[action$="/mode"] [name="bioactive"]').selectOption("true");await page.getByRole("button",{name:"Save mode",exact:true}).click();await page.waitForURL(manifest.origin+home);assert.match(await page.locator("main").innerText(),/Bioactive/);
  const plant=async label=>{
   await go(home+"/plants/new");await page.locator('[name="manual_species"]').fill("Monstera deliciosa");await page.locator('[name="label"]').fill(label);await page.getByRole("button",{name:"Add plant",exact:true}).click();await page.waitForURL(/\/plants\/[0-9a-f-]+$/);return new URL(page.url()).pathname;
  };
  const left=await plant("Left planter"), right=await plant("Right planter");
  const schedule=async(plantPath,days,takeCapture)=>{
   await go(plantPath);await page.getByRole("link",{name:"Set watering schedule",exact:true}).click();await page.locator('[name="interval_days"]').fill(String(days));await page.locator('[name="first_due_at"]').fill(localTime(-2*86400000));await page.locator('[name="enabled"]').check();
   if(takeCapture)await capture("plant-schedule-390");
   await page.getByRole("button",{name:"Preview schedule",exact:true}).click();await page.locator('[name="preview_token"]').waitFor({state:"attached"});
   if(takeCapture)await capture("plant-confirm-390");
   await page.getByRole("button",{name:"Confirm schedule",exact:true}).click();
   await page.waitForURL(manifest.origin+plantPath);
   assert.match(await page.locator("#history").innerText(),new RegExp("Every "+days+" days"));
  };
  await schedule(left,3,true);await schedule(right,7,false);
  await go(home);await capture("bioactive-enclosure-390");
  for(const route of ["/home","/calendar?view=agenda","/reminders"]){await go(route);const text=await page.locator("main").innerText();assert(text.includes("Left planter")&&text.includes("Right planter"),route);}
  await go(left);const water=page.locator("#watering");await water.locator('[name="occurred_at"]').fill(localTime(-60000));await water.locator('[name="notes"]').fill("Fictional browser watering record");await water.getByRole("button",{name:"Save watering",exact:true}).click();await page.waitForURL(manifest.origin+left+"#history");await page.evaluate(()=>scrollTo(0,0));await capture("plant-after-watering-390");
  await go("/home");assert((await page.locator('section[aria-labelledby="home-upcoming"]').innerText()).includes("Left planter"));assert((await page.locator('section[aria-labelledby="home-overdue"]').innerText()).includes("Right planter"));
  await go(left);await page.getByRole("link",{name:"Review, correct or void watering history",exact:true}).click();await page.getByText("Correct watering",{exact:true}).click();const correct=page.locator('form').filter({has:page.locator('[name="action"][value="correct"]')}).first();await correct.locator('[name="occurred_at"]').fill(localTime(-6*86400000));await correct.locator('[name="reason"]').fill("Correct fictional recording date");await correct.getByRole("button",{name:"Save correction",exact:true}).click();await page.waitForURL(manifest.origin+home+"/care-history");
  await go(left);assert((await page.locator("main").innerText()).includes("Fictional browser watering record"));
  await go("/home");assert((await page.locator('section[aria-labelledby="home-overdue"]').innerText()).includes("Left planter"));
  await go(home+"/care-history?plant_id="+left.split("/").at(-1));
  for(const [action,label] of [["void","Void record"],["reinstate","Reinstate record"]]){
   const form=page.locator("article form").filter({has:page.locator('[name="action"][value="'+action+'"]')}).first();
   await form.locator('[name="reason"]').fill("Fictional "+action+" qualification");await form.getByRole("button",{name:label,exact:true}).click();await page.waitForURL(manifest.origin+home+"/care-history");
   assert.match(await page.locator("main").innerText(),action==="void"?/Voided/:/Effective/);
  }
  await move(destination);await go(home);assert((await page.locator("main").innerText()).includes("No animals are assigned here."));assert((await page.locator("main").innerText()).includes("Left planter"));assert((await page.locator("main").innerText()).includes("Right planter"));assert.match(await page.locator("main").innerText(),/Bioactive/);
  await page.setViewportSize({width:1440,height:900});await capture("enclosure-after-move-1440");await go(home+"/care-history");await capture("maintenance-history-1440");
  await page.setViewportSize({width:320,height:844});await go(right);await capture("independent-plant-320");
  report.checks.push({name:"independent-plant-schedules-record-correct-and-animal-move",status:"passed"});
  assert.deepEqual(report.externalRequests,[]);assert.deepEqual(report.errors,[]);report.status="passed";
 }finally{if(report.status!=="passed"){const p=browser.contexts()[0]?.pages()[0];if(p){report.failurePage={url:p.url(),text:await p.locator("main").innerText().catch(()=>"")};}}fs.writeFileSync(path.join(output,"browser-results.json"),JSON.stringify(report,null,2)+"\n");await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
