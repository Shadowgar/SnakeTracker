# M6.6-A — Universal Species Directory

Status: implementation-qualified September 14, 2026; owner review pending

Base revision: `306f465623c50f8a24513975fa85b2104d88d82d`

Owner-review correction base: `d3e33981f9850755f710e4e85f34242b7df9b7f2`

Branch: `phase6.6/universal-species-directory`

Requirements: `R-086`–`R-090`

Architecture: [ADR-0043](../../../adr/0043-universal-species-directory.md)

## Evidence index

- [Provider and licensing audit](provider-audit.md)
- [Owner design source and visual-fidelity audit](../../../ux/owner-design/README.md)
- [Reference-image provider policy](../../../ux/owner-design/reference-image-provider-policy.md)
- [Owner-fidelity browser results](owner-fidelity-qualification.json)
- [ADR-0043](../../../adr/0043-universal-species-directory.md)
- [Browser results](browser-qualification.partial.json) and
  [provider-outage results](browser-outage-qualification.json)
- [Autocomplete performance](autocomplete-performance.json)
- [Owner-review screenshots](screenshots/)

## Architecture and behavior

The global relational directory owns Care Keeper taxon UUIDs, normalized common/scientific/
synonym names, group and classification fields, provider mappings/provenance, refresh time, and
licence-screened image metadata. A provider ID is never the primary identity. Household facts are
kept separate: keeper-confirmed `animal.taxon_linked` and
`animal.reference_image_preference_changed` v1 events link an Animal and retain its explicit image
choice, while immutable
`enclosure.plant_added`, `enclosure.plant_profile_changed`, and `enclosure.plant_removed` v1 events
own the lifecycle of a plant instance in exactly one Enclosure. Both projections are
household-scoped; neither rewrites registration, profile, or global reference history.

The selected discovery adapter is iNaturalist. Search is limited to two-to-100 normalized
characters and one of snake, lizard, spider, scorpion, or plant. The client waits 320 ms, cancels
superseded requests, deduplicates the active query, and supports arrow keys, Enter, and Escape with
combobox/listbox semantics. The service reads its 30-day local cache first. Provider calls use a
fixed HTTPS origin, a three-second timeout, no automatic interactive retry, a 256 KiB response
limit, and JSON/schema/string/group/rank validation. It sends only query text and group—not Care
Keeper identity, household, Animal, care, enclosure, financial, attachment, or account data.

An outage, timeout, `429`, malformed or oversized response, quota failure, and no result are normal
product states. Fresh cache avoids the provider; stale cache is displayed as a saved result; no
cache leaves manual species entry usable. Animal profile reads are local-only. An Enclosure-first
Add Plant flow can link a plant taxon or save a manual identity, label, quantity, optional date,
and notes; removing it preserves immutable history and removes it only from the effective active
roster. Watering, bioactive behavior, care guidance, schedules, and Today/Calendar integration
remain deferred.

Eligible CC0, CC BY, CC BY-SA, CC BY-NC, and CC BY-NC-SA reference images are global Directory
assets, not household
attachments. Care Keeper fetches only allow-listed iNaturalist HTTPS image origins server-side,
rejects redirects, applies a three-second timeout and 10 MiB response cap, requires JPEG/PNG/WebP,
decodes under 25-megapixel/8192-pixel limits, normalizes to WebP, stores checksum/cache metadata,
and revalidates the checksum on local delivery. Unknown or revoked licences, unsafe origins,
timeouts, invalid/oversized content, and unavailable cache bytes resolve to the placeholder. Keeper
pages contain only the authenticated same-origin image route; CSP remains `img-src 'self'`.

Plant reference imagery reuses that same cache and security boundary. An eligible linked taxon is
shown automatically on Plant Directory detail, Enclosure Plant detail, and compact Enclosure roster
thumbnails, with source/licence/creator attribution and a species-reference label. Manual plants and
taxa without eligible or verified bytes use a semantic leaf placeholder. No Plant attachment system,
household preference event, hotlink, or new provider fetcher was introduced.

