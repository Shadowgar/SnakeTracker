# Phase 6 Product Experience Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan
> task-by-task after explicit owner approval. Do not begin M7 work.

**Goal:** Deliver household-safe search, capability-aware reports and analytics, an explainable
keeper dashboard, curated reference-profile support, and an installable read-only PWA that satisfies
M6 without rewriting M0–M5.5 history or owner reminder rules.

**Architecture:** Reuse the accepted event store, effective-history semantics, projection generation
manager, durable jobs, M5 reminder facts, and M5.5 capability registry. Search, reports, analytics,
dashboard statistics, references, and suggestions are rebuildable read-side consumers. Server-
rendered Jinja pages remain primary; small locally served scripts provide charts and PWA behavior
under the existing strict CSP.

**Tech stack:** Python 3.13, FastAPI/Jinja2, synchronous SQLAlchemy/SQLite, SQLite FTS5, existing
projection generations and durable workers, locally served pinned Chart.js, Playwright/Pa11y for
real-browser qualification, Docker Compose, and Buildx ARM64 builds.

**Owner approval:** Approved August 15, 2026, with the proportional minimum-uncertainty amendment
recorded below.

---

## Scope and controlling requirements

The controlling requirements are roadmap M6; R-007, R-020–R-022, R-026, R-035, R-041, R-045,
R-046, and R-052; ADR-0007, ADR-0008, ADR-0019–ADR-0021, ADR-0025, ADR-0030, ADR-0034,
ADR-0036, ADR-0038, and ADR-0039; and threat controls TM-04, TM-05, TM-09, TM-18, TM-19, and
TM-20.

M6 adds no authoritative analytics, prediction, report, search, or reference aggregate. It does not
rewrite historical events, change the M5 reminder schedule, add another animal type, permit offline
writes, enable remote access, or claim production/Raspberry Pi qualification. Expense documents and
reports remain subject to their stricter financial capability, not household membership alone.

## Selected design and alternatives

Use four independently rebuildable, allow-listed groups:

1. `search`: `global_search_fts` content and FTS5 virtual tables.
2. `insights`: `measurement_analytics`, `feeding_analytics`, `report_facts`, and
   `husbandry_recommendations`.
3. `dashboard`: `dashboard_statistics`; authoritative due items continue to come directly from M5
   `reminder_facts`.
4. `references`: versioned `husbandry_reference_profiles` loaded only from reviewed source bundles.

This keeps a search failure from disabling reports and lets interdependent insight tables activate
atomically. Live SQL aggregation was rejected because it would lengthen requests and bypass the
accepted freshness/rebuild model. Browser-side calculation was rejected because it would duplicate
policy, increase disclosure risk, and make corrected effective history harder to enforce.

## Deterministic suggestion policy proposed for owner approval

- Feeding needs at least six effective accepted feedings, producing five positive intervals. Use at
  most the eight most recent qualifying intervals. Refused and regurgitated attempts never qualify.
- Snake shed and Spider molt each need at least five effective completed occurrences, producing
  four positive intervals. Use at most the six most recent qualifying intervals.
- Calculate the median interval and median absolute deviation (MAD). When MAD is nonzero, discard
  intervals more than three MAD from the median; when MAD is zero, retain the sample unchanged. Do
  not suggest if filtering leaves fewer than the minimum interval count.
- The window is the latest qualifying occurrence plus
  `median ± max(MAD, 10% of the median interval, one day)`, using the deterministic integer-day
  equivalent defined by the policy implementation and clamped to a positive lower interval. The
  10% term is a minimum uncertainty floor, not a confidence percentage. Use no opaque weighting in
  M6; the bounded recent sample is the recency policy.
- If today is after the upper window, display that the historical estimate window has passed; never
  roll the estimate forward without a new effective qualifying event. Corrections, voids, and
  reinstatements rebuild the sample before the result is shown.
- Every result is labeled **estimate** and exposes kind, policy version, sample count, included
  interval range, exclusions, median, MAD, source cutoff, and plain-language rationale. Insufficient
  history displays no prediction. Owner schedules remain the only reminder authority.

