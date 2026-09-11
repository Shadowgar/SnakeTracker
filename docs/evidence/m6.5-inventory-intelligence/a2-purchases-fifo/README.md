# M6.5-A2 Purchases, FIFO Valuation, and Cash-spend Facts

Status: **implemented and qualified; owner review pending**

Requirements `R-073` through `R-075`; acceptance procedures `AT-INVINT-04`, `AT-INVINT-05`,
and `AR-INVINT-01`. Branch `phase6.5/purchases-fifo`. M6.5 is not complete or owner-accepted.

## Implemented boundary

- One Purchase aggregate represents a real receipt with one to 25 Inventory lines. Posting uses
  one atomic multi-stream append for the Purchase and every linked version-3 stock receipt.
- Every line uses the Item's same-household canonical unit and a stable line ID. Positive integer
  minor-unit subtotals plus tax and fees less discount must exactly equal the positive total paid.
- Largest-remainder allocation capitalizes shared charges exactly and uses stable line-ID tie
  breaking. No floating-point money, currency conversion, or mutable Item price is introduced.
- Purchase is the sole purchase cash-spend source and does not create an Expense event. The
  Expenses experience labels Supply purchases separately from Other expenses.
- FIFO orders effective layers/depletions by occurrence time, recorded time, global position, and
  event ID. Partial-lot cumulative allocation assigns the final remainder cent exactly. Currencies
  remain separate, and historical/manual stock without Purchase cost remains explicitly unknown.
- Purchase correction, void, and reinstatement coordinate Purchase and receipt streams atomically.
  Invalid stock removal fails without a partial Purchase, receipt, cash, or balance change.
- Balance, effective receipts, and Purchase current state remain synchronous correctness inputs.
  FIFO lots/allocations and unified cash-spend facts use asynchronous, rebuildable generations with
  checkpoint freshness and unavailable/lagging presentation.

## Migration and live-data safety

Expand-only migration `0015_purchases_fifo` adds `purchase_current`, `purchase_line_current`, and
`inventory_effective_receipts`. It preserves immutable history and backfills prior receipts as
unknown-cost layers without guessing Purchase linkage. Generated FIFO/cash tables are not fixed
migration state.

The active paths were explicitly resolved as:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`
- attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`

No destructive command targeted either path. The isolated migration root was
`/tmp/carekeeper-a2-migration.ba1MsJ`. A zero-to-head database and an online copied live snapshot
both migrated to 0015 with integrity `ok`, zero foreign-key violations, and eight active product
projection definitions. The copied snapshot retained all 717 events at high-water 717 and the
pre-migration event identity/checksum hash
`907bf04333c2fdde614f392b8f2bb282428b4bf754e5d3acf4f4e7e3cf81c7e7`.

Before copied-snapshot qualification and deployment, the worker-owned pipeline created encrypted,
non-overwriting backup request `3e6ed004-652c-43a2-9cfe-2eaf7e110899`, run
`5ff003fa-1265-422b-8fc4-0fcfcdb35ac4`, with encrypted manifest SHA-256
`8805e339986e215dc0ec7325f4d5913b6b82c0a3027f0e03f93f6ab0015812a7`. Independent verification
reported migration 0014, high-water 717, and 33 referenced attachments.

Restore was rehearsed only into isolated target
`/tmp/carekeeper-a2-restore-host.9Rvdg6/5ff003fa1265422b8fc40fcfcdb35ac4`. It reported integrity
`ok`, zero foreign-key violations, migration 0014, 717 events at high-water 717, the exact event
hash above, and 33 restored attachments. The isolated restored target was then removed; the active
database was never restored over.

## Automated qualification

Focused A2 integration/browser and projection-worker tests cover atomic posting, total validation,
idempotent retry, 25-line bounds, household isolation, correction/add/remove lines, refused void
rollback, reinstate, changing prices, partial quantities, final-cent reconciliation, backdating,
unknown cost, currency separation, cash uniqueness, projection lag, generation rebuild, and
rollback. The focused A2 integration suite passed 21 tests. The exact authoritative command was:

```text
uv sync --frozen
./scripts/quality/check.sh
```

