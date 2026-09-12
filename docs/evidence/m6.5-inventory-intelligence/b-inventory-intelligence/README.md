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
relational schema version 17.

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

The exact authoritative path was run after the final accessibility correction:

```text
uv sync --frozen
./scripts/quality/check.sh
```

It passed formatting and Ruff across 459 files, the 42-ADR accepted architecture freeze,
documentation links across 207 files, strict mypy across 132 source files, all 583 tests,
dependency audit, Compose validation, and diff checks. Coverage artifacts report 94.62% lines,
85.06% branches, and 92.71% combined coverage. `coverage.json`, `coverage.xml`, and `junit.xml`
were produced; JUnit reports zero failures, zero errors, and zero skipped tests.

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

Care Keeper's production CSP remains unchanged. The isolated origin produced no CSP or application
console diagnostics. As established in M6 qualification, any Cloudflare Browser Insights script
blocked at the public origin by `script-src 'self'` is an expected external-platform diagnostic,
and diagnostics created solely by axe script injection are test-harness artifacts; neither is an
application-owned runtime failure or a reason to weaken CSP.

M6.5-C reports/CSV and spending estimates are explicitly out of scope, as are M6.5 final owner
acceptance and M7.