The keeper may opt into or decline a species reference per Animal. The existing attachment-backed
personal photo always wins and remains discoverable as **Add photo**, **Add my animal's photo**, or
**Change photo**. Uploading one does not delete global cache metadata. Morph/variant and
Genetics/lineage are explained as optional individual facts under progressive disclosure. Exact
previous values are suggested only for the same household and linked Care Keeper taxon, remain
free-text and explicitly selected, and are never inferred, normalized, or erased by species choice.

Owner correction #3 traced the apparently reverted autocomplete to stale asset identity rather
than the corrected layout rule: `base.html` still requested `/static/app.css?v=m65-c1`, while shell
cache `v5` precached `/static/app.css?v=m61-corrections`. The correction advances CSS, PWA bootstrap,
species-directory JavaScript, and service-worker registration to `m66-a-owner-c3`; the shell cache is
now `snaketracker-shell-m66-a-owner-c3`, installs those exact URLs, calls `skipWaiting`, claims
clients, and removes all older prefix-matching generations. The new-animal diamond was literal
template content; it is replaced by the entered Animal's initial over the existing type-specific
fallback treatment. Selected-image, selected-without-image, and manual-entry copy are now mutually
accurate states.

iNaturalist taxon `32093` explains the formerly reported Boa placeholder: its current default photo
`588689904` is `CC BY-NC`. The owner-confirmed noncommercial policy now permits that licence, so the
photo is selected after its provider metadata, hostname, bytes, dimensions, decoder, and checksum
pass the existing validation boundary. Its creator, source, provider record, licence code, and
licence URL remain cached for attribution and later business-model review.

## Owner visual-fidelity reset and guaranteed imagery

The owner-supplied design board is preserved byte-for-byte at
[care-keeper-owner-design-board.png](../../../ux/owner-design/care-keeper-owner-design-board.png),
with its checksum and authority recorded in the adjacent README. The completed
[screen-by-screen audit](../../../ux/owner-design/visual-fidelity-audit.md) maps the board's Today,
Animals, profile, Calendar, Quick Log, Enclosures, desktop shell, and onboarding principles to the
implemented product. This bounded reset restores image-led collection cards, compact mobile
navigation and actions, profile hero hierarchy, visual enclosure rows, and a two-stage Quick Log
flow without changing event or household semantics.

Every animal presentation now resolves through the same hierarchy: keeper photo, licensed species
photograph, reviewed species illustration, then a local biological-group illustration. The four
last-resort snake, lizard, spider, and scorpion illustrations are checked-in WebP assets generated
specifically for Care Keeper; their prompt, mode, dimensions, and non-photographic purpose are
recorded with the assets. They are visual group fallbacks, never a false claim about the animal's
species or individual appearance. A keeper upload immediately becomes primary and carries no
provider credit.

The image provider cascade is iNaturalist, Wikimedia Commons, then GBIF. It achieved verified local
photographic coverage for Ball Python, Boa Constrictor, Corn Snake, Kingsnake, Leopard Gecko,
Crested Gecko, Bearded Dragon, Bold Jumping Spider, a representative tarantula, and Emperor
Scorpion. The Boa result is the specifically requested iNaturalist photo `588689904` under
CC BY-NC. The full provider/creator/licence/source metadata for all ten results is retained in
[owner-fidelity-qualification.json](owner-fidelity-qualification.json). Major reference-image
presentations show a tiny readable attribution line immediately below the image; dense linked cards
defer full credit to the profile/detail view.

The isolated ARM64 browser runtime was
`/tmp/carekeeper-m66a-fidelity-runtime.wg2eTc`, with its own database, attachments, and reference
cache. At 390×844 it captured Today, Animals, the attributed Animal profile, Calendar, Quick Log,
and Enclosures; at 1440×900 it captured Today, Animals, the attributed profile, and Enclosures. All
ten captures had no horizontal overflow, zero axe violations, zero application console diagnostics,
zero page errors, and zero request failures. Every response retained `script-src 'self'` and
`img-src 'self'`; CSP and the downloader's SSRF, redirect, decode, byte, pixel, and dimension
controls were not weakened.

