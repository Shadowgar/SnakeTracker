"use strict";

// Qualification uses only a separately seeded fictional SQLite fixture.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require(process.env.M66B_PLAYWRIGHT_MODULE || "playwright");

const root = path.resolve(__dirname, "../..");
const manifestPath = process.env.M66B_MANIFEST || path.join(
  fs.readFileSync("/tmp/m66b-correction-browser-path", "utf8").trim(), "browser-manifest.json"
);
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const origin = process.env.M66B_ORIGIN || "http://127.0.0.1:8098";
const parsedOrigin = new URL(origin);
assert(["127.0.0.1", "localhost"].includes(parsedOrigin.hostname));
assert.equal(parsedOrigin.protocol, "http:");
assert.equal(parsedOrigin.port, "8098");
assert.equal(parsedOrigin.pathname, "/");
assert.equal(parsedOrigin.username + parsedOrigin.password + parsedOrigin.search + parsedOrigin.hash, "");
assert.match(fs.realpathSync(manifest.database), /^\/tmp\/m66b-browser\.[^/]+\/snaketracker\.sqlite3$/);
assert.equal(path.dirname(fs.realpathSync(manifestPath)), path.dirname(fs.realpathSync(manifest.database)));
const evidence = path.resolve(process.env.M66B_EVIDENCE || path.join(
  root, "docs/evidence/m6.6-species-aware-husbandry/b-corrections"
));
const axePath = process.env.M66B_AXE || "/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js";
const executablePath = process.env.M66B_CHROMIUM || "/home/rocco/.cache/ms-playwright/chromium-1208/chrome-linux/chrome";
const runId = new Date().toISOString().replace(/[^0-9]/g, "");
const cases = [];
const captures = [];
const diagnostics = [];
const blockedExternalRequests = [];
const resultPath = path.join(evidence, `browser-qualification-${runId}.json`);
const sourceCommit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
const dirtySource = Boolean(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim());
fs.mkdirSync(path.join(evidence, "screenshots"), { recursive: true });
const species = {
  snake: "Python regius", lizard: "Pogona vitticeps", spider: "Avicularia avicularia", scorpion: "Pandinus imperator",
};
const records = group => [{ taxon_id: manifest.taxon_ids[species[group]], group,
  scientific_name: species[group], common_name: null, reference_image_available: false }];
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function writeResult() {
  const result = {
    runId, sourceCommit, dirtySource, origin, fictionalDataOnly: true,
    fixtureGuard: "loopback:8098; real database and manifest in /tmp/m66b-browser.*",
    providerResponses: "intercepted locally; no live provider search or image fetch",
    phase: process.env.M66B_BROWSER_PHASE || "full", cases, captures, diagnostics, blockedExternalRequests,
    totals: { cases: cases.length, passed: cases.filter(item => item.status === "passed").length,
      failed: cases.filter(item => item.status === "failed").length, screenshots: captures.length,
      axeViolations: captures.reduce((sum, item) => sum + item.axeViolations.length, 0),
      overflowCaptures: captures.filter(item => item.overflow.scrollWidth > item.overflow.viewportWidth + 1).length,
      consoleErrors: diagnostics.filter(item => item.type === "console").length,
      expectedInjectedErrors: diagnostics.filter(item => item.expected).length,
      unexpectedErrors: diagnostics.filter(item => !item.expected).length,
      externalRequestsBlocked: blockedExternalRequests.length },
  };
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2) + "\n");
  return result;
}

async function capture(page, viewport, name) {
  await page.addScriptTag({ path: axePath });
  const axeViolations = await page.evaluate(async () => (await window.axe.run(document)).violations.map(item => ({
    id: item.id, impact: item.impact, nodes: item.nodes.map(node => node.target),
  })));
  const overflow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth }));
  const filename = `${runId}-${viewport}-${name}.png`;
  await page.screenshot({ path: path.join(evidence, "screenshots", filename), fullPage: true });
  captures.push({ viewport, name, screenshot: `screenshots/${filename}`, axeViolations, overflow });
  assert.deepEqual(axeViolations, [], `${name}: axe violations`);
  assert(overflow.scrollWidth <= overflow.viewportWidth + 1, `${name}: horizontal overflow`);
}