## Relational and compatibility strategy

Add one forward revision, `0011_product_experience`, after `0010_multispecies_foundation`. Extend
the projection catalog metadata with allow-listed source kind, freshness threshold, and optional
source-manifest checksum; generation-owned content/FTS/report/analytics tables remain created and
dropped by registered strategies rather than Alembic. The downgrade must refuse while M6
definitions or generations remain active, then succeed after the documented cleanup procedure.
Startup must reject unknown newer projection schemas, handler versions, and reference-bundle
schemas. Old M0–M5.5 events and read models remain unchanged.

## Test-driven implementation sequence

For every task: write the named failing tests, run the focused command and observe the expected
failure, implement the smallest slice, rerun focused tests, run `./scripts/quality/check.sh`, update
evidence, and commit. No roadmap box is checked until its evidence passes.

### Task 1 — Lock M6 scope, capabilities, compatibility, and migration

- **Files:** create `migrations/versions/0011_product_experience.py`; extend
  `domains/animals/capabilities.py`, `platform/projections/definitions.py`,
  `bootstrap/compatibility.py`, architecture/database/projection catalogs, and compatibility tests.
- **Projection work:** register analytics/reference capabilities per trusted `snake.v1` and
  `spider.v1`; reject arbitrary identifiers and unknown stored generations.
- **Routes/screens:** none.
- **Tests:** migration upgrade/downgrade/re-upgrade; destructive downgrade guard; legacy v1 and v2
  replay; unknown profile/projection/reference version; M7 and new-animal-type scope guards.
- **Capability enforcement:** Snake enables length/shed analytics; Spider enables molt analytics;
  both share feeding/weight only where declared.
- **Evidence:** `m6-product-experience/tests/compatibility` and `operations/migrations`.
- **Rollback/rebuild:** downgrade only after M6 generation cleanup; never change stored events.
- **Focused command:** `uv run pytest -q tests/integration/test_alembic_lifecycle.py
  tests/unit/bootstrap/test_compatibility.py tests/unit/domains/test_animal_capabilities.py`.
- **Commit:** `feat: establish M6 read-model compatibility boundary`.

### Task 2 — Add asynchronous projection advancement and freshness

- **Files:** create `application/projection_health.py`, `worker/projections.py`, and production
  definitions/strategies under `infrastructure/product_experience/`; extend the composition root and
  worker loop.
- **Projection work:** consume transactional handoff work in global-position order, checkpoint each
  active generation, expose last position/time/lag/health, and make retries idempotent.
- **Routes/screens:** authenticated projection freshness fragment used by later pages; operational
  detail remains progressively disclosed.
- **Tests:** duplicate/out-of-order handoff, restart, lag, failure quarantine, stale display,
  cross-household reads, interruption, activation, rollback, and cleanup.
- **Data/migration:** use 0011 catalog metadata and existing outbox/jobs; no business events.
- **Capability enforcement:** freshness reveals no counts or subjects outside the principal's
  current household/capabilities.
- **Evidence:** `m6-product-experience/tests/async-freshness` and `operations/projections`.
- **Rollback/rebuild:** retain the prior generation; a failed asynchronous projection cannot affect
  synchronous authorization/current state.
- **Focused command:** `uv run pytest -q tests/integration/test_product_projection_worker.py
  tests/integration/test_projection_rebuilds.py`.
- **Commit:** `feat: add asynchronous product projection runner`.

### Task 3 — Build household-authorized FTS5 search

- **Files:** create `application/search.py`, `infrastructure/search/fts.py`, `templates/search.html`,
  and search routes in `presentation/web.py`.
- **Projection work:** generation-specific content plus FTS5 tables for animals/species,
  enclosures, effective care/feedings/notes, applicable inventory, and authorized expenses. Store
  household, subject, capability requirement, safe route, title, body, effective time, and source
  checkpoint; never index raw envelope metadata for normal search.
- **Routes/screens:** `GET /search?q=` with grouped results, empty/error/rebuilding states, and
  material freshness notice; global search in primary navigation.