## Deterministic automated qualification

The exact authoritative path `uv sync --frozen` followed by `./scripts/quality/check.sh` passed on
September 14, 2026:

- formatting, Ruff, architecture freeze, documentation links, strict mypy, Compose validation,
  generated-artifact checks, dependency audit, and diff checks passed;
- 676 tests passed, including deterministic five-group, common/scientific/synonym, filter,
  provider-ID separation, legacy/change/idempotency/isolation, accepted-name, cache/outage,
  timeout/`429`/malformed/oversized, licence, image SSRF/redirect/decode/dimension/integrity,
  keeper image preference, personal-photo priority, identity-suggestion isolation, migration,
  backup, and replay coverage;
- total coverage reached 92.57 percent, with 94.45-percent line and 85.08-percent branch coverage,
  passing the enforced 90-percent total and 85-percent branch gates; and
- the dependency audit reported no known vulnerabilities.

The deterministic browser/API performance test also makes 20 authenticated cached autocomplete
requests and requires p95 below 250 ms. Native Chromium correction qualification measured a
separate 50-call sample at 33.1 ms p95 (15.3 ms median, 70.3 ms maximum) on the isolated ARM64
runtime.

## Browser, responsive, and accessibility qualification

One disposable runtime at `/tmp/carekeeper-m66-a-browser.0xQzvX` used its own database,
attachments, and reference-image cache outside `runtime/phase2`. It exercised Snake, Lizard,
Spider, and Scorpion autocomplete;
keyboard selection and save; manual Animal creation; legacy explicit linking; linked profile
identity; all controlled Enclosure types, custom and legacy-type handling; Enclosure-first
linked/manual Plant creation; multi-plant roster; plant search/detail; ambiguous pothos results;
no results; cached provider failure; licensed/unlicensed reference-image choice; attribution;
keeper opt-out; personal-photo takeover; Morph/Genetics explanations and exact suggestions; and
legacy identity-value retention.
The outage capture reused that database on an internal-only Docker network with the provider host
mapped to loopback. No qualification account or browser write targeted live data.

All 70 correction captures across 35 states were visually inspected at 390×844 and 1440×900. The result list starts
4 px beneath its Species input, matches the input width, participates in normal flow, and clears the
next form field at both viewports. Common and scientific names remain readable, mobile controls and
result rows are touch-friendly, manual fallback remains visible, and neither viewport overflows.
Seventy axe scans found zero WCAG 2.2 A/AA violations. The browser recorded zero application
console diagnostics, zero page errors, and zero failed requests in the connected journey; the
isolated outage journey also recorded zero console or page errors. Axe injection used only the test
context's CSP bypass. Production CSP was not changed and both local and public responses retain
`script-src 'self'`, `img-src 'self'`, and the existing strict policy.

Representative evidence includes [Snake autocomplete on mobile](screenshots/mobile-390x844-snake-autocomplete.png),
[Spider autocomplete on desktop](screenshots/desktop-1440x900-spider-autocomplete.png),
[Add Plant on mobile](screenshots/mobile-390x844-add-plant.png),
[multiple Enclosure plants on desktop](screenshots/desktop-1440x900-enclosure-multiple-plants.png),
[plant search on desktop](screenshots/desktop-1440x900-plant-search.png),
[linked profile on mobile](screenshots/mobile-390x844-linked-animal-profile.png),
[legacy linking on desktop](screenshots/desktop-1440x900-legacy-link-species.png), and
[cached outage on mobile](screenshots/mobile-390x844-cached-provider-outage.png). Addendum evidence
includes [reference choice on mobile](screenshots/mobile-390x844-new-animal-selected-species-reference-option.png),
[no-reference fallback on desktop](screenshots/desktop-1440x900-new-animal-no-reference-image.png),
[attributed reference profile on desktop](screenshots/desktop-1440x900-animal-profile-reference-attribution.png),
[personal-photo priority on mobile](screenshots/mobile-390x844-animal-profile-personal-photo.png),
[Morph/Genetics suggestions on desktop](screenshots/desktop-1440x900-morph-and-genetics-suggestions.png),
and [exact legacy identity values on mobile](screenshots/mobile-390x844-legacy-animal-edit-preserved-values.png). The screenshot
directory contains both viewports for every required review state.