It passed formatting and Ruff across 451 files, the 42-ADR accepted architecture freeze,
documentation links across 206 files, strict mypy across 130 source files, all 554 tests,
dependency audit, Compose validation, and diff checks. Coverage passed at 94.69% lines and 85.01%
branches; `coverage.json`, `coverage.xml`, and `junit.xml` were generated.

## Native ARM64 browser and accessibility qualification

The promoted image is `snaketracker:m65-a2`, ARM64 image
`sha256:a483407510030b945e0d7abd7ee662566596eee307d1eb1dab3bbedbe5de049f`,
built for and running as UID/GID `1001:1001` on the Raspberry Pi.

The write journey ran only against the isolated online snapshot target
`/tmp/carekeeper-a2-browser.kqgOum`, never the active database. Native Chromium exercised a
two-line Purchase, exact total reconciliation, one-row-per-click line editing, atomic stock
receipt, one cash-spend fact, two FIFO lots, correction, void, reinstatement, Inventory FIFO value,
and single rendering in Expenses. The final isolated state had Purchase stream version 4, two
active linked receipts, integrity `ok`, and zero foreign-key violations. The isolated runtime and
target were removed after evidence capture.

Seven isolated and four public-origin axe checks reported zero WCAG 2.2 AA violations. Both
1440×900 desktop and 390×844 mobile views had no document-level horizontal overflow. After the
complete attachment snapshot was present, isolated console capture reported zero application
errors, page errors, HTTP errors, or failed requests.

Owner-review captures:

- [desktop Purchase form](screenshots/desktop-1440x900-purchase-form.png)
- [desktop Purchase detail](screenshots/desktop-1440x900-purchase-detail.png)
- [desktop Inventory FIFO value](screenshots/desktop-1440x900-inventory-fifo.png)
- [desktop Expenses](screenshots/desktop-1440x900-expenses.png)
- [mobile Purchase form](screenshots/mobile-390x844-purchase-form.png)
- [mobile Purchase detail](screenshots/mobile-390x844-purchase-detail.png)
- [mobile Inventory FIFO value](screenshots/mobile-390x844-inventory-fifo.png)
- [live desktop Purchase form](screenshots/live-desktop-1440x900-purchase-form.png)
- [live mobile Purchase form](screenshots/live-mobile-390x844-purchase-form.png)

Machine-readable results and artifact paths are in
[`browser-qualification.json`](browser-qualification.json).

## Console and CSP decision

Public-origin console capture had zero Care Keeper JavaScript/runtime errors and zero CSP
violations caused by Care Keeper-owned resources. Cloudflare changed the public HTML by adding a
same-origin `/cdn-cgi/.../email-decode.min.js` loader plus one inline challenge loader that is not
present in the direct origin HTML. That injected code attempted to load
`static.cloudflareinsights.com/beacon.min.js` and execute paired inline scripts. Care Keeper's
intentional `script-src 'self'` policy blocked both, producing seven external-beacon and seven
paired inline-loader diagnostics during repeated navigations. Axe produced no CSP diagnostic in
this run. The origin and public response retained the same strict policy; no Cloudflare host,
`unsafe-inline`, `unsafe-eval`, nonce, hash, or other allowance was added.

## Promoted runtime and live integrity

Migration `0015_purchases_fifo` is applied on the active database. After deployment, SQLite
integrity remained `ok`, foreign-key violations remained zero, and the database retained 717
events at high-water 717. The ordered identity/checksum hash for those events remained exactly
`907bf04333c2fdde614f392b8f2bb282428b4bf754e5d3acf4f4e7e3cf81c7e7`; household, user, Animal,
Enclosure, Inventory, and attachment counts were unchanged. The 40-file attachment tree hash
remained `d9c69298591f8d42adb9ca6a43174ac17a3925d718bf8034866e79444e375fab`.

The live public smoke was read-only for domain data and covered Purchases, Add Purchase, and
Expenses at desktop and mobile sizes. Web, worker, and Nginx remained healthy on the one active
Compose stack, with web and worker running the promoted image.

## Explicitly deferred

Physical/cycle counts, usage forecasting, remaining-duration/excess signals, advanced Inventory
Overview, expanded reports/CSV, and spending estimates remain M6.5-B/C work. This evidence does not
accept A2, M6.5, or any later milestone.