- **Tests:** household and financial-capability leakage, removed/voided/corrected facts, Unicode,
  query limits, safe highlighting, FTS integrity/optimize, shadow swap/rollback/interruption, and
  stale state.
- **Data/migration:** FTS structures belong to the search generation and use only registry-created
  physical identifiers.
- **Capability enforcement:** filter in the repository before snippets/routes are returned; UI
  hiding is not the security boundary.
- **Evidence:** `m6-product-experience/tests/search`, `security/search-authorization`, and
  `browser/search`.
- **Rollback/rebuild:** atomically restore the retained search generation; fall back to a clear
  unavailable/rebuilding state, never an unscoped query.
- **Focused command:** `uv run pytest -q tests/integration/test_search.py
  tests/security/test_product_experience_security.py`.
- **Commit:** `feat: add authorized FTS5 keeper search`.

### Task 4 — Build reconciled keeper reports

- **Files:** create `application/reports.py`, `infrastructure/reports/projections.py`, report
  templates, and report routes.
- **Projection work:** normalized effective `report_facts` for collection, care, feeding,
  measurements, Snake sheds, Spider molts, and expenses.
- **Routes/screens:** `/reports`, focused HTML reports, and authorized CSV exports with household-
  timezone grouping and accessible tables.
- **Tests:** reconciliation against event fixtures, correction/void/reinstate, household/expense
  authorization, timezone/DST boundaries, CSV injection protection, and export security audit.
- **Data/migration:** report tables belong to the insights generation; no authoritative write model.
- **Capability enforcement:** omit inapplicable report types and fields rather than manufacturing
  empty Snake metrics for Spiders.
- **Evidence:** `m6-product-experience/tests/reports` and `security/exports`.
- **Rollback/rebuild:** report reads stay on the retained generation until replacement validation
  succeeds.
- **Focused command:** `uv run pytest -q tests/integration/test_reports.py
  tests/security/test_product_experience_security.py`.
- **Commit:** `feat: add capability-aware keeper reports`.

### Task 5 — Add effective measurement analytics and charts

- **Files:** create `application/analytics.py`, `infrastructure/analytics/projections.py`,
  `templates/animal_analytics.html`, `static/charts.js`, and versioned JSON chart routes.
- **Projection work:** effective weight points for applicable animals; length points only for
  profiles declaring length; change/interval summaries with units and source cutoff.
- **Routes/screens:** `/animals/{id}/analytics` and `/api/v1/animals/{id}/analytics/measurements`;
  locally served Chart.js plus visible table/text summaries.
- **Tests:** corrected/voided/reinstated points, units, missing data, ETag/authorization, capability
  rejection, CSP, keyboard, mobile, and chart-equivalent text.
- **Data/migration:** measurement tables live in insights generation; no event or aggregate change.
- **Capability enforcement:** application query policy and projection handlers both consult the
  trusted profile registry.
- **Evidence:** `m6-product-experience/tests/measurement-analytics` and `accessibility/charts`.
- **Rollback/rebuild:** chart endpoints use one active validated generation and report staleness.
- **Focused command:** `uv run pytest -q tests/integration/test_measurement_analytics.py
  tests/browser/test_product_experience.py`.
- **Commit:** `feat: add accessible measurement trends`.

### Task 6 — Add effective feeding analytics

- **Files:** extend analytics application/projection modules and animal analytics templates.
- **Projection work:** accepted/refused/regurgitated counts, accepted-feeding intervals, frequency
  trend, and historical prey facts from effective history.
- **Routes/screens:** feeding trend section plus accessible interval/outcome table and explanation.
- **Tests:** refused/regurgitated exclusion from accepted intervals, correction/void/reinstate,
  shared Snake/Spider feeding semantics, inventory compensation independence, and household scope.
- **Data/migration:** extend the insights generation only.
- **Capability enforcement:** require registered feeding capability; do not infer support from
  animal type strings.
- **Evidence:** `m6-product-experience/tests/feeding-analytics`.
- **Rollback/rebuild:** deterministic replay from effective feeding facts and retained-generation
  rollback.