Correction #3 evidence includes [selected Animal without an eligible image](screenshots/mobile-390x844-new-animal-no-reference-image.png),
[Plant Directory reference image](screenshots/desktop-1440x900-plant-directory-detail-with-reference-image.png),
[Plant Directory placeholder](screenshots/mobile-390x844-plant-directory-detail-without-reference-image.png),
[Enclosure Plant reference image](screenshots/mobile-390x844-enclosure-plant-detail-with-reference-image.png),
[Enclosure Plant manual placeholder](screenshots/desktop-1440x900-enclosure-plant-detail-without-linked-image.png),
[dense roster thumbnails](screenshots/mobile-390x844-enclosure-multiple-plants.png), and the
[upgraded shell/autocomplete state](screenshots/desktop-1440x900-upgraded-service-worker-current-assets.png).
The browser began with a synthetic `snaketracker-shell-v5` cache containing the obsolete
`m65-c1` overlay rule. Normal service-worker activation removed it and activated only
`snaketracker-shell-m66-a-owner-c3`, serving `/static/app.css?v=m66-a-owner-c3` at SHA-256
`0304f9ddf9a2fc21971c7be56f05f912ecedf84f5f29e7e969d64e60dfd8f0e2` without manual cache or
site-storage clearing. Fourteen responsive autocomplete geometry observations reported CSS
`position: static`, an exact 4 px input-to-list gap, zero width delta, and clearance from subsequent
fields. One successfully served favicon was cancelled with `net::ERR_ABORTED` by the harness's
intentional rapid navigation; it is recorded separately from the zero application request failures.

The final [public cache qualification](public-cache-qualification.json) independently loaded the
promoted public origin with fresh authenticated browser contexts at both required viewports. Public
HTML requested `/static/app.css?v=m66-a-owner-c3`; public and direct-origin responses both matched
SHA-256 `0304f9ddf9a2fc21971c7be56f05f912ecedf84f5f29e7e969d64e60dfd8f0e2`. Snake and Spider
results were `position: static`, exactly 4 px below the input, exactly the input width, clear of the
Profile Picture and Sex fields by at least 164.78 px, and caused no horizontal overflow. Cloudflare
injected its Browser Insights beacon and paired inline loaders into public responses; Care Keeper's
unchanged `script-src 'self'` blocked them. Those external-platform diagnostics are not
Care Keeper-owned script failures, and no CSP allowance was added.

## Migration, backup, restore, and live-data preservation

The active paths were resolved before every destructive operation as
`/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3` and
`/home/rocco/SnakeTracker/runtime/phase2/attachments`. Disposable targets were explicitly compared
against them. The active database was never wiped, reset, reseeded, replaced, restored over,
truncated, manually cleaned, or used for qualification accounts.

Before correction qualification, encrypted backup request
`40f36a55-3f64-404d-9795-0106d16ca150` completed as run
`f320f695-f981-491f-b02b-d049bbd612d5`. Its manifest checksum is
`789f37b5ba9636769229ea9542ff013436a09f59f3a7a5062c53497144b8ea99`; the encrypted database
SHA-256 is `3e3bd9875553ae11e96b4ce299aa20f7591017b0537ed1a445a2f5ab31f31d32`.
The backup restored with status `verified` and all 33 referenced attachments into
`/var/lib/snaketracker/qualification/m66a-owner-correction-restore-20260914/`
`f320f695f981491fb02bd049bbd612d5`. This isolated target was never copied or restored over the
active database.

