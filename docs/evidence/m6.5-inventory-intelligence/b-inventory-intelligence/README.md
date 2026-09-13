# M6.5-B Inventory Intelligence and Physical Counts

Status: **implemented and qualified; owner review pending**

Requirements `R-070` through `R-072`; acceptance procedures `AT-INVINT-01` through
`AT-INVINT-03`. Branch `phase6.5/inventory-intelligence-ux`. M6.5 is not complete or
owner-accepted.

## Implemented boundary

- Inventory Overview and Item detail now present available quantity, owner-defined reorder state,
  last restock and verification, 30/90-day effective use, supported usage pace, estimated duration,
  and owner-maximum excess or fixed-window disuse observations.
- Rate support is deterministic: at least 28 observed household-local calendar days, at least two
  distinct effective-use dates, positive effective use, and the half-open `[window start, as-of)`
  boundary. Sparse history says **Not enough usage history** and never invents a duration.
- **Reorder now** requires only the owner's minimum. **Reorder soon** additionally requires a
  supported rate and owner-entered supplier lead time. No husbandry threshold or opaque confidence
  score exists.
- A mobile-first Count stock flow supports full, Inventory Type category, rolling/due, and single
  Item scope. Every Item save is independently durable. It records expected, actual, exact
  variance, context, workflow, actor, and time, including zero variance.
- Count correction atomically appends `event.voided` and a replacement
  `inventory.stock_counted` fact. Original history is retained and stock effect is applied exactly
  once. A concurrency conflict preserves the entered actual quantity and refreshes expected stock.
- Generic **Use inventory** records scaled consumption with a controlled Care, Maintenance,
  Discarded, or Other context. Feeding remains Inventory-authoritative under accepted A1 semantics.
- Inventory count variance participates in the existing deterministic FIFO value projection as an
  unknown-basis increase or a variance depletion; correction rebuilds from the effective count set.
- The asynchronous intelligence generation is household-scoped and rebuildable. A stale generation
  returns unavailable labels instead of serving a stale estimate.
- The owner-review correction replaces the flat Inventory overview with Care stock (default),
  Equipment & spares, All inventory, and Archived views. Care and All views are grouped by
  controlled Type; Equipment & spares is separated into Replacement / spare and Equipment groups.
  Search and Low stock, Check due, and Cost not tracked filters operate inside each selected view.
- One centralized stock-role model classifies Care supplies, Replacement / spares, and durable
  Equipment. Existing structured rows derive a safe role without rewriting history; new and edited
  rows persist an owner-overridable role. Water & Hydration is an additive controlled Type with
  volume and Bottle/Jug/Case tracking.
- Keeper-facing **Check stock** replaces warehouse terminology. A due CTA opens the first eligible
  item directly, a matching amount is confirmed with one tap while still recording the zero-variance
  event, changed amounts advance automatically, and completion lists only differences.
- Stock-check attention now requires an owner-configured recurrence. Never-counted stock without a
  recurrence is `not_scheduled`, legacy setup-only rows are excluded, and one shared eligibility
  function drives the dashboard count, CTA destination, and stable multi-item workflow.

## Contracts and migration

Migration `0017_inventory_intelligence` is expand-only. It adds nullable policy/verification fields
to `inventory_balance` plus household-scoped `inventory_count_history`. It neither rewrites nor
deletes prior Inventory, Purchase, Feeding, Expense, or Attachment data. Downgrade is refused after
M6.5-B contracts have been persisted.

New registered contracts are:

- `inventory.stock_consumed` v3 for generic contextual use;
- `inventory.stock_counted` v1 for the immutable physical observation and balance variance;
- `inventory.reorder_policy_changed` v2 for minimum/target/maximum/lead time; and
- `inventory.verification_policy_changed` v1 for the optional recount interval.

All legacy contracts remain registered and replayable. The startup compatibility head advances to
relational schema version 18 after the additive `0018_inventory_stock_roles` migration. That
migration adds only a nullable projection override, leaves old events and quantities unchanged, and
blocks downgrade once role-aware v3 history exists. Role-aware Item registration and update use
`inventory.item_registered` v3 and `inventory.item_updated` v3; earlier versions remain registered.

