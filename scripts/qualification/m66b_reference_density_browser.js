"use strict";

// Real HTTP, normal CSP and self-hosted axe. Only an existing fictional /tmp fixture.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require(process.env.M66B_PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(__dirname, "../..");
const fixture = fs.realpathSync(fs.readFileSync("/tmp/m66b-density-browser-path", "utf8").trim());
assert.match(fixture, /^\/tmp\/m66b-browser\.[^/]+$/);
const manifest = JSON.parse(fs.readFileSync(path.join(fixture, "browser-manifest.json"), "utf8"));
assert.equal(fs.realpathSync(manifest.database), path.join(fixture, "snaketracker.sqlite3"));
const origin = "http://127.0.0.1:8098";
const review = path.join(fixture, "density-review");
const baseline = JSON.parse(fs.readFileSync(path.join(review, "baseline.json"), "utf8"));
const server = JSON.parse(fs.readFileSync(path.join(review, "server-meta.json"), "utf8"));
assert.equal(server.environment, "test");
assert.equal(server.database, manifest.database);
assert.equal(server.origin, origin);
assert(server.network_guard && server.reference_sql_guard);
const evidence = path.resolve(process.env.M66B_DENSITY_EVIDENCE || path.join(review, "qualification"));
assert(evidence.startsWith(review + path.sep), "Evidence must stay inside the private fixture review");
fs.mkdirSync(path.join(evidence, "screenshots"), { recursive: true });
const axePath = process.env.M66B_AXE || "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";
const result = {
  fixture, origin, fictionalDataOnly: true, normalCSP: true, serverGuards: server,
  sourceCommit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
  dirtySource: Boolean(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim()),
  cases: [], measurements: [], captures: [], diagnostics: [], externalRequests: [], providerRequests: [],
};
const state = { viewport: "", name: "" };
const routeCases = [
  ["python", manifest.animal_urls.with_guide],
  ["boa", manifest.animal_urls.boa_guide],
  ...["tarantula", "scorpion"].map(name => {
    const existing = baseline.cases.find(item => item.name === name);
    assert(existing, `Baseline must identify an already existing ${name} animal`);
    return [name, existing.route];
  }),
  ["imperator", manifest.animal_urls.boa_imperator],
  ["unlinked", manifest.animal_urls.unlinked],
];
function finish() {
  result.totals = {
    cases: result.cases.length, passed: result.cases.filter(item => item.status === "passed").length,
    failed: result.cases.filter(item => item.status === "failed").length, captures: result.captures.length,
    axeViolations: result.captures.reduce((n, item) => n + item.axeViolations.length, 0),
    pageOverflow: result.captures.filter(item => item.width.scroll > item.width.viewport + 1).length,
    unexpectedErrors: result.diagnostics.length, externalRequests: result.externalRequests.length,
    providerRequests: result.providerRequests.length,
  };
  fs.writeFileSync(path.join(evidence, "qualification.json"), JSON.stringify(result, null, 2) + "\n");
}
async function runCase(name, action) {
  state.name = name;
  try {
    const facts = await action();
    result.cases.push({ viewport: state.viewport, name, status: "passed", facts: facts || {} });
  } catch (error) {
    result.cases.push({ viewport: state.viewport, name, status: "failed", error: error.stack });
    console.error(`${state.viewport} ${name}: ${error.message}`);
  }
  finish();
}
async function open(page, route) {
  const response = await page.goto(origin + route, { waitUntil: "domcontentloaded" });
  assert.equal(response.status(), 200, `${route}: HTTP status`);
  const csp = response.headers()["content-security-policy"];
  assert(csp && csp.includes("script-src 'self'") && !csp.includes("'unsafe-inline'"), "Normal application CSP");
  return response;
}
async function measurements(page) {
  return page.evaluate(() => {
    const box = element => {
      if (!element) return null;
      const r = element.getBoundingClientRect(), s = getComputedStyle(element);
      return { top: r.top + scrollY, height: r.height, width: r.width, padding: s.padding, gap: s.gap,
        minHeight: s.minHeight, alignItems: s.alignItems, alignSelf: s.alignSelf,
        display: s.display, gridColumns: s.gridTemplateColumns, whiteSpace: s.whiteSpace };
    };
    const section = id => document.getElementById(id)?.closest("section");
    return { species: box(section("species-overview-title")),
      glance: box(document.querySelector(".profile-reference-section")),
      reviewed: box(section("reviewed-care-title")), sources: box(section("reference-provenance-title")),
      whole: box(document.querySelector(".animal-reference-content")),
      tiles: Array.from(document.querySelectorAll(".profile-reference-fact")).map(box),
      careRows: Array.from(document.querySelectorAll(".profile-reference-sections > details")).map(box),
      width: { viewport: innerWidth, scroll: document.documentElement.scrollWidth } };
  });
}
async function capture(page, name, target = null, fullPage = false) {
  if (target) await target.scrollIntoViewIfNeeded();
  const position = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
  const focus = await page.evaluateHandle(() => document.activeElement);
  if (!await page.evaluate(() => Boolean(window.axe))) await page.addScriptTag({ url: origin + "/static/qualification-axe.js" });
  const axeViolations = await page.evaluate(async () => (await window.axe.run(document)).violations.map(item => ({
    id: item.id, impact: item.impact, nodes: item.nodes.map(node => node.target),
  })));
  await focus.evaluate(element => { if (element?.isConnected && element.focus) element.focus({ preventScroll: true }); });
  await focus.dispose();
  await page.evaluate(({ x, y }) => scrollTo(x, y), position);
  const width = await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
  const filename = `${state.viewport}-${name}.png`;
  await page.screenshot({ path: path.join(evidence, "screenshots", filename), fullPage });
  result.captures.push({ viewport: state.viewport, name, screenshot: `screenshots/${filename}`, fullPage, axeViolations, width });
  assert.deepEqual(axeViolations, [], `${name}: axe violations`);
  assert(width.scroll <= width.viewport + 1, `${name}: page overflow`);
}
async function keyboardToggle(page, detail, key = "Enter") {
  const previous = await detail.evaluate(element => element.open);
  const summary = detail.locator(":scope > summary");
  await summary.focus();
  await page.keyboard.press(key);
  assert.equal(await detail.evaluate(element => element.open), !previous, `Native ${key} disclosure toggle`);
  const geometry = await summary.evaluate(element => ({
    height: element.getBoundingClientRect().height, outline: parseFloat(getComputedStyle(element).outlineWidth),
    outlineStyle: getComputedStyle(element).outlineStyle,
  }));
  assert(geometry.height >= 43, "Disclosure remains an approximately 44px interactive target");
  assert(geometry.outline >= 2 && geometry.outlineStyle !== "none", "Visible keyboard disclosure focus");
  return geometry;
}
async function qualifiedDefault(page, name, route, viewport) {
  await open(page, route + "/reference");
  const current = await measurements(page);
  const before = baseline.cases.find(item => item.name === name && item.viewport === state.viewport).measurements;
  const reductions = Object.fromEntries(["species", "glance", "reviewed", "sources", "whole"].map(key => [key,
    current[key] && before[key] ? Number((100 * (before[key].height - current[key].height) / before[key].height).toFixed(1)) : null]));
  result.measurements.push({ viewport: state.viewport, name, before, after: current, reductionPercent: reductions });
  await capture(page, `${name}-default-full`, null, true);
  if (name === "python" || name === "boa") await capture(page, `${name}-default-viewport`);
  assert(current.whole.height < before.whole.height * .85, "Substantial default whole-reference height reduction");
  const content = page.locator(".animal-reference-content");
  assert.equal(await content.locator("details[open]").count(), 0, "All reference disclosures default closed");
  if (name !== "unlinked") {
    const taxonomy = content.locator("details.profile-taxonomy-disclosure");
    assert.equal(await taxonomy.count(), 1, "Full classification must use a native same-page disclosure");
    assert.equal(await taxonomy.evaluate(element => element.open), false);
    const line = content.locator(".profile-taxonomy-line");
    assert(await line.isVisible(), "Concise classification line visible by default");
    const actualValues = before.taxonomy || baseline.cases.find(item => item.name === name && item.viewport === state.viewport).measurements.taxonomy;
    for (const row of actualValues || []) {
      const parts = row.split("\n");
      assert((await taxonomy.textContent()).includes(parts.at(-1)), `Saved taxonomy value retained: ${row}`);
    }
    assert((await line.textContent()).includes(name === "python" ? "Python" : name === "boa" || name === "imperator" ? "Boa" : name === "tarantula" ? "Avicularia" : "Pandinus"));
    await keyboardToggle(page, taxonomy);
    assert(await taxonomy.locator("dl").isVisible(), "Full taxonomy reachable on the same page");
    await capture(page, `${name}-taxonomy-expanded`, taxonomy);
    await keyboardToggle(page, taxonomy, "Space");
    if (viewport.width === 1440) assert(current.species.height <= 180, "Normal short species identity should approach the 100–160px target");
  }
  if (["imperator", "unlinked"].includes(name)) {
    assert.equal(await content.locator("article.guide-fact").count(), 0);
    assert((await content.innerText()).includes(name === "unlinked"
      ? "Choose a linked species to check for a reviewed captive-care guide."
      : "No reviewed captive-care guide is available yet."));
  } else {
    const glance = content.locator(".profile-reference-grid");
    const columns = await glance.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(" ").length);
    assert.equal(columns, viewport.width === 390 ? 2 : 4);
    const careGrid = content.locator(".profile-reference-sections");
    assert.equal(await careGrid.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(" ").length), viewport.width === 390 ? 1 : 2);
    assert.equal(await careGrid.evaluate(element => getComputedStyle(element).alignItems), "start");
    assert(current.tiles.every(tile => tile.minHeight === "auto" || parseFloat(tile.minHeight) <= 90), "No oversized static tile minimum height");
    assert(current.tiles.every(tile => tile.whiteSpace !== "nowrap"), "Legitimate long values can wrap");
    if (name === "python" && viewport.width === 1440) {
      assert(new Set(current.tiles.map(tile => Math.round(tile.height))).size > 1, "Food wraps naturally without stretching simpler tiles");
      assert(current.tiles.filter(tile => tile.height <= 100).length >= 3, "Simple glance facts remain compact and readable");
      assert(current.sources.top < before.sources.top - 200, "More care rows and provenance visible within the same desktop viewport");
    }
  }
  return { reductionPercent: reductions, heights: Object.fromEntries(["species", "glance", "reviewed", "sources", "whole"].map(key => [key, current[key]?.height || null])) };
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.M66B_CHROMIUM || "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome" });
  const guardFile = path.join(review, "server-guards.jsonl");
  const guardBefore = fs.readFileSync(guardFile, "utf8");
  try {
    for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
      state.viewport = label;
      const context = await browser.newContext({ viewport, serviceWorkers: "block" });
      await context.route("**/*", route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) { result.externalRequests.push(url.href); return route.abort("blockedbyclient"); }
        if (url.pathname.startsWith("/api/directory/")) result.providerRequests.push(url.pathname);
        if (url.pathname === "/static/qualification-axe.js") return route.fulfill({ contentType: "application/javascript", body: fs.readFileSync(axePath) });
        return route.continue();
      });
      const page = await context.newPage();
      page.setDefaultTimeout(8000);
      page.on("pageerror", error => result.diagnostics.push({ viewport: label, case: state.name, message: String(error) }));
      page.on("console", message => { if (message.type() === "error") result.diagnostics.push({ viewport: label, case: state.name, message: message.text() }); });
      await open(page, "/login");
      await page.locator('[name="email"]').fill("guide-review@example.test");
      await page.locator('[name="password"]').fill("fictional-guide-review-password");
      await Promise.all([page.waitForURL(url => url.pathname !== "/login"), page.locator('button[type="submit"]').click()]);
      for (const [name, route] of routeCases) await runCase(`${name}-default-density`, () => qualifiedDefault(page, name, route, viewport));
      const boa = manifest.animal_urls.boa_guide;
      await runCase("boa-all-care-facts-and-disagreement-retained", async () => {
        await open(page, boa + "/reference");
        const content = page.locator(".animal-reference-content");
        const care = content.locator(".profile-reference-sections > details");
        assert.equal(await care.count(), 8);
        assert.equal(await content.locator("article.guide-fact").count(), 28);
        assert.equal(await content.locator("article.guide-fact:visible").count(), 0);
        const feedingPreview = care.filter({ has: page.locator("summary h3", { hasText: /^Feeding$/ }) }).locator(":scope > summary");
        const feedingText = await feedingPreview.innerText();
        for (const context of ["Mature feeding interval", "4 years and older", "Young feeding interval", "newborn to 12 months"])
          assert(feedingText.includes(context), `Collapsed Boa Feeding retains the age-specific meaning: ${context}`);
        await capture(page, "boa-care-collapsed-rows", care.first());
        const temperature = care.filter({ has: page.locator("summary h3", { hasText: "Temperature & humidity" }) });
        await keyboardToggle(page, temperature);
        assert(await temperature.locator(".guide-state-differ").count() > 0, "Sources differ textual support state retained");
        assert(await temperature.locator(".guide-position strong").count() >= 2, "Distinct source positions retained");
        await capture(page, "boa-one-care-section-expanded", temperature);
        await keyboardToggle(page, temperature, "Space");
        for (const section of await care.all()) await keyboardToggle(page, section);
        assert.equal(await content.locator("article.guide-fact:visible").count(), 28);
        assert.equal(await content.locator("article.guide-fact details.guide-disclosure li").count(), 34);
        for (const detail of await content.locator("article.guide-fact details.guide-disclosure").all()) {
          await keyboardToggle(page, detail);
          assert(await detail.locator("a").first().isVisible());
        }
        await capture(page, "boa-all-facts-and-claim-provenance-expanded", null, true);
        return { facts: 28, positions: 34, careSections: 8 };
      });
      await runCase("sources-native-keyboard-and-bibliography-retained", async () => {
        await open(page, boa + "/reference");
        const provider = page.locator(".profile-source-overview > .field-help a");
        assert.equal(await provider.count(), 1, "Saved species-provider attribution retained");
        assert.match(await provider.getAttribute("href"), /^https:\/\//);
        await provider.focus();
        await page.keyboard.press("Tab");
        await page.keyboard.press("Shift+Tab");
        assert(await provider.evaluate(element => element === document.activeElement));
        const providerGeometry = await provider.evaluate(element => ({
          height: element.getBoundingClientRect().height, outline: parseFloat(getComputedStyle(element).outlineWidth),
        }));
        assert(providerGeometry.height >= 43, "Species provider link remains an approximately 44px target");
        assert(providerGeometry.outline >= 2, "Species provider link has visible keyboard focus");
        const sources = page.locator("details.profile-reference-sources");
        assert.equal(await sources.evaluate(element => element.open), false);
        await keyboardToggle(page, sources);
        assert.equal(await sources.locator(".profile-reference-bibliography li").count(), 7);
        assert((await sources.innerText()).includes("Version 1"));
        for (const item of await sources.locator(".profile-reference-bibliography li").all()) {
          const link = item.locator("a");
          assert.match(await link.getAttribute("href"), /^https:\/\//);
          assert.equal(await link.getAttribute("target"), "_blank");
          assert((await link.getAttribute("rel")).includes("noopener"));
          assert((await item.innerText()).includes("Retrieved") && (await item.innerText()).includes("Reviewed"));
          assert(await link.isVisible());
          await link.focus();
          await page.keyboard.press("Tab");
          await page.keyboard.press("Shift+Tab");
          assert(await link.evaluate(element => element === document.activeElement));
          const geometry = await link.evaluate(element => ({ height: element.getBoundingClientRect().height, outline: parseFloat(getComputedStyle(element).outlineWidth) }));
          assert(geometry.height >= 40, "Source link remains a usable approximately 44px target");
          assert(geometry.outline >= 2, "Source link has visible keyboard focus");
        }
        await capture(page, "boa-sources-expanded", sources);
        await capture(page, "boa-sources-expanded-full", null, true);
        await keyboardToggle(page, sources, "Space");
        return { bibliographySources: 7, versionRetained: true, nativeEnterAndSpace: true, providerGeometry };
      });
      await runCase("overview-remains-concise", async () => {
        await open(page, boa);
        const overview = page.locator(".overview-reference");
        assert.equal(await overview.locator(".profile-reference-fact").count(), 3);
        assert.equal(await overview.locator("article.guide-fact, details.profile-reference-disclosure").count(), 0);
        assert(await overview.getByRole("link", { name: "Guides & Species Reference", exact: false }).isVisible());
        assert(await page.locator(".overview-care").isVisible());
        await capture(page, "boa-overview-top");
        return { glanceFacts: 3, fullFacts: 0 };
      });
      await runCase("standalone-directory-and-care-guide-rendered", async () => {
        for (const [name, route] of [
          ["directory-index", "/directory"],
          ["directory-python", "/directory/" + manifest.taxon_ids["Python regius"]],
          ["directory-python-guide", "/directory/" + manifest.taxon_ids["Python regius"] + "/care-guide"],
          ["directory-tarantula-guide", "/directory/" + manifest.taxon_ids["Avicularia avicularia"] + "/care-guide"],
        ]) {
          await open(page, route);
          assert(await page.getByRole("heading").first().isVisible());
          await capture(page, name, null, true);
        }
        return { surfaces: 4 };
      });
      await context.close();
    }
    await runCase("network-errors-and-reference-sql-write-guards", async () => {
      const guardAfter = fs.readFileSync(guardFile, "utf8");
      assert(guardAfter.startsWith(guardBefore), "Append-only server guard evidence");
      const events = guardAfter.slice(guardBefore.length).trim().split("\n").filter(Boolean).map(line => JSON.parse(line));
      result.serverGuardEvents = events;
      const authRefreshes = events.filter(event => event.type === "existing-auth-session-refresh");
      const referenceMutations = events.filter(event => event.type !== "existing-auth-session-refresh");
      for (const refresh of authRefreshes) assert.match(refresh.statement,
        /^UPDATE sessions SET last_seen_at=\?,idle_expires_at=\? WHERE session_id=\?$/,
        "Only the existing normal authentication last-seen and idle-expiry refresh is distinguished");
      assert.deepEqual(referenceMutations, [], "Zero provider socket calls and zero reference/domain SQL mutations during reference GET");
      assert.deepEqual(result.diagnostics, [], "Zero unexpected console or page errors");
      assert.deepEqual(result.externalRequests, [], "Zero outbound browser calls");
      assert.deepEqual(result.providerRequests, [], "Zero provider directory calls during normal reads");
      return { referenceOrDomainSqlWrites: 0, existingAuthenticationSessionRefreshes: authRefreshes.length,
        literalZeroSqlWrites: authRefreshes.length === 0, externalSocketCalls: 0, externalBrowserRequests: 0, errors: 0 };
    });
  } finally { await browser.close(); finish(); }
  process.stdout.write(JSON.stringify(result.totals) + "\n");
  if (result.totals.failed) process.exitCode = 1;
})().catch(error => { result.fatalError = error.stack; finish(); console.error(error); process.exitCode = 1; });