async function runCase(state, viewport, name, action, expectedErrors = false) {
  state.caseName = name;
  state.expectedErrors = expectedErrors;
  const started = Date.now();
  try {
    const facts = await action();
    cases.push({ viewport, name, status: "passed", durationMs: Date.now() - started, facts: facts || {} });
  } catch (error) {
    cases.push({ viewport, name, status: "failed", durationMs: Date.now() - started, error: error.message });
    console.error(`${viewport} ${name}: ${error.message}`);
  }
  writeResult();
}

async function open(page, route) {
  const response = await page.goto(`${origin}${route}`, { waitUntil: "networkidle" });
  assert.equal(response.status(), 200, `${route}: HTTP ${response.status()}`);
}

async function newAnimal(page, state, group, label) {
  state.mode = "known";
  await open(page, "/animals/new");
  await page.locator('select[name="animal_type"]').selectOption(group);
  await page.locator('input[name="name"]').fill(`Fictional ${label} ${runId.slice(-9)}`);
}

async function selectSpecies(page, state, group) {
  state.mode = "known";
  await page.locator('[role="combobox"]').fill(species[group]);
  await page.locator('[data-taxon-results] [role="option"]').first().waitFor();
  await page.locator('[role="combobox"]').press("ArrowDown");
  await page.locator('[role="combobox"]').press("Enter");
  assert.equal(await page.locator('input[data-taxon-id]').inputValue(), manifest.taxon_ids[species[group]]);
}

async function createAnimal(page, linked) {
  const submit = page.getByRole("button", { name: "Create animal", exact: true });
  await Promise.all([page.waitForURL(url => /^\/animals\/[0-9a-f-]+$/.test(url.pathname)), submit.click()]);
  const text = await page.locator(".overview-reference").innerText();
  assert(text.includes(linked ? "Reviewed reference guidance" : "Link a species to see reviewed guidance."));
  return new URL(page.url()).pathname;
}

function parseCsv(value) {
  // All numeric/identity columns used here are fixture-controlled; handle standard escaped CSV.
  return value.trim().split(/\r?\n/).map(line => Array.from(line.matchAll(/(?:^|,)("(?:[^"]|"")*"|[^,]*)/g), match =>
    match[1].startsWith('"') ? match[1].slice(1, -1).replaceAll('""', '"') : match[1]));
}

async function measurementRow(page, animalRoute) {
  const response = await page.request.get(`${origin}${animalRoute}/measurements.csv`);
  assert.equal(response.status(), 200);
  const [header, ...rows] = parseCsv(await response.text());
  const objects = rows.map(row => Object.fromEntries(header.map((key, index) => [key, row[index]])));
  return objects.find(row => row.Kind === "length");
}