## Owner-review correction qualification

The correction specifically covers stock-role derivation and override, Water & Hydration units,
care/equipment filtering, Type grouping, lightweight search/filters, role-aware detail semantics,
actionable-only attention, the reported six-due/zero-count contradiction, a stable exact three-item
due workflow, direct entry, one-tap match, changed quantity, completion summary, and 0017-to-0018
preservation/downgrade behavior. Final authoritative-gate, isolated-browser, screenshot, backup,
live migration, runtime, and GitHub results are recorded below after promotion.

## Qualification

All write-oriented qualification uses pytest temporary directories and disposable SQLite files,
not the active Care Keeper runtime database or Attachment store. Focused suites cover:

- policy ordering and boundary validation;
- zero, positive, and negative count variance;
- full/category/cycle/single browser count flows;
- correction, idempotency, concurrency, replay equivalence, and FIFO reconciliation;
- generic use, nonnegative stock, household isolation, CSRF, and role enforcement;
- 28/90/180-day sparse/use/disuse boundaries, household-local dates, duration, lead time, owner
  maximum, verification due state, and supported period comparison;
- migration zero-to-head, 0016-to-0017 preservation, downgrade guard, integrity, and foreign keys;
  and
- accepted A1/A2 browser and domain regression coverage.

## Automated qualification

The exact authoritative path was run after the final accessibility and CI-timezone corrections:

```text
uv sync --frozen
./scripts/quality/check.sh
```

It passed formatting and Ruff across 460 files, the 42-ADR accepted architecture freeze,
documentation links across 207 files, strict mypy across 132 source files, all 600 tests,
dependency audit, Compose validation, and diff checks. Coverage artifacts report 94.58% lines,
85.19% branches, and 92.69% combined coverage. `coverage.json`, `coverage.xml`, and `junit.xml`
were produced; JUnit reports zero failures, zero errors, and zero skipped tests.

The initial GitHub run exposed a browser-test fixture defect rather than an application defect:
the Inventory intelligence helper supplied the CI host's naive UTC wall time to a
household-local `datetime-local` field, so the correctly validated acquisition appeared to be in
the future. The helper now submits the household-local default rendered by the application, which
is the same contract used by the real browser form. The four affected tests pass under an explicit
`TZ=UTC` runner environment and in the complete frozen authoritative gate; production date
validation was not relaxed.

The focused browser journey used native ARM64 Chromium 1208 against the disposable restored
database at
`/tmp/carekeeper-m65-b-browser.9Phd5D/a3c0637bd810434abdba8023159413ef/snaketracker.sqlite3`.
It exercised policy editing, generic Inventory use, a single-Item physical count, completion,
correction entry, Overview intelligence, and Item intelligence at desktop 1440×900 and mobile
390×844. All 14 page-level axe checks had zero violations. Browser capture had zero application
console errors, page errors, HTTP errors, or failed requests. The machine-readable result is
[`browser-qualification.json`](browser-qualification.json). Owner-review captures are:

- [desktop Inventory Overview](screenshots/desktop-1440x900-inventory-overview.png)
- [desktop Inventory Item](screenshots/desktop-1440x900-inventory-detail.png)
- [desktop stock policy](screenshots/desktop-1440x900-stock-policy.png)
- [desktop count start](screenshots/desktop-1440x900-count-start.png)
- [desktop count Item](screenshots/desktop-1440x900-count-stock.png)
- [desktop count complete](screenshots/desktop-1440x900-count-complete.png)
- [desktop count correction](screenshots/desktop-1440x900-count-correction.png)
- [mobile Inventory Overview](screenshots/mobile-390x844-inventory-overview.png)
- [mobile Inventory Item](screenshots/mobile-390x844-inventory-detail.png)
- [mobile stock policy](screenshots/mobile-390x844-stock-policy.png)
- [mobile count start](screenshots/mobile-390x844-count-start.png)
- [mobile count complete](screenshots/mobile-390x844-count-complete.png)
- [mobile count correction](screenshots/mobile-390x844-count-correction.png)