A copy of that verified restore was upgraded at
`/tmp/carekeeper-m66a-0019-to-0021.HauNJ8/snaketracker.sqlite3`. Migrations
`0020_enclosure_plants` and `0021_reference_images` advanced 0019→0021, adding the
Enclosure-plant current projection, global image-cache metadata, and default-false Animal image preference,
kept SQLite integrity `ok` and FK violations at zero, and preserved all 816 events plus ordered
newline-delimited ordered-checksum hash
`31c530eb4fcde1370194d7b92bdfb6b6e8b4afc82fa9819164d6daee0d3e2d26`.
Before/after counts also matched: four households/users/memberships, 44 Animals, 29 Enclosures, 30
Inventory Items, four Purchases, 14 Expenses, and 39 Attachment versions. The new projection was
empty, as expected, before any Enclosure plant facts exist.

The rehearsed migrations were then applied forward in place to live data. Post-deploy revision is
`0021_reference_images`, integrity is `ok`, FK violations are zero, all 816 events, ordered hash,
and business counts remain unchanged. Every existing Animal has the safe default-false reference
preference; the Enclosure Plant projection remains empty because qualification did not use the live
household. The 40-file Attachment tree remains byte-identical at
`87855d591f9646ccd0f6b214f191db58ff38b9d57794ecced6eb223d2836dbd7`.

## ARM64 deployment

Correction #3 took a new non-overwriting encrypted backup before promotion: request
`93f1757e-afaf-432b-b8f5-f0f02545abb7`, run
`de8ba1f0-8666-470c-89b7-40f495eeffe0`. The encrypted manifest checksum is
`e78502c8a84cc3e165b8909b989428038fb6d8bbea5407e741960634c3ab21d0`; the encrypted database
SHA-256 is `52c91c94db1b6de8d28e9fb8a0d046119d21f88fc5d1d1b8ce6a46524af1eadf`.
Restore verification completed with status `verified`, 33 referenced Attachments, and matching
revision, integrity, FK status, event count, and ordered event checksum in the isolated host-backed
target `/tmp/carekeeper-m66a-owner-c3-restore.IbHQEE`. The active database was never a restore
target. An earlier isolated container-overlay target exhausted its own available space and was
removed only after its resolved path was proven distinct from every active runtime path.

Immediately before correction #3 deployment, the active runtime was at `0021_reference_images`
with integrity `ok`, zero FK violations, 818 events, ordered checksum hash
`34dae0b2cc38d13f92acbaf1a24a644238dc3af4b084c4b60de904dc040ae41f`, 44 Animals, 30
Enclosures, one Enclosure Plant, 30 Inventory balances, four Purchases, 14 Expenses, four users,
four households, and 39 Attachment versions. The same values and checksum remained exact after
deployment. During the explicitly required public computed-style check, a concurrent Edge 153
keeper session—not the HeadlessChrome 145 qualification session—submitted one legitimate
`enclosure.plant_added` event at 09:10:56 UTC. Server access logs distinguish its POST and user
agent from the qualification's login, GET, and autocomplete requests. The final live state therefore
has 819 events and two Enclosure Plants; qualification did not create, edit, delete, reset, reseed,
or restore any household record. All first 818 event checksums remain identical to the pre-deploy
baseline. The 40-file Attachment tree remained byte-identical before and after at SHA-256
`d9c69298591f8d42adb9ca6a43174ac17a3925d718bf8034866e79444e375fab`.

Native image `snaketracker:m66-a-owner-c3` is Linux ARM64, SHA-256
`94f6b00c17497a6ac458a82ea5f888a55d30031ef3715ee2092abbf3c0c2135b`. The migration one-shot
exited zero at existing head `0021_reference_images`. Web and worker run as UID/GID `1001:1001`;
web, worker, and Nginx are healthy; local and public `/health/ready` return `ready`; and exactly one
`snaketracker` Compose project with three active services remains. `SnakeTracker.code-workspace`
remains untracked and untouched.

## Owner-fidelity correction final promotion

The exact frozen authoritative command, `uv sync --frozen` followed by
`./scripts/quality/check.sh`, completed successfully after the owner-fidelity correction. All 676
tests passed. Enforced coverage was 94.45 percent lines, 85.08 percent branches, and 92.57 percent
total. Formatting, Ruff, strict mypy, architecture freeze, documentation links, generated-artifact
checks, dependency audit (no known vulnerabilities), Compose validation, and diff checks passed.

