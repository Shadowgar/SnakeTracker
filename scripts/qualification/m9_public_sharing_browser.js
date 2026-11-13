"use strict";
// Focused fictional M9 owner → visitor → revocation journey. No production address accepted.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium } = require(process.env.CARE_PLAYWRIGHT || "playwright");
const fixture = fs.realpathSync(process.env.CARE_FIXTURE);
assert.match(fixture, /^\/tmp\/carekeeper-m9-browser-[^/]+$/);
const manifest = JSON.parse(fs.readFileSync(path.join(fixture, "manifest.json"), "utf8"));
assert.equal(manifest.fictional, true);
assert.match(manifest.origin, /^http:\/\/127\.0\.0\.1:81\d\d$/);
const output = process.env.CARE_OUTPUT || path.join(fixture, "browser-evidence");
fs.mkdirSync(output, { recursive: true });
const ownerLayoutOnly = process.env.CARE_OWNER_LAYOUT_ONLY === "1";
const report = { checks: [], screenshots: [], externalRequests: [], errors: [] };

(async () => {
  const browser = await chromium.launch({ headless: true });
  const contexts = [];
  const makeContext = async () => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    contexts.push(context);
    context.setDefaultTimeout(20000);
    context.setDefaultNavigationTimeout(20000);
    await context.route("**/*", async route => {
      const url = route.request().url();
      if (!url.startsWith(manifest.origin + "/")) {
        report.externalRequests.push(url); return route.abort();
      }
      if (url.endsWith("/static/m9-axe.js")) return route.fulfill({
        contentType: "application/javascript", body: fs.readFileSync(process.env.CARE_AXE, "utf8"),
      });
      return route.continue();
    });
    const page = await context.newPage();
    page.on("pageerror", error => report.errors.push(String(error)));
    return { page, context };
  };
  try {
    const { page: owner } = await makeContext();
    const { page: visitor, context: visitorContext } = await makeContext();
    const go = (page, route) => page.goto(manifest.origin + route);
    const capture = async (page, name) => {
      await page.addScriptTag({ url: manifest.origin + "/static/m9-axe.js" });
      const result = await page.evaluate(async () => {
        await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
        const a11y = await axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        });
        return {
          viewport: innerWidth, scroll: document.documentElement.scrollWidth,
          violations: a11y.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })),
          images: [...document.querySelectorAll("main img")].map(i => ({
            width: i.getBoundingClientRect().width, height: i.getBoundingClientRect().height,
            fit: getComputedStyle(i).objectFit, naturalWidth: i.naturalWidth, naturalHeight: i.naturalHeight,
          })),
        };
      });
      report.checks.push({ name, ...result });
      assert(result.scroll <= result.viewport, name + ": horizontal overflow");
      assert.deepEqual(result.violations, [], name + ": accessibility violations");
      assert(result.images.every(i => i.naturalWidth > 0 && i.height <= 520 && i.fit === "contain"),
             name + ": image is unbounded, missing or distorted");
      const file = name + ".png";
      await page.screenshot({ path: path.join(output, file), fullPage: true });
      report.screenshots.push(file);
    };
    await go(owner, "/login");
    await owner.locator('[name="email"]').fill(manifest.email);
    await owner.locator('[name="password"]').fill(manifest.password);
    await owner.getByRole("button", { name: "Sign in", exact: true }).click();
    await owner.waitForURL(/\/home$/);
    const animal = manifest.animals.main;
    if (ownerLayoutOnly) {
      for (const width of [390, 320]) {
        await owner.setViewportSize({ width, height: 1000 });
        for (const [route, name] of [[animal + "/album", "owner-album-final"],
                                     [animal + "/sharing", "owner-sharing-final"],
                                     ["/sharing", "owner-collection-final"]]) {
          await go(owner, route); await capture(owner, name + "-" + width);
        }
      }
      assert.deepEqual(report.externalRequests, []);
      assert.deepEqual(report.errors, []);
      report.status = "passed";
      return;
    }
    await go(owner, animal);
    const primaryPhoto = await owner.locator(".profile-hero-photo").getAttribute("src");
    await go(owner, animal + "/album");
    await capture(owner, "owner-empty-album-1440");
    const upload = async caption => {
      await go(owner, animal + "/album");
      const disclosure = owner.locator("details.sharing-upload");
      if ((await disclosure.getAttribute("open")) === null) await disclosure.locator("summary").click();
      await owner.locator('[name="photo"]').setInputFiles(manifest.image);
      await owner.locator('[name="caption"]').fill(caption);
      await owner.getByRole("button", { name: "Add photo privately", exact: true }).click();
      await owner.waitForURL(/\/album\?uploaded=1$/);
    };
    await upload("Fictional Ember — original group illustration for testing");
    await upload("A quiet afternoon — fictional second album photo");
    let cards = owner.locator("[data-media-id]");
    assert.equal(await cards.count(), 2);
    const first = await cards.nth(0).getAttribute("data-media-id");
    const second = await cards.nth(1).getAttribute("data-media-id");
    const edit = async (id, caption, position, isPublic) => {
      await go(owner, animal + "/album/" + id);
      await owner.locator('[name="caption"]').fill(caption);
      await owner.locator('[name="position"]').fill(String(position));
      await owner.locator('[name="is_public"]').setChecked(isPublic);
      await owner.getByRole("button", { name: "Save photo choices", exact: true }).click();
      await owner.waitForURL(/\/album\?saved=1$/);
    };
    await edit(first, "Ember in the leaves · fictional illustration", 2, true);
    await edit(second, "Afternoon portrait · fictional illustration", 1, true);
    assert.equal(await owner.locator("[data-media-id]").first().getAttribute("data-media-id"), second);
    await go(owner, "/sharing");
    await owner.locator('[name="title"]').fill("The Woodland Collection");
    await owner.locator('[name="slug"]').fill("woodland");
    await owner.locator('[name="description"]').fill("A small collection of remarkable companions. Fictional qualification data.");
    await owner.locator('[name="enabled"]').check();
    await owner.getByRole("button", { name: "Save sharing choices", exact: true }).click();
    await owner.waitForURL(/\/sharing\?saved=1$/);
    const collection = await owner.locator("[data-public-url]").getAttribute("data-public-url");
    await go(visitor, collection);
    assert.match(await visitor.locator("main").innerText(), /No Animals shared yet/);
    await capture(visitor, "public-empty-collection-1440");
    const configure = async (route, title, slug, cover = "") => {
      await go(owner, route + "/sharing");
      await owner.locator('[name="title"]').fill(title);
      await owner.locator('[name="slug"]').fill(slug);
      await owner.locator('[name="species"]').fill("Deliberately shared species label");
      await owner.locator('[name="description"]').fill("A curious observer with a quiet presence. This is a fictional public profile.");
      await owner.locator('[name="cover_media_id"]').selectOption(cover);
      await owner.locator('[name="is_public"]').check();
      await owner.getByRole("button", { name: "Save public profile choices", exact: true }).click();
      await owner.waitForURL(/\/sharing\?saved=1$/);
      return owner.locator("[data-public-url]").getAttribute("data-public-url");
    };
    const published = await configure(animal, "Ember", "ember", first);
    const missing = await configure(manifest.animals.missing, "Moss", "moss");
    const long = await configure(manifest.animals.long,
      "An extraordinarily long fictional Animal name beside the woodland canopy and the quiet fern garden", "canopy");
    for (const width of [1440, 390, 320]) {
      await owner.setViewportSize({ width, height: 1000 });
      await visitor.setViewportSize({ width, height: 1000 });
      for (const [route, name] of [[animal + "/album", "owner-album"],
                                    [animal + "/sharing", "owner-sharing"], ["/sharing", "owner-collection"]]) {
        await go(owner, route); await capture(owner, name + "-" + width);
      }
      for (const [route, name] of [[published, "public-animal"], [collection, "public-collection"],
                                    [missing, "public-no-photo"], [long, "public-long-name"]]) {
        const response = await go(visitor, route); assert.equal(response.status(), 200);
        assert.match(response.headers()["cache-control"], /no-store/);
        await capture(visitor, name + "-" + width);
      }
    }
    await go(visitor, published);
    const mediaUrl = await visitor.locator("main img").first().getAttribute("src");
    assert(mediaUrl.startsWith("/m/"));
    const html = await visitor.content();
    for (const secret of [animal.split("/").at(-1), "Mixed Household", "/attachments/", "/animals/", "/logout"]) {
      assert(!html.includes(secret), "visitor leaked " + secret);
    }
    assert.equal((await visitorContext.request.get(manifest.origin + mediaUrl)).status(), 200);
    await edit(first, "Ember in the leaves · fictional illustration", 2, false);
    assert.equal((await visitorContext.request.get(manifest.origin + mediaUrl)).status(), 404);
    assert.equal((await visitorContext.request.head(manifest.origin + mediaUrl)).status(), 404);
    await go(owner, animal + "/sharing");
    await owner.locator('[name="is_public"]').uncheck();
    await owner.getByRole("button", { name: "Save public profile choices", exact: true }).click();
    await owner.waitForURL(/\/sharing\?saved=1$/);
    assert.equal((await visitorContext.request.get(manifest.origin + published)).status(), 404);
    await go(owner, animal);
    assert.equal(await owner.locator(".profile-hero-photo").getAttribute("src"), primaryPhoto);
    report.checks.push({ name: "real-upload-organize-publication-anonymous-delivery-revocation-primary-unchanged", status: "passed" });
    assert.deepEqual(report.externalRequests, []);
    assert.deepEqual(report.errors, []);
    report.status = "passed";
  } finally {
    if (report.status !== "passed") {
      report.failurePages = [];
      for (const context of contexts) for (const page of context.pages()) {
        report.failurePages.push({ url: page.url(), text: await page.locator("main").innerText({ timeout: 1000 }).catch(() => "") });
      }
    }
    fs.writeFileSync(path.join(output, ownerLayoutOnly ? "owner-mobile-results.json" : "browser-results.json"), JSON.stringify(report, null, 2) + "\n");
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