- **Focused command:** `uv run pytest -q tests/integration/test_feeding_analytics.py
  tests/integration/test_inventory.py`.
- **Commit:** `feat: add effective feeding analytics`.

### Task 7 — Add separate Snake shed and Spider molt analytics

- **Files:** extend analytics policy/projections, capability presentation definitions, templates,
  and JSON endpoints.
- **Projection work:** separate interval series and summaries for completed Snake sheds and Spider
  molts; premolt observations remain context, not completed molt intervals.
- **Routes/screens:** capability-selected shed or molt history/trend with no misleading combined
  statistic.
- **Tests:** Snake/Spider isolation, molt result policy, premolt exclusion, correction/void/
  reinstate, legacy Snake replay, and unknown capability failure.
- **Data/migration:** insight-generation extension only.
- **Capability enforcement:** use registered analytics kinds; no scattered `animal_type` route or
  template branches.
- **Evidence:** `m6-product-experience/tests/husbandry-analytics`.
- **Rollback/rebuild:** replay effective history and atomically switch the complete insights group.
- **Focused command:** `uv run pytest -q tests/integration/test_husbandry_analytics.py
  tests/integration/test_multispecies_animals.py`.
- **Commit:** `feat: add capability-specific husbandry trends`.

### Task 8 — Integrate the Today dashboard with M5 reminder facts

- **Files:** create `application/dashboard.py`, `infrastructure/dashboard/projections.py`, and
  refactor `templates/home.html` plus dashboard routes.
- **Projection work:** async collection statistics/recent trends only. Overdue, due-today, and
  upcoming care query authoritative M5 reminder facts with their existing explanation.
- **Routes/screens:** mobile-first Today page ordered by overdue, today, upcoming, recent activity,
  and progressively disclosed collection statistics.
- **Tests:** timezone boundaries, why-due text, disabled rules, household scope, stale statistics,
  correction-triggered reminder recalculation, and no schedule mutation.
- **Data/migration:** dashboard generation only; M5 reminder tables/contracts remain unchanged.
- **Capability enforcement:** only applicable reminder facts and authorized subjects appear.
- **Evidence:** `m6-product-experience/tests/dashboard` and `browser/dashboard`.
- **Rollback/rebuild:** due facts remain usable if async statistics fail; stale statistics are
  labeled or withheld.
- **Focused command:** `uv run pytest -q tests/integration/test_dashboard.py
  tests/integration/test_reminders.py tests/browser/test_product_experience.py`.
- **Commit:** `feat: add explainable keeper dashboard`.

### Task 9 — Add explainable suggested care windows

- **Files:** create `application/suggestion_policy.py`; extend recommendation projection and animal
  analytics/dashboard presentation.
- **Projection work:** versioned deterministic feeding, Snake shed, and Spider molt suggestions
  using the approved minimum-history/MAD policy and effective history.
- **Routes/screens:** estimate cards show window and plain-language reason; technical provenance is
  optional disclosure; insufficient/stale history produces no invented date.
- **Tests:** short and long feeding intervals; long Spider molt intervals; zero MAD; nonzero MAD
  below and above the proportional floor; every sample threshold; outliers; long/passed windows;
  refused feeds; corrections/voids/reinstatements; separate shed/molt rules; owner schedule
  precedence; insufficient history; and deterministic rebuild/replay.
- **Data/migration:** recommendations remain insights read models and never write Animal/Reminder
  streams.
- **Capability enforcement:** the registered profile selects allowed suggestion policies.
- **Evidence:** `m6-product-experience/tests/husbandry-analytics/suggestions`.
- **Rollback/rebuild:** policy version change builds a shadow insights generation; retain the prior
  generation for rollback.
- **Focused command:** `uv run pytest -q tests/unit/application/test_suggestion_policy.py
  tests/integration/test_husbandry_recommendations.py`.
- **Commit:** `feat: add deterministic care-window suggestions`.

### Task 10 — Add versioned husbandry reference profiles

- **Files:** create `application/husbandry_references.py`, `infrastructure/references/repository.py`,
  a JSON Schema and reviewed bundles under `src/snaketracker/reference_data/`, provenance templates,
  and compatibility tests.
