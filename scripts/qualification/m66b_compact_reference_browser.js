"use strict";
// Real HTTP against a separately seeded fictional fixture only.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.M66B_PLAYWRIGHT_MODULE||'playwright');
const fixture=fs.readFileSync('/tmp/m66b-compact-browser-path','utf8').trim();
assert.match(fs.realpathSync(fixture),/^\/tmp\/m66b-browser\.[^/]+$/);
const manifest=JSON.parse(fs.readFileSync(path.join(fixture,'browser-manifest.json')));
assert.equal(fs.realpathSync(manifest.database),path.join(fs.realpathSync(fixture),'snaketracker.sqlite3'));
const out=process.env.M66B_COMPACT_EVIDENCE||path.join(fixture,'compact-review');fs.mkdirSync(out,{recursive:true});
const origin='http://127.0.0.1:8098', baseline=process.env.M66B_COMPACT_BASELINE==='1';
const axePath='/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js';
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:'/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome'});
const result={fictionalDataOnly:true,baseline,captures:[],cases:[],diagnostics:[],externalRequests:[]};
try{
for(const [name,viewport] of [['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]]){
 const context=await browser.newContext({viewport,serviceWorkers:'block'});const page=await context.newPage();
 page.on('pageerror',e=>result.diagnostics.push(String(e)));page.on('console',m=>{if(m.type()==='error')result.diagnostics.push(m.text());});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==origin){result.externalRequests.push(url.origin);return route.abort();}if(url.pathname==='/static/qualification-axe.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(axePath)});return route.continue();});
 await page.goto(origin+'/login');await page.locator('[name=email]').fill('guide-review@example.test');await page.locator('[name=password]').fill('fictional-guide-review-password');await Promise.all([page.waitForURL(u=>u.pathname!='/login'),page.locator('button[type=submit]').click()]);
 async function capture(label){await page.addScriptTag({url:origin+'/static/qualification-axe.js'});const violations=await page.evaluate(async()=>(await axe.run(document)).violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)})));const width=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));await page.screenshot({path:path.join(out,name+'-'+label+'.png'),fullPage:true});result.captures.push({viewport:name,label,axeViolations:violations,width});assert.deepEqual(violations,[]);assert(width.scroll<=width.viewport+1);}
 for(const [taxon,route,count] of [['boa',manifest.animal_urls.boa_guide,28],['dragon',manifest.animal_urls.disagreement,7],['python',manifest.animal_urls.with_guide,6]]){
  const response=await page.goto(origin+route,{waitUntil:'networkidle'});assert.equal(response.status(),200);const ref=page.locator('.overview-reference');
  const height=await ref.evaluate(e=>e.getBoundingClientRect().height);result.cases.push({viewport:name,taxon,defaultHeight:height});
  if(baseline){await capture(taxon+'-baseline');continue;}
  const sections=ref.locator('details.profile-reference-disclosure');assert(await sections.count()>0,'Major sections must be collapsible');assert.equal(await sections.locator(':scope[open]').count(),0);
  assert.equal(await ref.locator('article.guide-fact').count(),count);assert.equal(await ref.locator('article.guide-fact:visible').count(),0);
  const glance=ref.locator('.profile-reference-grid');assert(await glance.isVisible());const columns=await glance.evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);assert.equal(columns,viewport.width===390?2:4);
  assert(await ref.locator('.guide-state-differ:visible').count()>=1 || taxon==='python');await capture(taxon+'-default');
  if(taxon==='boa'){
   await ref.scrollIntoViewIfNeeded();await capture('boa-collapsed-sections');
   const temps=sections.filter({has:page.locator('summary h3',{hasText:'Temperature & humidity'})});assert.equal(await temps.count(),1);const summary=temps.locator(':scope > summary');await summary.focus();assert(await summary.evaluate(e=>parseFloat(getComputedStyle(e).outlineWidth)>=2),'Keyboard focus must have a visible outline');await page.keyboard.press('Enter');assert(await temps.evaluate(e=>e.open));assert(await temps.locator('.guide-positions').count()>0);await capture('boa-temperature-disagreement');
   await page.keyboard.press('Space');assert.equal(await temps.evaluate(e=>e.open),false);
   const sources=ref.locator('details.profile-reference-sources');await sources.locator(':scope > summary').focus();await page.keyboard.press('Enter');assert(await sources.evaluate(e=>e.open));assert.equal(await sources.locator('li').count(),7);assert((await sources.innerText()).includes('Version 1'),'Guide version provenance must remain on the Animal page');for(const link of await sources.locator('li a').all()){assert(await link.isVisible());assert((await link.innerText()).trim().length>3);assert((await link.getAttribute('href')).startsWith('https://'));}await capture('boa-sources-expanded');
  }
  for(const section of await sections.all()){await section.locator(':scope > summary').click();}
  assert.equal(await ref.locator('article.guide-fact:visible').count(),count,'All facts must become available on this page');for(const detail of await ref.locator('article.guide-fact .guide-disclosure').all()){await detail.locator('summary').click();assert(await detail.locator('a').first().isVisible());}
  await capture(taxon+'-all-content-reachable');
 }
 if(!baseline){for(const route of ['/directory','/directory/'+manifest.taxon_ids['Pogona vitticeps'],'/directory/'+manifest.taxon_ids['Pogona vitticeps']+'/care-guide','/directory/'+manifest.taxon_ids['Monstera deliciosa']+'/care-guide']){const response=await page.goto(origin+route,{waitUntil:'networkidle'});assert.equal(response.status(),200);await capture(route.endsWith('care-guide')?'standalone-'+(route.includes(manifest.taxon_ids['Monstera deliciosa'])?'plant':'dragon'):'directory-'+(route==='/directory'?'index':'dragon'));}}
 await context.close();
}
assert.deepEqual(result.diagnostics,[]);assert.deepEqual(result.externalRequests,[]);
}catch(error){result.error=String(error);throw error;}finally{fs.writeFileSync(path.join(out,baseline?'baseline.json':'qualification.json'),JSON.stringify(result,null,2)+'\n');await browser.close();}
process.stdout.write(JSON.stringify({captures:result.captures.length,cases:result.cases,axeViolations:0,overflow:0,unexpectedConsoleErrors:0,externalRequests:0})+'\n');
})().catch(e=>{console.error(e);process.exit(1)});
