# M6.6-A — Universal Species Directory

Status: implementation-qualified September 14, 2026; owner review pending

Base revision: `306f465623c50f8a24513975fa85b2104d88d82d`

Owner-review correction base: `d3e33981f9850755f710e4e85f34242b7df9b7f2`

Branch: `phase6.6/universal-species-directory`

Requirements: `R-086`–`R-090`

Architecture: [ADR-0043](../../../adr/0043-universal-species-directory.md)

## Evidence index

- [Provider and licensing audit](provider-audit.md)
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

Eligible CC0, CC BY, and CC BY-SA reference images are global Directory assets, not household
attachments. Care Keeper fetches only allow-listed iNaturalist HTTPS image origins server-side,
rejects redirects, applies a three-second timeout and 10 MiB response cap, requires JPEG/PNG/WebP,
decodes under 25-megapixel/8192-pixel limits, normalizes to WebP, stores checksum/cache metadata,
and revalidates the checksum on local delivery. Unknown or revoked licences, unsafe origins,
timeouts, invalid/oversized content, and unavailable cache bytes resolve to the placeholder. Keeper
pages contain only the authenticated same-origin image route; CSP remains `img-src 'self'`.

The keeper may opt into or decline a species reference per Animal. The existing attachment-backed
personal photo always wins and remains discoverable as **Add photo**, **Add my animal's photo**, or
**Change photo**. Uploading one does not delete global cache metadata. Morph/variant and
Genetics/lineage are explained as optional individual facts under progressive disclosure. Exact
previous values are suggested only for the same household and linked Care Keeper taxon, remain
free-text and explicitly selected, and are never inferred, normalized, or erased by species choice.

## Deterministic automated qualification

The exact authoritative path `uv sync --frozen` followed by `./scripts/quality/check.sh` passed on
September 14, 2026:

- formatting, Ruff, architecture freeze, documentation links, strict mypy, Compose validation,
  generated-artifact checks, dependency audit, and diff checks passed;
- 652 tests passed, including deterministic five-group, common/scientific/synonym, filter,
  provider-ID separation, legacy/change/idempotency/isolation, accepted-name, cache/outage,
  timeout/`429`/malformed/oversized, licence, image SSRF/redirect/decode/dimension/integrity,
  keeper image preference, personal-photo priority, identity-suggestion isolation, migration,
  backup, and replay coverage;
- the enforced 90-percent total and 85-percent branch coverage gates passed; and
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

All 60 correction captures across 30 states were visually inspected at 390×844 and 1440×900. The result list starts
4 px beneath its Species input, matches the input width, participates in normal flow, and clears the
next form field at both viewports. Common and scientific names remain readable, mobile controls and
result rows are touch-friendly, manual fallback remains visible, and neither viewport overflows.
Sixty axe scans found zero WCAG 2.2 A/AA violations. The browser recorded zero application
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

Native image `snaketracker:m66-a-owner-correction-2` is Linux ARM64, SHA-256
`b2f78d427dfe4f58b6f9492da245b1c614efefaddb38ba35cb540ea27f2dc71a`. The migrate container
exited zero. Web and worker run as UID/GID `1001:1001`; web, worker, and Nginx are healthy; local
and public `/health/ready` return `ready`; and exactly one `snaketracker` Compose project with three
active services remains. `SnakeTracker.code-workspace` remains untracked and untouched.

## Boundaries

This tranche implements directory search, provider abstraction/cache, Animal linking and manual
fallback, controlled Enclosure types, basic Enclosure-owned plant placement and immutable
lifecycle, licensed local reference images, keeper image preference, personal-photo-first display,
and non-inferred household/taxon-scoped Morph/Genetics assistance. It does not implement care guides,
watering, schedule suggestions, bioactive mode,
Today/Calendar plant reminders, M6.6-B, M7, or PR merge.