The owner-review correction then ran in native ARM64 Chromium 1208 against the isolated restored
database at
`/tmp/carekeeper-m65-b-correction-browser.0nRmwz/e3b6e0f5ee164f25bac7e13336c1002c/snaketracker.sqlite3`.
The active database was explicitly excluded. The journey proved the calm zero-attention state,
three genuinely actionable Care-stock items, an exact two-item due CTA and destination, direct
entry, `1 of 2` / `2 of 2` stable progress, one-tap zero-variance acceptance, a 20-to-18
correction, Water & Hydration, separate Equipment and Replacement / spare groups, Type-grouped All
Inventory, and a difference-only completion summary. Across 22 required viewport states, axe
reported zero violations and capture reported zero horizontal overflow, application console
diagnostics, page errors, failed requests, or HTTP errors. A focused post-review run after the
completion-row spacing correction repeated the affected axe/overflow/console checks successfully.
The machine-readable result is
[`browser-owner-correction.json`](browser-owner-correction.json).

Owner-review correction captures, each framed at the literal requested viewport size, are:

- Care Stock default: [mobile](screenshots/owner-correction-mobile-390x844-care-stock-default-overview.png), [desktop](screenshots/owner-correction-desktop-1440x900-care-stock-default-overview.png)
- Food section: [mobile](screenshots/owner-correction-mobile-390x844-food-section.png), [desktop](screenshots/owner-correction-desktop-1440x900-food-section.png)
- Equipment & spares: [mobile](screenshots/owner-correction-mobile-390x844-equipment-and-spares.png), [desktop](screenshots/owner-correction-desktop-1440x900-equipment-and-spares.png)
- All Inventory grouped: [mobile](screenshots/owner-correction-mobile-390x844-all-inventory-grouped.png), [desktop](screenshots/owner-correction-desktop-1440x900-all-inventory-grouped.png)
- Actionable attention: [mobile](screenshots/owner-correction-mobile-390x844-attention-actionable-items.png), [desktop](screenshots/owner-correction-desktop-1440x900-attention-actionable-items.png)
- Calm state: [mobile](screenshots/owner-correction-mobile-390x844-no-attention-calm-state.png), [desktop](screenshots/owner-correction-desktop-1440x900-no-attention-calm-state.png)
- Check Stock start: [mobile](screenshots/owner-correction-mobile-390x844-check-stock-start.png), [desktop](screenshots/owner-correction-desktop-1440x900-check-stock-start.png)
- Direct due workflow: [mobile](screenshots/owner-correction-mobile-390x844-direct-due-items-workflow.png), [desktop](screenshots/owner-correction-desktop-1440x900-direct-due-items-workflow.png)
- One-tap match: [mobile](screenshots/owner-correction-mobile-390x844-quick-yes-matches-stock-check.png), [desktop](screenshots/owner-correction-desktop-1440x900-quick-yes-matches-stock-check.png)
- Changed quantity: [mobile](screenshots/owner-correction-mobile-390x844-changed-quantity-stock-check.png), [desktop](screenshots/owner-correction-desktop-1440x900-changed-quantity-stock-check.png)
- Completion summary: [mobile](screenshots/owner-correction-mobile-390x844-completion-summary.png), [desktop](screenshots/owner-correction-desktop-1440x900-completion-summary.png)

## Live-data safety, backup, and deployment

The active paths were resolved before qualification as:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`;
- attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`; and
- backups: `/home/rocco/SnakeTracker/runtime/phase2/backups`.

The worker-owned, non-overwriting encrypted backup completed as request
`be68394b-5499-4c0d-a5a4-1a56ab04fbdd`, run
`a3c0637b-d810-434a-bdba-8023159413ef`. Its encrypted manifest SHA-256 is
`37da9a91b22e71a5e8d4bc9acdb031c7df8f5d9fc33e9dcb01a194fc498a97d3` and its encrypted
archive is 24,249 bytes. Restore was verified only under
`/tmp/carekeeper-m65-b-restore.yq4Vdi`, outside all active paths, with 33 referenced Attachments,
SQLite integrity `ok`, zero foreign-key violations, and the saved 727-event prefix intact. The
isolated restored copy migrated from 0016 to 0017 without changing that event prefix.