async function main() {
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      const label = viewport.width === 1440 ? "desktop-1440x900" : "mobile-390x844";
      const context = await browser.newContext({ viewport, bypassCSP: true, serviceWorkers: "block" });
      const state = { mode: "known", caseName: "login", expectedErrors: false, searchStarted: 0, imageDelay: false };
      await context.route("**/*", async route => {
        const url = new URL(route.request().url());
        if (url.origin !== parsedOrigin.origin) {
          blockedExternalRequests.push({ viewport: label, case: state.caseName, origin: url.origin });
          await route.abort("blockedbyclient");
          return;
        }
        if (url.pathname === "/api/directory/search") {
          state.searchStarted += 1;
          const mode = state.mode;
          const group = url.searchParams.get("group");
          if (mode === "timeout") return route.abort("timedout");
          if (mode === "outage") return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Injected provider unavailable"}' });
          if (mode === "throttle") return route.fulfill({ status: 429, contentType: "application/json", body: '{"detail":"Injected provider throttle"}' });
          if (mode === "malformed") return route.fulfill({ status: 200, contentType: "application/json", body: '{"records":' });
          let payload = { records: records(group), message: "Locally intercepted fictional qualification result." };
          if (mode === "none") payload = { records: [], message: "No matching species. You can keep a manual species entry." };
          if (mode === "oversized") payload = { records: Array.from({ length: 1000 }, () => records(group)[0]) };
          if (mode === "search-race") {
            const first = url.searchParams.get("q").startsWith("Old");
            if (first) await sleep(650);
            payload = first ? { records: records(group), message: "Old response must be discarded" } : { records: [], message: "Newest query: manual entry is available." };
          }
          try { await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) }); } catch (_) { /* Aborted stale request. */ }
          return;
        }
        if (/\/api\/directory\/[^/]+\/reference-image$/.test(url.pathname)) {
          const delayed = state.imageDelay;
          if (delayed) await sleep(650);
          return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(delayed ? {
            available: true, url: "/static/species-references/boa-constrictor.webp", creator: "Fictional image response", license_code: "cc-by",
          } : { available: false }) });
        }
        if (/\/api\/directory\/[^/]+\/identity-suggestions$/.test(url.pathname)) {
          return route.fulfill({ status: 200, contentType: "application/json", body: '{"morphs":[],"genetics":[]}' });
        }
        await route.continue();
      });
      const page = await context.newPage();
      page.setDefaultTimeout(9000);
      page.on("pageerror", error => diagnostics.push({ viewport: label, case: state.caseName, type: "pageerror", expected: false, message: error.message }));
      page.on("console", message => {
        if (message.type() === "error") diagnostics.push({ viewport: label, case: state.caseName, type: "console", expected: state.expectedErrors && message.text().startsWith("Failed to load resource:"), message: message.text() });
      });
      await open(page, "/login");
      await page.locator('input[name="email"]').fill(process.env.M66B_EMAIL || "guide-review@example.test");
      await page.locator('input[name="password"]').fill(process.env.M66B_PASSWORD || "fictional-guide-review-password");
      await Promise.all([page.waitForURL(url => url.pathname !== "/login"), page.locator('button[type="submit"]').click()]);

      for (const group of Object.keys(species)) {
        for (const mode of ["none", "outage", "timeout", "throttle", "malformed", "oversized"]) {
          await runCase(state, label, `manual-${group}-${mode}`, async () => {
            await newAnimal(page, state, group, `${group} ${mode}`);
            state.mode = mode;
            const started = state.searchStarted;
            const text = `Fictional unlisted ${group} ${mode}`;
            await page.locator('input[name="species"]').fill(text);
            await page.waitForFunction(() => {
              const status = document.querySelector("[data-taxon-status]").textContent;
              return status.length > 0 && !status.includes("Searching");
            });
            assert(state.searchStarted > started);
            assert(await page.locator('[data-taxon-results] [role="option"]').count() <= 20);
            await page.locator('[data-manual-species]').click();
            assert.equal(await page.locator('input[data-taxon-id]').inputValue(), "");
            assert.equal(await page.locator('input[name="species"]').inputValue(), text);
            assert.equal(await page.locator('input[name="photo_preference"]').inputValue(), "none");
            if (group === "spider" && mode === "none") await capture(page, label, "manual-spider-form");
            const animalRoute = await createAnimal(page, false);
            if (group === "spider" && mode === "none") await capture(page, label, "manual-spider-profile");
            return { animalType: group, simulatedProviderResponse: mode, savedUnlinked: true, manualSpeciesPreserved: true };
          }, ["outage", "timeout", "throttle"].includes(mode));
        }
        await runCase(state, label, `selected-${group}-without-image`, async () => {
          await newAnimal(page, state, group, `${group} selected`);
          await selectSpecies(page, state, group);
          await page.locator('[data-reference-photo-copy]').getByText("No licensed species reference image", { exact: false }).waitFor();
          assert.equal(await page.locator('input[name="photo_preference"]').inputValue(), "none");
          const animalRoute = await createAnimal(page, true);
          assert((await page.locator(".overview-reference").innerText()).includes(species[group]));
          if (group === "spider") await capture(page, label, "selected-spider-linked-profile");
          return { savedAlreadyLinked: true, referenceImageRequired: false, species: species[group] };
        });
      }

      await runCase(state, label, "selection-cleared-by-species-text-edit", async () => {
        await newAnimal(page, state, "snake", "text change");
        await selectSpecies(page, state, "snake");
        state.mode = "none";
        await page.locator('input[name="species"]').fill("Fictional edited manual species");
        assert.equal(await page.locator('input[data-taxon-id]').inputValue(), "");
        await page.locator('[data-manual-species]').click();
        await createAnimal(page, false);
        return { staleTaxonCleared: true, savedUnlinked: true };
      });
      await runCase(state, label, "selection-cleared-by-animal-type-change", async () => {
        await newAnimal(page, state, "snake", "type change");
        await selectSpecies(page, state, "snake");
        state.mode = "none";
        await page.locator('select[name="animal_type"]').selectOption("spider");
        assert.equal(await page.locator('input[data-taxon-id]').inputValue(), "");
        await page.locator('[data-manual-species]').click();
        await createAnimal(page, false);
        return { staleTaxonCleared: true, savedUnlinked: true, selectedType: "spider" };
      });
      await runCase(state, label, "stale-search-response-discarded", async () => {
        await newAnimal(page, state, "snake", "search race");
        state.mode = "search-race";
        const oldRequest = page.waitForRequest(request => new URL(request.url()).searchParams.get("q") === "Old selected query");
        await page.locator('input[name="species"]').fill("Old selected query");
        await oldRequest;
        await page.locator('input[name="species"]').fill("Newest manual query");
        await page.locator('[data-taxon-status]').getByText("Newest query", { exact: false }).waitFor();
        await sleep(700);
        assert.equal(await page.locator('input[data-taxon-id]').inputValue(), "");
        assert.equal(await page.locator('[data-taxon-results] [role="option"]').count(), 0);
        assert.equal(await page.locator('input[name="species"]').inputValue(), "Newest manual query");
        return { oldestResponseDiscarded: true };
      });
      await runCase(state, label, "stale-reference-image-response-discarded", async () => {
        await newAnimal(page, state, "snake", "image race");
        state.imageDelay = true;
        const oldImageRequest = page.waitForRequest(request => request.url().endsWith("/reference-image"));
        await selectSpecies(page, state, "snake");
        await oldImageRequest;
        state.mode = "none";
        await page.locator('input[name="species"]').fill("Fictional changed after image request");
        await page.locator('[data-manual-species]').click();
        await sleep(850);
        state.imageDelay = false;
        assert.equal(await page.locator('input[data-taxon-id]').inputValue(), "");
        assert.equal(await page.locator('input[name="photo_preference"]').inputValue(), "none");
        assert(await page.locator('[data-reference-photo-image]').isHidden());
        return { staleImageDiscarded: true };
      });

      await runCase(state, label, "edit-retains-explicit-selected-link", async () => {
        await newAnimal(page, state, "snake", "edit link");
        await page.locator('input[name="species"]').fill("Fictional manual identity");
        await page.locator('[data-manual-species]').click();
        const route = await createAnimal(page, false);
        await open(page, `${route}/edit`);
        await selectSpecies(page, state, "snake");
        await Promise.all([page.waitForURL(url => url.pathname === route), page.getByRole("button", { name: "Save profile", exact: true }).click()]);
        assert((await page.locator(".overview-reference").innerText()).includes("Reviewed reference guidance"));
        await open(page, `${route}/edit`);
        await page.locator('input[name="name"]').fill(`Fictional retained edit ${runId.slice(-9)}`);
        await Promise.all([page.waitForURL(url => url.pathname === route), page.getByRole("button", { name: "Save profile", exact: true }).click()]);
        assert((await page.locator(".overview-reference").innerText()).includes("Python regius"));
        return { selectionSavedOnEdit: true, laterIdentityEditRetainedLink: true };
      });
      await runCase(state, label, "legacy-unlinked-inline-confirmation", async () => {
        await newAnimal(page, state, "snake", "legacy inline");
        await page.locator('input[name="species"]').fill("Python regius");
        await page.locator('[data-manual-species]').click();
        const route = await createAnimal(page, false);
        assert(await page.locator(".overview-reference [data-taxon-combobox]").isVisible());
        await selectSpecies(page, state, "snake");
        await Promise.all([page.waitForURL(url => url.pathname === route), page.getByRole("button", { name: "Confirm species link", exact: true }).click()]);
        assert((await page.locator(".overview-reference").innerText()).includes("Reviewed reference guidance"));
        return { manualFreeTextDidNotAutoLink: true, confirmedInsideProfile: true };
      });
      if (process.env.M66B_BROWSER_PHASE === "species") {
        await context.close();
        continue;
      }

      const profiles = [
        ["linked-python-direct-guide", manifest.animal_urls.with_guide, ["30–32°C", "Royal Veterinary College", "Feeding"]],
        ["linked-lizard-separate-disagreements", manifest.animal_urls.disagreement, ["Sources differ", "35–40°C", "38–42°C", "Royal Veterinary College", "RSPCA"]],
        ["linked-boa-direct-guide", manifest.animal_urls.boa_guide, ["Boa constrictor", "Royal Veterinary College", "ReptiFiles", "55–75%", "Sources differ"]],
        ["linked-no-reviewed-guide", manifest.animal_urls.linked_without_guide, ["No reviewed species guidance available yet."]],
        ["unlinked-honest-reference", manifest.animal_urls.unlinked, ["Link a species to see reviewed guidance.", "Confirm species link"]],
      ];
      for (const [name, route, requiredText] of profiles) await runCase(state, label, name, async () => {
        assert(route, `${name}: manifest URL is required`);
        await open(page, route);
        const reference = await page.locator(".overview-reference").textContent();
        const provenance = await page.locator(".overview-reference").textContent();
        for (const text of requiredText) {
          const visibleText = ["Royal Veterinary College", "RSPCA", "ReptiFiles"].includes(text) ? provenance : reference;
          assert(visibleText.includes(text), `${name}: missing ${text}`);
        }
        assert(await page.locator(".overview-identity").isVisible());
        assert(await page.locator(".overview-care").isVisible());
        if (name.includes("direct-guide") || name.includes("disagreements")) {
          const facts = page.locator(".overview-reference article.guide-fact");
          const expectedFacts = { "linked-python-direct-guide": 6, "linked-lizard-separate-disagreements": 7, "linked-boa-direct-guide": 28 }[name];
          assert.equal(await facts.count(), expectedFacts, "Every sourced contextual fact must appear directly");
          const sections = page.locator(".overview-reference details.profile-reference-disclosure");
          assert(await sections.count(), "Detailed reference must be expandable on the same page");
          assert.equal(await facts.locator(":visible").count(), 0, "Guide defaults must stay compact");
          for (const section of await sections.all()) await section.locator(":scope > summary").click();
          for (const fact of await facts.all()) {
            assert(await fact.locator(".guide-value, .guide-position strong").first().isVisible(), "Guide claim missing after same-page expansion");
          }
          for (const section of await sections.all()) await section.locator(":scope > summary").click();
        }
        if (name === "linked-no-reviewed-guide") assert.equal(await page.locator(".profile-reference-fact").count(), 0);
        await capture(page, label, name);
        return { guidanceVisibleOnProfile: name.includes("direct-guide"), expectedTextVerified: requiredText };
      });
      await runCase(state, label, "directory-remains-usable", async () => {
        state.mode = "known";
        await open(page, "/directory");
        assert(await page.locator("main input").count());
        await open(page, `/directory/${manifest.taxon_ids["Python regius"]}`);
        assert((await page.locator("main").innerText()).includes("Python regius"));
        await capture(page, label, "directory-species");
        return { directoryAndTaxonDetailAccessible: true };
      });

      await runCase(state, label, "precise-length-record-correct-export", async () => {
        await newAnimal(page, state, "snake", "exact length");
        await page.locator('input[name="species"]').fill("Fictional length specimen");
        await page.locator('[data-manual-species]').click();
        const route = await createAnimal(page, false);
        const animalId = route.split("/").at(-1);
        await open(page, `${route}/lengths/new`);
        assert.equal(await page.locator('input[name="length_value"]').getAttribute("inputmode"), "decimal");
        assert.equal(await page.locator('input[name="length_value"]').getAttribute("step"), "0.1");
        await page.locator('select[name="length_unit"]').selectOption("in");
        await page.locator('input[name="length_value"]').fill("48.5");
        await page.locator('input[name="occurred_at"]').fill("2026-10-01T06:00");
        await capture(page, label, "length-48-5-in-form");
        await Promise.all([page.waitForURL(url => url.pathname === route), page.getByRole("button", { name: "Record length", exact: true }).click()]);
        assert((await page.locator(".overview-care").innerText()).includes("48.5 in"));
        await capture(page, label, "length-48-5-in-profile");
        await open(page, `${route}/measurements`);
        assert((await page.locator("#effective-history").innerText()).includes("48.5 in"));
        await capture(page, label, "length-48-5-in-history");
        await open(page, `${route}/analytics`);
        assert((await page.locator(".chart-card").innerText()).includes("48.5 in"));
        const data = await (await page.request.get(`${origin}/api/v1/animals/${animalId}/analytics/measurements`)).json();
        const point = data.points.find(item => item.kind === "length");
        assert.equal(point.value, 1231.9);
        assert.equal(point.unit, "mm");
        assert.equal(point.display_value, "48.5");
        assert.equal(point.display_unit, "in");
        await capture(page, label, "length-48-5-in-trends");
        const row = await measurementRow(page, route);
        assert.equal(row["Canonical value"], "1231900");
        assert.equal(row["Canonical unit"], "um");
        assert.equal(row["Entered value"], "48.5");
        assert.equal(row["Entered unit"], "in");
        assert.equal(row["Schema version"], "2");
        await open(page, `${route}/events/${row["Event ID"]}/correct`);
        assert.equal(await page.locator('input[name="length_value"]').inputValue(), "48.5");
        assert.equal(await page.locator('select[name="length_unit"]').inputValue(), "in");
        await page.locator('select[name="length_unit"]').selectOption("cm");
        assert.equal(await page.locator('input[name="length_value"]').inputValue(), "48.5", "Unit-only correction must preserve the entered number");
        await page.locator('input[name="length_value"]').fill("48.5");
        assert((await page.locator('[data-length-original]').innerText()).includes("48.5 cm"));
        await capture(page, label, "length-correction-48-5-cm");
        await Promise.all([page.waitForURL(url => url.pathname.endsWith("/timeline")), page.getByRole("button", { name: "Save correction", exact: true }).click()]);
        assert((await page.locator("#effective-history").innerText()).includes("48.5 cm"));
        assert(!(await page.locator("#effective-history").innerText()).includes("48.5 in"));
        const corrected = await measurementRow(page, route);
        assert.equal(corrected["Canonical value"], "485000");
        assert.equal(corrected["Entered value"], "48.5");
        assert.equal(corrected["Entered unit"], "cm");
        assert.equal(corrected["Root event ID"], row["Event ID"]);
        assert.equal(corrected["Target event ID"], row["Event ID"]);
        await open(page, route);
        assert((await page.locator(".overview-care").innerText()).includes("48.5 cm"));
        await capture(page, label, "length-corrected-profile");
        return { entered: "48.5 in", canonicalChartMillimetres: 1231.9, canonicalExportMicrometres: 1231900,
          corrected: "48.5 cm", correctedExportMicrometres: 485000, rootIdentityPreserved: true, unitOnlyCorrectionPreservesEnteredNumber: true };
      });
      await runCase(state, label, "length-excess-precision-accessible-alert", async () => {
        await open(page, `${manifest.animal_urls.with_guide}/lengths/new`);
        await page.locator('select[name="length_unit"]').selectOption("mm");
        await page.locator('input[name="length_value"]').fill("12.25");
        await page.locator('input[name="occurred_at"]').fill("2026-10-01T06:00");
        const response = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/lengths"));
        await page.getByRole("button", { name: "Record length", exact: true }).click();
        assert.equal((await response).status(), 422);
        await page.getByRole("alert").waitFor();
        assert((await page.getByRole("alert").innerText()).length > 0);
        assert.equal(await page.locator('input[name="length_value"]').inputValue(), "12.25");
        await capture(page, label, "length-excess-precision-alert");
        return { status: 422, errorRole: "alert", submittedValuePreserved: true };
      }, true);
      await context.close();
    }
  } finally {
    await browser.close();
    const result = writeResult();
    console.log(JSON.stringify({ evidence: resultPath, ...result.totals }));
    if (result.totals.failed || result.totals.unexpectedErrors || blockedExternalRequests.length) process.exitCode = 1;
  }
}

main().catch(error => { diagnostics.push({ type: "fatal", expected: false, message: error.stack }); writeResult(); console.error(error); process.exitCode = 1; });