- **Projection work:** load checksummed, schema-versioned source bundles into the references
  generation with species identity, capability profile, optional life stage, ranges/statements,
  explicit absence, source, publication/retrieval/version data, and bundle checksum.
- **Routes/screens:** references appear below facts, owner configuration, and observed history;
  provenance is progressively disclosed and suggestions stay separately labeled.
- **Tests:** schema/provenance/version validation, unsupported species/life stage, explicit absence,
  range rendering, source escaping, unknown newer bundle failure, and reminder non-mutation.
- **Data/migration:** immutable packaged reference bundles plus rebuildable reference generation;
  no user-editable EAV/JSON model.
- **Capability enforcement:** bundle applicability must match a registered profile; no Gecko or
  arbitrary profile is accepted.
- **Evidence:** `m6-product-experience/tests/husbandry-references` and `references/provenance`.
- **Rollback/rebuild:** activate a complete validated bundle generation; retain the prior bundle;
  an invalid/missing bundle displays guidance unavailable.
- **Focused command:** `uv run pytest -q tests/integration/test_husbandry_references.py
  tests/unit/application/test_husbandry_reference_schema.py`.
- **Commit:** `feat: add curated husbandry reference profiles`.

No husbandry statements ship until the owner approves their specific primary sources and bundle
contents. The implementation may build and test the schema with clearly marked fixture data, but
fixture guidance never loads in production.

### Task 11 — Complete strict-CSP PWA and accessible product experience

- **Files:** add pinned frontend dependency metadata, locally served vendor assets, `app.js`,
  `manifest.webmanifest`, `service-worker.js`, `offline.html`, PWA icons, navigation/templates, and
  browser/security tests.
- **Projection work:** none beyond freshness presentation.
- **Routes/screens:** installable shell, offline guidance, responsive primary navigation, reports,
  search, dashboard, analytics, and provenance disclosures.
- **Tests:** no inline/generated JavaScript, no unsafe CSP directives, service-worker cache allowlist,
  authenticated-response exclusion, offline mutation rejection, cache-version upgrade, logout
  clearing, keyboard/focus/live regions, reduced motion, and desktop/phone WCAG 2.2 AA.
- **Data/migration:** no database change. Draft persistence remains deny-by-default with **zero M6
  forms allow-listed initially**.
- **Capability enforcement:** server authorization remains mandatory regardless of cached shell or
  hidden controls.
- **Evidence:** `m6-product-experience/security/csp`, `tests/pwa`,
  `accessibility/critical-journeys`, and `browser`.
- **Rollback/rebuild:** bump cache version and delete obsolete public caches; an unavailable service
  worker leaves the online server-rendered application functional.
- **Focused command:** `uv run pytest -q tests/security/test_csp_pwa.py
  tests/browser/test_product_experience.py` plus documented Playwright/Pa11y runs.
- **Commit:** `feat: complete accessible read-only PWA experience`.

### Task 12 — Qualify M6 and assemble reproducible evidence

- **Files:** create `scripts/fixtures/generate_representative_dataset.py`,
  `scripts/benchmarks/phase6_qualification.py`, qualification tests, and the structured
  `docs/evidence/m6-product-experience/` package.
- **Projection work:** cold/warm rebuild and query measurements for all four groups, including FTS
  optimize/integrity, tail catch-up, swap, rollback, cleanup, WAL, and storage headroom.
- **Routes/screens:** real-browser desktop and 390×844 journeys covering every M6 roadmap screen.
- **Tests:** full quality gate; migration lifecycle; M0–M5.5 replay/backup compatibility; search
  leakage; report reconciliation; analytics/suggestions; PWA/CSP; accessibility; backup/isolated
  restore; amd64 Compose; ARM64 OCI; dependency/container/security scans.
- **Data/migration:** generate `snaketracker-reference-v1` deterministically with manifest/hash and
  record cache state, host, filesystem, SQLite, Python, Docker, encryption, and concurrency mix.