The initial live read-only baseline contained 727 events at high-water 727, with ordered event
identity/checksum hash `bf80fad1a650917bd54999e6ede2dec537415ba0b30e8f212ed846729c419d7d`.
Before migration, legitimate concurrent owner activity advanced the live store to 732 events and
25 Inventory Items. The resulting 732-event prefix hash was
`57e93c4963fd95b48192fdddb00b127f063a1618e521bb1ba22276b779939301`.
After final deployment the live store contained 734 events at high-water 734; the first 732 events
retain that exact hash. The two later events are concurrent live-user activity: the browser journey
used only the disposable database and records
`active_database_mutated_by_browser_qualification: false`. The final live database has integrity
`ok`, zero foreign-key violations, four households, four users, 42 Animals, 29 Enclosures, 25
Inventory Items, and 39 finalized Attachment versions. The Attachment store remains 40 files with
tree hash `5e77a73f0304f3cedc4c8646f2f43eb41e12b7ed77767c9a489bcab70da78cd2`.

Migration `0017_inventory_intelligence` is applied. The promoted native ARM64 image is
`snaketracker:m65-b-owner-review`, SHA-256
`bbb634e811928889628896c2172a61c9fa62a58600b96218c2bd6711c2f32276`. The image refreshes
Debian security packages during its reproducible build; `libpcre2-8-0` is the fixed
`10.42-1+deb12u1` release. Web and worker run as
UID/GID `1001:1001`; web, worker, and Nginx are healthy; local and public readiness return
`ready`; nine product projection definitions are active; and exactly one Care Keeper Compose
project is running. The active database and Attachment store were never wiped, reset, reseeded,
replaced, restored over, or used for qualification writes.

Before this owner-review correction, a second non-overwriting encrypted backup completed as
request `bc886983-6b20-4e16-ac75-89db601925c9`, run
`e3b6e0f5-ee16-4f25-bac7-e13336c1002c`. The encrypted database artifact is 12,636,193 bytes with
SHA-256 `1432256184fda54ebd4d88e9f4d64b94d0cb936d420549cdd501c90aa4803d49`; the encrypted
manifest is 24,329 bytes with SHA-256
`845815411a8a60173416ce17b2dbd564220dfec1917e2c68e90bd6a45327e47c`. Restore verification
used only `/tmp/carekeeper-m65-b-correction-restore.hlI7LN`, returned status `verified`, and
restored 33 referenced Attachments. The active database was never a restore target.

Immediately before owner-correction promotion, the live runtime remained on
`0017_inventory_intelligence` with 743 events at high-water 743, four households, four users, 42
Animals, 29 Enclosures, 25 Inventory Items, and 39 Attachment versions. Its ordered event hash was
`2dd2fdb9dd3bee8751dfd4700953b396da13cb17551207e0da70ba9c2f2226f9`. After the additive
`0018_inventory_stock_roles` migration, every count and that exact event hash remained unchanged;
SQLite integrity remained `ok` with zero foreign-key violations. The 40-file Attachment tree also
remained byte-identical under the same qualification algorithm, SHA-256
`d9c69298591f8d42adb9ca6a43174ac17a3925d718bf8034866e79444e375fab` before and after.

The corrected native ARM64 image is `snaketracker:m65-b-owner-correction`, SHA-256
`d238843c73045fcb24b86cf8ce59d7e2fee3a14baa6c40e1091eeea714d4a4f4`. Migration 0018 is
applied; web, worker, and Nginx are healthy; web and worker run as UID/GID `1001:1001`; local and
public readiness return `ready`; and exactly one `snaketracker` Compose project with three active
services remains. No browser qualification write targeted the active database or Attachment store.

Care Keeper's production CSP remains unchanged. The isolated origin produced no CSP or application
console diagnostics. As established in M6 qualification, any Cloudflare Browser Insights script
blocked at the public origin by `script-src 'self'` is an expected external-platform diagnostic,
and diagnostics created solely by axe script injection are test-harness artifacts; neither is an
application-owned runtime failure or a reason to weaken CSP.

M6.5-C reports/CSV and spending estimates are explicitly out of scope, as are M6.5 final owner
acceptance and M7.