Before this qualification, encrypted backup request
`c70efed4-e85c-4776-a491-9620dce9b652` completed as run
`7b5847b5-01e6-4a59-848c-e3fa400cc9d4`; manifest SHA-256 is
`9919dd08ad5453e5313d7edf26243e44bdbb81acb1b1f44bd3c4d0014473fc0e` and encrypted database
SHA-256 is `6a7dfa719ae87aaab7b9964ca60261d46f4e686e529b6c2a8cba55fabaeeba60`.
Its restore was verified outside all active paths at
`/tmp/carekeeper-m66a-fidelity-restore.vWgAii`. A copy at
`/tmp/carekeeper-m66a-fidelity-upgrade.VAVMSE` rehearsed 0021→0022 with integrity `ok`, zero FK
violations, all 819 events, and exact ordered event checksum
`66f4f49ebaece8bf6adf73115a2578262ef5f97da88a8508568d6568378f8c83`.

Promotion applied only `0022_reference_image_provenance` to the active database. Before/after
business state is exact: 819 events and the checksum above, four households/users/memberships, 44
Animals, 30 Enclosures, two Enclosure Plants, 30 Inventory balances, four Purchases, 14 Expenses,
39 Attachment versions, 35 taxa, and five taxon-image records. SQLite integrity is `ok`, FK
violations are zero, and the 40-file Attachment tree is byte-identical at
`d9c69298591f9646ccd0f6b214f191db58b9d57794ecced6eb223d2836dbd7`. No live household record was
created, edited, deleted, reset, reseeded, replaced, or used as a qualification fixture.

The final non-overwriting encrypted backup is request
`6d7cb65c-02b6-44eb-acbb-0ae0c60f3316`, run
`86c35fe9-1e79-4323-82b3-f22ed66f29cf`, manifest SHA-256
`b6ee25f40b2a7d8bea2bedd60006fdfb1f366e056b5614888a00b76c2fcb9d5b`, and encrypted database
SHA-256 `8a7bd856f0afb1f2f343dbae85951ab1057742e65fc2538c3492a21fd9985789`.
It restored with status `verified` and all 33 referenced Attachments only into
`/tmp/carekeeper-m66a-fidelity-postrestore.KHJFL0`; that restored database is at 0022 with
integrity `ok`, zero FK violations, 819 events, and the exact ordered checksum above.

Final native image `snaketracker:m66-a-owner-fidelity` is Linux ARM64, SHA-256
`4e79df1ca7f3dbd5783c102871e77d40229bf93493a6d412bab3b6c3b6fe2934`. Web and worker run as
UID/GID `1001:1001`; web, worker, and Nginx are healthy; both local and public readiness return
`ready`; and exactly one Care Keeper Compose stack is active.

The required owner-review captures are
[mobile Today](screenshots/mobile-390x844-today.png),
[mobile Animals](screenshots/mobile-390x844-animals.png),
[mobile profile](screenshots/mobile-390x844-animal-profile-reference.png),
[mobile Calendar](screenshots/mobile-390x844-calendar.png),
[mobile Quick Log](screenshots/mobile-390x844-quick-log.png),
[mobile Enclosures](screenshots/mobile-390x844-enclosures.png),
[desktop Today](screenshots/desktop-1440x900-today.png),
[desktop Animals](screenshots/desktop-1440x900-animals.png),
[desktop profile](screenshots/desktop-1440x900-animal-profile-reference.png), and
[desktop Enclosures](screenshots/desktop-1440x900-enclosures.png).

## Boundaries

This tranche implements directory search, provider abstraction/cache, Animal linking and manual
fallback, controlled Enclosure types, basic Enclosure-owned plant placement and immutable
lifecycle, licensed local reference images, keeper image preference, personal-photo-first display,
and non-inferred household/taxon-scoped Morph/Genetics assistance. It does not implement care guides,
watering, schedule suggestions, bioactive mode,
Today/Calendar plant reminders, M6.6-B, M7, or PR merge.