- **Capability enforcement:** qualify a mixed Snake/Spider household and negative cross-household,
  financial-role, unsupported-profile, and inapplicable-analytics cases.
- **Evidence:** `tests`, `security`, `operations`, `performance/laptop-container`, `containers`,
  `browser`, `accessibility`, `references`, `reviews`, and `approvals` below the M6 evidence root.
- **Rollback/rebuild:** rehearse generation rollback, interrupted rebuild cleanup, application
  downgrade guard, backup restore, and safe startup with unknown newer metadata.
- **Qualification commands:** `./scripts/quality/check.sh`; focused M6 suites; Alembic lifecycle;
  `docker compose up --build -d --wait`; `docker buildx build --platform linux/arm64 ...`; and the
  documented Playwright/Pa11y/performance commands.
- **Commit:** `docs: record M6 implementation qualification`.

## Evidence and acceptance mapping

| M6 criterion | Principal evidence |
| --- | --- |
| Authorized FTS5 search | `tests/search`, `security/search-authorization`, FTS swap evidence |
| Reconciled reports | `tests/reports`, export audit and effective-history fixtures |
| Material freshness visible | `tests/async-freshness`, browser stale/rebuild states |
| Strict CSP | `security/csp` and real-browser policy capture |
| Read-only PWA | `tests/pwa`, offline and cache inspection |
| WCAG 2.2 AA | `accessibility/critical-journeys` and desktop/mobile scans |
| Development targets | `performance/laptop-container`, representative dataset manifest |
| Weight/length and care analytics | measurement, feeding, and husbandry analytics suites |
| Suggested windows | policy fixtures, explanation snapshots, effective-history rebuild tests |
| Curated references | source bundle manifest, provenance/version/precedence tests |

## Proposed commit sequence

1. `feat: establish M6 read-model compatibility boundary`
2. `feat: add asynchronous product projection runner`
3. `feat: add authorized FTS5 keeper search`
4. `feat: add capability-aware keeper reports`
5. `feat: add accessible measurement trends`
6. `feat: add effective feeding analytics`
7. `feat: add capability-specific husbandry trends`
8. `feat: add explainable keeper dashboard`
9. `feat: add deterministic care-window suggestions`
10. `feat: add curated husbandry reference profiles`
11. `feat: complete accessible read-only PWA experience`
12. `docs: record M6 implementation qualification`

## Risks and rollback points

- **Projection lag or storage growth:** keep groups independent, expose freshness, measure the full
  representative dataset, and retain one validated generation before cleanup.
- **FTS disclosure:** enforce household and capability predicates inside the repository and seed
  authorization-negative documents; any leakage blocks M6.
- **Misleading analytics:** require effective history, explicit applicability, minimum samples, and
  textual provenance; insufficient data remains absent.
- **Reference-data authority:** ship no unapproved guidance; invalid/unknown bundles fail safely and
  explicit absence is a valid result.
- **Frontend supply chain/CSP:** pin and locally serve audited assets, retain licenses/checksums, and
  fail CI on CSP or dependency regressions.
- **Downgrade incompatibility:** 0011 and startup compatibility stop older binaries from opening M6
  state; cleanup plus backup is required before downgrade.
- **M7 scope creep:** native Pi, remote deployment, production recovery, AI, sensors, cameras,
  breeding, new animal types, and unrestricted offline synchronization remain prohibited.

## Owner approvals embedded in this plan

Approval of this plan confirms:

1. the deterministic minimum-history/MAD/window policy above, including the 10% proportional
   uncertainty floor that is never presented as a confidence percentage;
2. HTML plus CSV as the M6 report/export boundary, with no PDF implementation;
3. zero browser-persisted drafts in M6 unless a later form receives a separate security review; and
4. no production husbandry reference content until its exact sources and bundle are presented for
   owner approval.

No new ADR is presently required. The 0011 relational/catalog extension and projection catalog
details implement accepted ADR-0008, ADR-0038, and ADR-0039. If implementation requires changing a
projection consistency class, introducing an authoritative analytics aggregate, allowing offline
writes, or weakening reference provenance, stop and propose an architecture-freeze amendment before
continuing.
