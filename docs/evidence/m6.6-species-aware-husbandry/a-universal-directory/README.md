# M6.6-A — Universal Species Directory

Status: implementation-qualified September 14, 2026; owner review pending

Base revision: `306f465623c50f8a24513975fa85b2104d88d82d`

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
licence-screened image metadata. A provider ID is never the primary identity. The only household
fact is the keeper-confirmed `animal.taxon_linked` v1 event on the Animal stream; its projection is
household-scoped and its confirmation snapshot does not rewrite registration or profile history.

The selected discovery adapter is iNaturalist. Search is limited to two-to-100 normalized
characters and one of snake, lizard, spider, scorpion, or plant. The client waits 320 ms, cancels
superseded requests, deduplicates the active query, and supports arrow keys, Enter, and Escape with
combobox/listbox semantics. The service reads its 30-day local cache first. Provider calls use a
fixed HTTPS origin, a three-second timeout, no automatic interactive retry, a 256 KiB response
limit, and JSON/schema/string/group/rank validation. It sends only query text and group—not Care
Keeper identity, household, Animal, care, enclosure, financial, attachment, or account data.

An outage, timeout, `429`, malformed or oversized response, quota failure, and no result are normal
product states. Fresh cache avoids the provider; stale cache is displayed as a saved result; no
cache leaves manual species entry usable. Animal profile reads are local-only. The plant directory
provides taxonomy search/detail only and creates no household plant, watering, bioactive, care
guide, or schedule state. Unknown or incompatible image rights produce a local placeholder;
M6.6-A does not fetch or render remote provider images.

## Deterministic automated qualification

The exact authoritative path `uv sync --frozen` followed by `./scripts/quality/check.sh` passed on
September 14, 2026:

- formatting, Ruff, architecture freeze, documentation links, strict mypy, Compose validation,
  generated-artifact checks, dependency audit, and diff checks passed;
- 638 tests passed, including deterministic five-group, common/scientific/synonym, filter,
  provider-ID separation, legacy/change/idempotency/isolation, accepted-name, cache/outage,
  timeout/`429`/malformed/oversized, licence, migration, backup, and replay coverage;
- line coverage was 94.45 percent and branch coverage was 85.02 percent; and
- the dependency audit reported no known vulnerabilities.

The deterministic browser/API performance test also makes 20 authenticated cached autocomplete
requests and requires p95 below 250 ms. Native Chromium qualification measured a separate 50-call
sample at 23.9 ms p95 (14.8 ms median, 140.8 ms maximum) on the isolated ARM64 runtime.

## Browser, responsive, and accessibility qualification

One disposable runtime at `/tmp/carekeeper-m66-a-browser.0xQzvX` used its own database and
attachments outside `runtime/phase2`. It exercised Snake, Lizard, Spider, and Scorpion autocomplete;
keyboard selection and save; manual Animal creation; legacy explicit linking; linked profile
identity; plant search/detail; ambiguous pothos results; no results; and cached provider failure.
The outage capture reused that database on an internal-only Docker network with the provider host
mapped to loopback. No qualification account or browser write targeted live data.

All 22 required screenshots were captured and visually inspected at 390×844 and 1440×900. Common
and scientific names remain readable, mobile controls and result rows are touch-friendly, desktop
results use a compact grid, manual fallback remains visible, and neither viewport overflows.
Twenty-two axe scans found zero WCAG 2.2 A/AA violations. The browser recorded zero application
console errors/warnings, zero page errors, and zero failed requests in the connected journey; the
isolated outage journey also recorded zero console or page errors. Axe injection used only the
test context's CSP bypass. Production CSP was not changed and both local and public responses retain
`script-src 'self'`, `img-src 'self'`, and the existing strict policy.

Representative evidence includes [Snake autocomplete on mobile](screenshots/mobile-390x844-snake-autocomplete.png),
[plant search on desktop](screenshots/desktop-1440x900-plant-search.png),
[linked profile on mobile](screenshots/mobile-390x844-linked-animal-profile.png),
[legacy linking on desktop](screenshots/desktop-1440x900-legacy-link-species.png), and
[cached outage on mobile](screenshots/mobile-390x844-cached-provider-outage.png). The screenshot
directory contains both viewports for every required review state.

## Migration, backup, restore, and live-data preservation

The active paths were resolved before every destructive operation as
`/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3` and
`/home/rocco/SnakeTracker/runtime/phase2/attachments`. Disposable targets were explicitly compared
against them. The active database was never wiped, reset, reseeded, replaced, restored over,
truncated, manually cleaned, or used for qualification accounts.

Before browser or migration qualification, encrypted backup request
`f6246d85-eebf-4c85-81d7-605bade7a47e` completed as run
`846366b6-3472-4846-ac9b-c29a4b9839bf`. Its manifest checksum is
`cb010b0fa957978023cb86596843a5f675a9729c08c5e4013417b826d33c7e5a`; the encrypted database
SHA-256 is `b656a70a9c970187e73124ad12e75fcdfd1a8cb9e960dbbedb11f0a8571085d0`.
The backup restored with status `verified` into
`/tmp/carekeeper-m66-a-preflight-restore.uKY3UW` and restored 33 referenced attachments. It was
never restored over the active database.

A copy of that verified restore was upgraded at
`/tmp/carekeeper-m66-a-upgrade.nA3iCy/snaketracker.sqlite3`. Migration
`0019_universal_species_directory` advanced 0018→0019, created the five directory/link tables,
kept SQLite integrity `ok` and FK violations at zero, and preserved all 812 events plus ordered
event hash `514a3800ceeb7459dbfbf978bb00adc624f32debbba03d6f13235d45cdc5a695`.
Before/after counts also matched: four households/users/memberships, 42 Animals, 29 Enclosures, 30
Inventory Items, four Purchases, 14 Expenses, and 39 Attachment versions.

The backed-up migration was then applied in place to live data. Post-deploy revision is 0019,
integrity is `ok`, FK violations are zero, all counts and the same 812-event hash remain unchanged,
and the 40-file Attachment tree remains byte-identical at
`d9c69298591f8d42adb9ca6a43174ac17a3925d718bf8034866e79444e375fab`.
The new reference/link tables are empty because qualification did not use the live household.

## ARM64 deployment

Native image `snaketracker:m66-a-review` is Linux ARM64, SHA-256
`cbbf49581d082c4ff43217629362a74c977e6a92e0c6920c676bb9f48dbba10e`. The migrate container
exited zero. Web and worker run as UID/GID `1001:1001`; web, worker, and Nginx are healthy; local
and public `/health/ready` return `ready`; and exactly one `snaketracker` Compose project with three
active services remains. `SnakeTracker.code-workspace` remains untracked and untouched.

## Boundaries

This tranche implements directory search, provider abstraction/cache, Animal linking and manual
fallback, and plant taxonomy browsing only. It does not implement care guides, schedule
suggestions, bioactive enclosures, owned plants/watering, M7, or PR merge.
