"use strict";

// Private browser evidence against a disposable fictional SQLite fixture only.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require(process.env.M66B_PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(__dirname, "../..");
const fixture = fs.realpathSync(fs.readFileSync("/tmp/m66b-navigation-browser-path", "utf8").trim());
assert.match(fixture, /^\/tmp\/m66b-browser\.[^/]+$/);
const manifest = JSON.parse(fs.readFileSync(path.join(fixture, "browser-manifest.json"), "utf8"));
assert.equal(fs.realpathSync(manifest.database), path.join(fixture, "snaketracker.sqlite3"));
const origin = "http://127.0.0.1:8098";
const evidence = path.resolve(process.env.M66B_NAVIGATION_EVIDENCE || path.join(fixture, "navigation-review"));
fs.mkdirSync(path.join(evidence, "screenshots"), { recursive: true });
const axePath = process.env.M66B_AXE || "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";
const runId = new Date().toISOString().replace(/[^0-9]/g, "");
const result = {
  runId, origin, fictionalDataOnly: true, fixture, normalCSP: true,
  sourceCommit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
  dirtySource: Boolean(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim()),
  providerMapping: manifest.provider_mappings["Boa imperator"],
  cases: [], captures: [], diagnostics: [], externalRequests: [], directoryRequestsOnReads: [],
};
const labels = ["Overview", "History", "Trends", "Care", "Guides & Species Reference"];
const suffixes = ["", "/timeline", "/analytics", "/care", "/reference"];
const absentGuide = "No reviewed captive-care guide is available yet.";
const state = { viewport: "", case: "", referenceRead: false };
function writeResult() {
  result.totals = {
    cases: result.cases.length, passed: result.cases.filter(c => c.status === "passed").length,
    failed: result.cases.filter(c => c.status === "failed").length, captures: result.captures.length,
    axeViolations: result.captures.reduce((n, c) => n + c.axeViolations.length, 0),
    pageOverflow: result.captures.filter(c => c.width.scroll > c.width.viewport + 1).length,
    unexpectedConsoleOrPageErrors: result.diagnostics.length,
    externalRequests: result.externalRequests.length,
    directoryRequestsOnReads: result.directoryRequestsOnReads.length,
  };
  fs.writeFileSync(path.join(evidence, "qualification.json"), JSON.stringify(result, null, 2) + "\n");
}
async function runCase(name, action) {
  state.case = name;
  const start = Date.now();
  try {
    const facts = await action();
    result.cases.push({ viewport: state.viewport, name, status: "passed", durationMs: Date.now() - start, facts: facts || {} });
  } catch (error) {
    result.cases.push({ viewport: state.viewport, name, status: "failed", durationMs: Date.now() - start, error: error.stack });
    console.error(`${state.viewport} ${name}: ${error.message}`);
  }
  state.referenceRead = false;
  writeResult();
}
async function open(page, route, referenceRead = false) {
  state.referenceRead = referenceRead;
  const response = await page.goto(origin + route, { waitUntil: "domcontentloaded" });
  assert.equal(response.status(), 200, `${route}: HTTP ${response.status()}`);
  const width = await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
  assert(width.scroll <= width.viewport + 1, `${route}: page overflow`);
  return response;
}
async function capture(page, name, target = null, fullPage = false) {
  // axe temporarily focuses interactive elements. Preserve actual keyboard focus before capture.
  const focused = await page.evaluateHandle(() => document.activeElement);
  const position = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
  if (!await page.evaluate(() => Boolean(window.axe))) await page.addScriptTag({ url: origin + "/static/qualification-axe.js" });
  const axeViolations = await page.evaluate(async () => (await window.axe.run(document)).violations.map(v => ({
    id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target),
  })));
  await focused.evaluate(e => { if (e && e.isConnected && e.focus) e.focus({ preventScroll: true }); });
  await focused.dispose();
  await page.evaluate(({ x, y }) => scrollTo(x, y), position);
  if (target) await target.scrollIntoViewIfNeeded();
  const width = await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
  const filename = `${state.viewport}-${name}.png`;
  await page.screenshot({ path: path.join(evidence, "screenshots", filename), fullPage });
  result.captures.push({ viewport: state.viewport, name, screenshot: `screenshots/${filename}`, actualViewport: !fullPage, axeViolations, width });
  assert.deepEqual(axeViolations, [], `${name}: axe violations`);
  assert(width.scroll <= width.viewport + 1, `${name}: page overflow`);
}
async function verifyNav(page, route, active) {
  const nav = page.locator(".animal-section-nav");
  assert.deepEqual(await nav.locator("a").allTextContents(), labels);
  assert.deepEqual(await nav.locator("a").evaluateAll(a => a.map(e => e.getAttribute("href"))), suffixes.map(s => route + s));
  assert.deepEqual(await nav.locator('[aria-current="page"]').allTextContents(), [labels[active]]);
  assert(await page.locator(".profile-hero #page-title").isVisible());
  const fontSizes = await nav.locator("a").evaluateAll(a => a.map(e => parseFloat(getComputedStyle(e).fontSize)));
  assert(fontSizes.every(size => size >= 14), "Five-tab labels must remain readable");
  return { order: labels, active: labels[active], fontSizes };
}
async function keyboardToggle(page, detail, key = "Enter") {
  const previous = await detail.evaluate(e => e.open);
  const summary = detail.locator(":scope > summary");
  await summary.focus();
  await page.keyboard.press(key);
  assert.equal(await detail.evaluate(e => e.open), !previous, `Native ${key} disclosure toggle`);
  const outline = await summary.evaluate(e => getComputedStyle(e).outlineWidth);
  assert(parseFloat(outline) >= 2, "Disclosure keyboard focus outline");
  return summary;
}
async function actionStyle(page, selector, name, href, secondary) {
  const link = page.locator(selector).getByRole("link", { name, exact: true });
  assert.equal(await link.evaluate(e => e.tagName), "A");
  assert.equal(await link.getAttribute("href"), href);
  assert.equal(await link.getAttribute("role"), null, "Navigation must retain native anchor role");
  assert(await link.isVisible());
  const styles = await link.evaluate(e => {
    const s = getComputedStyle(e);
    return { display: s.display, minHeight: parseFloat(s.minHeight), radius: parseFloat(s.borderRadius),
      textDecoration: s.textDecorationLine, borderWidth: parseFloat(s.borderTopWidth), background: s.backgroundColor };
  });
  assert(["flex", "inline-flex"].includes(styles.display));
  assert(styles.minHeight >= 40 && styles.radius >= 4, `${name}: button dimensions`);
  assert.equal(styles.textDecoration, "none");
  if (secondary) assert(styles.borderWidth >= 1, `${name}: secondary border`);
  await link.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  assert(await link.evaluate(e => e === document.activeElement), `${name}: native keyboard focus`);
  const focused = await link.evaluate(e => ({ width: parseFloat(getComputedStyle(e).outlineWidth), style: getComputedStyle(e).outlineStyle }));
  assert(focused.width >= 2 && focused.style !== "none", `${name}: visible keyboard focus`);
  return styles;
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.M66B_CHROMIUM || "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome" });
  try {
    for (const [label, viewport] of [["desktop-1440x900", { width: 1440, height: 900 }], ["mobile-390x844", { width: 390, height: 844 }]]) {
      state.viewport = label;
      const context = await browser.newContext({ viewport, serviceWorkers: "block" });
      await context.route("**/*", route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) {
          result.externalRequests.push({ viewport: label, case: state.case, url: url.href });
          return route.abort("blockedbyclient");
        }
        if (state.referenceRead && url.pathname.startsWith("/api/directory/")) result.directoryRequestsOnReads.push({ viewport: label, case: state.case, path: url.pathname });
        if (url.pathname === "/static/qualification-axe.js") return route.fulfill({ contentType: "application/javascript", body: fs.readFileSync(axePath) });
        return route.continue();
      });
      const page = await context.newPage();
      page.setDefaultTimeout(8000);
      page.on("pageerror", e => result.diagnostics.push({ viewport: label, case: state.case, type: "pageerror", message: String(e) }));
      page.on("console", m => { if (m.type() === "error") result.diagnostics.push({ viewport: label, case: state.case, type: "console", message: m.text() }); });
      state.case = "login";
      await open(page, "/login");
      await page.locator('[name="email"]').fill("guide-review@example.test");
      await page.locator('[name="password"]').fill("fictional-guide-review-password");
      await Promise.all([page.waitForURL(u => u.pathname !== "/login"), page.locator('button[type="submit"]').click()]);
      const boa = manifest.animal_urls.boa_guide;
      await runCase("compact-overview-summary", async () => {
        await open(page, boa, true);
        const nav = await verifyNav(page, boa, 0);
        const summary = page.locator(".overview-reference");
        const text = await summary.innerText();
        assert(text.includes("Boa constrictor") && text.includes("Reviewed captive-care guide available."));
        assert.equal(await summary.locator("article.guide-fact, details.profile-reference-disclosure").count(), 0);
        assert.equal(await summary.locator(".profile-reference-fact").count(), 3);
        assert(await page.locator(".overview-care").isVisible());
        assert(await summary.getByRole("link", { name: "Guides & Species Reference", exact: false }).isVisible());
        await capture(page, "boa-overview-top");
        await capture(page, "boa-overview-compact-reference", summary);
        return { ...nav, glanceFacts: 3, fullFactsOnOverview: 0, compactHeight: await summary.evaluate(e => e.getBoundingClientRect().height) };
      });
      await runCase("five-tabs-active-and-navigation", async () => {
        const facts = [];
        for (let index = 0; index < suffixes.length; index++) {
          await open(page, boa + suffixes[index], true);
          facts.push(await verifyNav(page, boa, index));
          if (index === 3) assert.equal(await page.locator("article.guide-fact").count(), 0, "Care remains personal");
        }
        await capture(page, "boa-reference-top");
        return { sections: facts };
      });
      await runCase("keyboard-tabstrip-reaches-reference", async () => {
        await open(page, boa, true);
        const nav = page.locator(".animal-section-nav");
        await nav.locator("a").first().focus();
        for (let index = 1; index < labels.length; index++) {
          await page.keyboard.press("Tab");
          assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), labels[index]);
        }
        const last = nav.locator("a").last();
        const geometry = await last.evaluate(e => {
          const a = e.getBoundingClientRect(), n = e.parentElement.getBoundingClientRect();
          return { anchorLeft: a.left, anchorRight: a.right, stripLeft: n.left, stripRight: n.right, scrollLeft: e.parentElement.scrollLeft,
            scrollWidth: e.parentElement.scrollWidth, clientWidth: e.parentElement.clientWidth,
            focusOutline: getComputedStyle(e).outlineWidth };
        });
        assert(geometry.anchorLeft >= geometry.stripLeft - 1 && geometry.anchorRight <= geometry.stripRight + 1);
        assert(parseFloat(geometry.focusOutline) >= 2);
        if (viewport.width === 390) assert(geometry.scrollLeft > 0 && geometry.scrollWidth > geometry.clientWidth);
        await capture(page, "keyboard-tabstrip-reference-focused", nav);
        await Promise.all([page.waitForURL(u => u.pathname === boa + "/reference"), page.keyboard.press("Enter")]);
        await verifyNav(page, boa, 4);
        return geometry;
      });
      await runCase("full-reviewed-guide-collapsed-and-expanded", async () => {
        await open(page, boa + "/reference", true);
        const content = page.locator(".animal-reference-content");
        for (const name of ["Species Overview / Natural History", "Reviewed Captive Care", "Sources / Provenance"]) assert(await content.getByRole("heading", { name, exact: true }).isVisible());
        const sections = content.locator(".profile-reference-sections > details.profile-reference-disclosure");
        const facts = content.locator("article.guide-fact");
        assert.equal(await sections.count(), 8);
        assert.equal(await content.locator("details.profile-reference-disclosure[open]").count(), 0);
        assert.equal(await facts.count(), 28);
        assert.equal(await content.locator("article.guide-fact:visible").count(), 0);
        const gridColumns = await content.locator(".profile-reference-sections").evaluate(e => getComputedStyle(e).gridTemplateColumns.split(" ").length);
        assert.equal(gridColumns, viewport.width === 390 ? 1 : 2);
        await capture(page, "boa-reference-collapsed-sections", sections.first());
        for (const section of await sections.all()) await keyboardToggle(page, section);
        assert.equal(await content.locator("article.guide-fact:visible").count(), 28);
        for (const fact of await facts.all()) assert(await fact.locator(".guide-value, .guide-position strong").first().isVisible());
        const citationPositions = await facts.locator("details.guide-disclosure li").count();
        assert.equal(citationPositions, 34);
        await capture(page, "boa-reference-expanded-top", content.getByRole("heading", { name: "Reviewed Captive Care", exact: true }));
        await capture(page, "boa-reference-all-expanded-full-page", null, true);
        return { contextualFacts: 28, citedPositions: 34, sections: 8, sectionGridColumns: gridColumns };
      });
      await runCase("sources-differ-native-disclosure", async () => {
        await open(page, boa + "/reference", true);
        const section = page.locator(".profile-reference-sections > details").filter({ has: page.locator("summary h3", { hasText: "Temperature & humidity" }) });
        await keyboardToggle(page, section);
        const fact = section.locator("article.guide-fact").filter({ has: page.locator(".guide-positions") }).first();
        assert(await fact.isVisible());
        const positions = await fact.locator(".guide-position strong").allTextContents();
        assert(positions.length >= 2 && new Set(positions).size >= 2, "Separate source positions remain available");
        assert((await fact.innerText()).includes("Sources differ"));
        await capture(page, "boa-temperature-sources-differ", fact);
        await keyboardToggle(page, section, "Space");
        assert.equal(await section.evaluate(e => e.open), false);
        return { separatePositions: positions, keyboardEnterAndSpace: true };
      });
      await runCase("source-provenance-and-per-fact-disclosures", async () => {
        await open(page, boa + "/reference", true);
        const content = page.locator(".animal-reference-content");
        const source = content.locator("details.profile-reference-sources");
        assert.equal(await source.evaluate(e => e.open), false);
        await keyboardToggle(page, source);
        assert.equal(await source.locator(".profile-reference-bibliography li").count(), 7);
        assert((await source.innerText()).includes("Version 1"));
        for (const item of await source.locator(".profile-reference-bibliography li").all()) {
          const link = item.locator("a");
          assert.match(await link.getAttribute("href"), /^https:\/\//);
          assert.equal(await link.getAttribute("target"), "_blank");
          assert((await link.getAttribute("rel")).includes("noopener"));
          assert((await item.innerText()).includes("Retrieved") && (await item.innerText()).includes("Reviewed"));
        }
        await capture(page, "boa-sources-expanded", source);
        const sections = content.locator(".profile-reference-sections > details");
        for (const section of await sections.all()) await keyboardToggle(page, section);
        for (const disclosure of await content.locator("article.guide-fact details.guide-disclosure").all()) {
          await keyboardToggle(page, disclosure);
          assert(await disclosure.locator("a").first().isVisible());
        }
        await capture(page, "boa-fact-provenance-expanded", content.locator("article.guide-fact").first());
        return { bibliographySources: 7, factSourceDisclosures: 28, reviewedDates: true, externalLinksNotOpened: true };
      });
      for (const key of ["boa_imperator", "linked_without_guide"]) await runCase(`${key}-linked-without-care-guide`, async () => {
        const route = manifest.animal_urls[key];
        await open(page, route, true);
        assert((await page.locator(".overview-reference").innerText()).includes(absentGuide));
        await open(page, route + "/reference", true);
        const content = page.locator(".animal-reference-content");
        const scientific = key === "boa_imperator" ? "Boa imperator" : "Morelia spilota";
        assert((await content.innerText()).includes(scientific));
        assert((await content.innerText()).includes(absentGuide));
        assert(!(await content.innerText()).includes("No reviewed species guidance"));
        assert.equal(await content.locator("article.guide-fact").count(), 0);
        assert((await content.getByRole("heading", { name: "Species Overview / Natural History", exact: true }).locator("..").innerText()).includes("Kingdom"));
        if (key === "boa_imperator") {
          assert((await content.innerText()).includes("Central American Boa"));
          assert(await content.locator('a[href^="https://www.inaturalist.org/taxa/539399"]').count());
          assert.deepEqual(manifest.provider_mappings["Boa imperator"], { provider: "inaturalist", provider_id: "539399" });
        }
        await capture(page, key + "-reference-top");
        await capture(page, key + "-reference-guide-absence", content.getByRole("heading", { name: "Reviewed Captive Care", exact: true }));
        return { scientificName: scientific, absentCareSpecific: true, savedTaxonomyAvailable: true, inventedNaturalHistory: false };
      });
      await runCase("unlinked-reference-link-species-native-anchor", async () => {
        const route = manifest.animal_urls.unlinked;
        await open(page, route, true);
        assert.equal(await page.locator(".overview-reference article.guide-fact").count(), 0);
        await open(page, route + "/reference", true);
        const content = page.locator(".animal-reference-content");
        assert((await content.innerText()).includes("Your manual species record remains valid."));
        const link = content.getByRole("link", { name: "Link species", exact: true });
        assert.equal(await link.evaluate(e => e.tagName), "A");
        assert.equal(await link.getAttribute("href"), route + "/species");
        await capture(page, "unlinked-reference");
        await link.focus();
        await Promise.all([page.waitForURL(u => u.pathname === route + "/species"), page.keyboard.press("Enter")]);
        assert(await page.locator("[data-taxon-combobox]").isVisible());
        return { explicitLinkWorkflow: true, manualRecordPreserved: true };
      });
      await runCase("empty-feeding-peer-actions-style-and-semantics", async () => {
        await open(page, boa + "/feedings/new");
        const actions = {};
        actions.addFood = await actionStyle(page, ".action-row", "Add food to inventory", "/inventory/new", false);
        actions.setup = await actionStyle(page, ".action-row", "Set up inventory", "/inventory", true);
        actions.cancel = await actionStyle(page, ".form-actions", "Cancel", boa, true);
        assert.equal(await page.locator('.care-form-page button[type="submit"]').count(), 0);
        await capture(page, "feeding-empty-inventory-actions", page.locator(".empty-state"));
        const setup = page.locator(".action-row").getByRole("link", { name: "Set up inventory", exact: true });
        await setup.focus();
        await Promise.all([page.waitForURL(u => u.pathname === "/inventory"), page.keyboard.press("Enter")]);
        return { actions, navigationPreserved: true, falseSubmitAbsent: true };
      });
      for (const [kind, suffix, animal] of [
        ["weight", "weights", boa], ["length", "lengths", boa], ["shed", "sheds", boa], ["bath", "baths", boa],
        ["molt", "molts", manifest.animal_urls.form_spider], ["premolt", "premolt-observations", manifest.animal_urls.form_spider],
        ["misting", "mistings", manifest.animal_urls.form_spider],
      ]) await runCase(`record-${kind}-submit-cancel-controls`, async () => {
        await open(page, `${animal}/${suffix}/new`);
        const styles = await actionStyle(page, ".form-actions", "Cancel", animal, true);
        const submit = page.locator('.form-actions button[type="submit"]');
        assert.equal(await submit.count(), 1);
        assert.equal((await submit.innerText()).toLowerCase(), `record ${kind}`);
        assert.equal(await submit.evaluate(e => e.tagName), "BUTTON");
        const primary = await submit.evaluate(e => ({ display: getComputedStyle(e).display, minHeight: parseFloat(getComputedStyle(e).minHeight), background: getComputedStyle(e).backgroundColor }));
        assert(["flex", "inline-flex"].includes(primary.display));
        assert(primary.minHeight >= 40 && primary.background !== styles.background);
        if (["length", "weight"].includes(kind)) {
          await capture(page, `record-${kind}-submit-cancel`, page.locator(".form-actions"));
          const cancel = page.locator(".form-actions").getByRole("link", { name: "Cancel", exact: true });
          await cancel.focus();
          await Promise.all([page.waitForURL(u => u.pathname === animal), page.keyboard.press("Enter")]);
        }
        return { kind, cancelNativeAnchor: true, submitNativeButton: true, cancelStyles: styles, primaryStyles: primary };
      });
      await context.close();
    }
  } catch (error) {
    result.diagnostics.push({ type: "fatal", message: error.stack });
  } finally {
    await browser.close();
    writeResult();
    console.log(JSON.stringify({ evidence, ...result.totals }));
    if (result.totals.failed || result.totals.unexpectedConsoleOrPageErrors || result.totals.externalRequests || result.totals.directoryRequestsOnReads) process.exitCode = 1;
  }
})();
