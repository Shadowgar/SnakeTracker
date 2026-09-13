# M6.5-C Expense Integration and Inventory Reports

Status: **implemented and qualified; owner review pending**

Requirement `R-076`; acceptance procedure `AT-INVINT-06`. Branch
`phase6.5/expense-reports`. M6.5 is not complete or owner-accepted.

## Implemented boundary

- Expenses and its CSV present every effective Purchase once as a **Supply purchase** and every
  independent Expense once as an **Other expense**. A Purchase is not duplicated as an editable
  Expense.
- The household Inventory & spending report has explicit 30/90 complete-day and currency controls.
  It keeps supply cash, other-expense cash, known value used, expiry/variance value, and current
  known stock value distinct.
- The report is visually led by summary metrics and locally rendered Chart.js charts for spending
  over time, spending by category, bought versus used, and current known stock value. Attention and
  plain-language explanation follow; exact reconciliation tables and protected CSV exports are
  secondary. Chart input is authoritative server-derived read-side data rather than browser-side
  financial calculation.
- Category and Item tables expose period purchase/use quantities and values, current stock/value,
  reorder and count attention, fixed-window unused observations, and unknown-cost stock. Quantities
  with unlike units are never summed. Unknown acquisition cost is disclosed and never changed to
  zero.
- Item reports show 30/90-day usage evidence, supported rate/duration, last count facts, latest
  effective acquisition, lifetime known-value reconciliation, period expiry/variance, projection
  freshness, and source explanation.
- Potential replenishment appears only for Care supplies with a supported use rate and a positive
  effective acquisition cost from the prior 365 days in the selected currency. The report uses
  available stock, discloses horizon, quantity, latest cost/date, stock/target assumption, and says
  **Estimate only—not a vendor quote or guarantee**.
- HTML and CSV resolve data through the authenticated household. CSV applies the existing formula
  injection protection and contains no event, household, user, or other internal identifiers.
  Tables retain row/column semantics and collapse responsively at the accepted mobile breakpoint.

M6.5-C itself adds no event contract, domain write behavior, or schema migration. Its owner-review
correction also removes FIFO, cost-basis, depletion-layer, and projection-internals terminology
from normal keeper-facing report templates while preserving the deterministic internal accounting
policy. The Chart.js dependency and `/static/report-charts.js` are self-hosted; production CSP was
not weakened.

The bounded internal cost-activity reader groups effective allocations into consumption, expiry,
and variance for an explicit household, Item, half-open time range, and currency. Unknown-cost
stock is always reconciled separately.

## Decimal animal-weight correction

The separately committed live-bug correction replaces whole-number-only body-weight writes with an
exact fixed-point representation: `weight_grams_scaled: int`, where one gram is 1,000 scaled units
and supported precision is 0.001 g. Keeper strings are parsed with `Decimal`; zero, negative,
malformed, scientific-notation, and over-precision input is rejected without rounding.

Existing `animal.weight_recorded` and `animal.weight_corrected` V1 events remain immutable and
replay as whole grams normalized into the same internal scale. New writes use
`AnimalWeightRecordedV2` and `AnimalWeightCorrectedV2`. A V2 correction can target an effective V1
record. Central normalization and formatting produces natural output such as `525 g`, `42.5 g`,
`8.25 g`, and `0.875 g`; timeline, correction forms, reminder/effective-state handling, and
measurement analytics all consume the shared representation. Analytics retains `Decimal` until
the numeric JSON presentation boundary. No event rewrite or SQL migration was required.

## Automated qualification

Focused unit, projection, purchase, report, authorization/isolation, CSV, and browser tests cover
the representative `$65 / 50` acquisition and `$23.40 / 18` consumption reconciliation,
expiry/variance classification, multiple currencies without mixing, unsupported estimate states,
formula-safe export, invalid period/currency input, and cross-household direct Item/CSV denial.

The original M6.5-C journey used native ARM64 Chromium 1208 against the isolated restored database
at `/tmp/carekeeper-m65-c-restore-host-325c741a/verified/325c741a2378454c97f5200530272f56/snaketracker.sqlite3`.
The active database was explicitly recorded as
`/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3` and was never a browser target. The
journey covered the collection Inventory & spending report, a costed Dubia Roaches Item with
recorded consumption, the integrated Expenses page, both CSVs, desktop 1440×900, and mobile
390×844. Six axe WCAG 2.2 AA scans reported zero violations; all six pages had no horizontal
overflow. Console capture reported zero application diagnostics, page errors, request failures, or
HTTP errors. The machine-readable result is
[`browser-qualification.json`](browser-qualification.json).

Owner-review captures are:

- Inventory & spending: [mobile](screenshots/mobile-390x844-inventory-spending-collection.png),
  [desktop](screenshots/desktop-1440x900-inventory-spending-collection.png)
- Item reconciliation: [mobile](screenshots/mobile-390x844-inventory-item-reconciliation.png),
  [desktop](screenshots/desktop-1440x900-inventory-item-reconciliation.png)
- Integrated Expenses: [mobile](screenshots/mobile-390x844-expenses-integrated-spending.png),
  [desktop](screenshots/desktop-1440x900-expenses-integrated-spending.png)

The owner-review correction used a separate writable copy at
`/tmp/carekeeper-m65-correction-IllXzRzG/snaketracker.sqlite3`; the active database path was checked
and rejected as a possible target before the journey. A web and worker pair using the corrected
native ARM64 image caught every isolated projection up to the isolated event high-water of 772.
The journey exercised meaningful 30-day and 90-day reports, all four required charts, period-data
changes, readable category labels, unknown-cost disclosure, a meaningful Item chart, sparse Item
fallback, decimal entry, correction, history, over-precision validation, and decimal analytics.
The analytics API and chart preserved `[8.175, 0.875]` exactly at the presentation boundary.

Across 14 mobile 390×844/desktop 1440×900 page scans, axe reported zero violations and every page
had zero horizontal overflow. Chart canvases were non-zero and sensibly sized (mobile report width
346 px; heights 240–322 px; mobile measurement chart 338×208 px). Console capture found zero Care
Keeper JavaScript diagnostics, page errors, failed requests, or unexpected HTTP errors. The one
deliberate invalid `8.2579` submission returned the expected readable 422 validation response.
Machine-readable assertions and artifact paths are in
[`owner-correction-browser-qualification.json`](owner-correction-browser-qualification.json).

Visual-first report captures:

- Meaningful 30-day report: [mobile](screenshots/mobile-390x844-owner-correction-report-30-day.png),
  [desktop](screenshots/desktop-1440x900-owner-correction-report-30-day.png)
- Meaningful 90-day report: [mobile](screenshots/mobile-390x844-owner-correction-report-90-day.png),
  [desktop](screenshots/desktop-1440x900-owner-correction-report-90-day.png)
- Meaningful Item: [mobile](screenshots/mobile-390x844-owner-correction-item-meaningful.png),
  [desktop](screenshots/desktop-1440x900-owner-correction-item-meaningful.png)
- Sparse Item: [mobile](screenshots/mobile-390x844-owner-correction-item-sparse.png),
  [desktop](screenshots/desktop-1440x900-owner-correction-item-sparse.png)

Decimal-weight captures:

- Entry: [mobile](screenshots/mobile-390x844-decimal-weight-entry.png),
  [desktop](screenshots/desktop-1440x900-decimal-weight-entry.png)
- Readable over-precision validation:
  [mobile](screenshots/mobile-390x844-decimal-weight-validation.png)
- Corrected effective history: [mobile](screenshots/mobile-390x844-decimal-weight-history.png),
  [desktop](screenshots/desktop-1440x900-decimal-weight-history.png)
- Decimal trend: [mobile](screenshots/mobile-390x844-decimal-weight-trend.png),
  [desktop](screenshots/desktop-1440x900-decimal-weight-trend.png)

## Live-data safety and backup

Before qualification, the active paths were explicitly resolved as:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`;
- Attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`; and
- backups: `/home/rocco/SnakeTracker/runtime/phase2/backups`.

The live baseline and post-browser comparison both contain 743 events at high-water 743 with
ordered event identity/checksum hash
`2dd2fdb9dd3bee8751dfd4700953b396da13cb17551207e0da70ba9c2f2226f9`. SQLite integrity is
`ok`, foreign-key violations are zero, and the Attachment tree remains byte-identical under the
same container-side algorithm with hash
`0ce316009a1127871bbe3101849b76df5b898b1c0d3386ec815e570659110c73`. The browser used only
the isolated restored copy and wrote no live domain data.

Legitimate concurrent live-user activity occurred after that comparison and before/during final
promotion. The final read-only observation at `2026-09-13T03:06:42-04:00` found 773 events and 28
Inventory Items. Positions 744–755 are one Purchase/receipt, two Inventory registrations, one Item
update, two Inventory-authoritative Feedings/consumptions, one weight, and one care-record void.
Positions 756–773 are one further Inventory registration/receipt followed by eight
Inventory-authoritative Feeding/consumption pairs. Qualification issued none of those commands.
The saved first-743-event prefix retains the exact baseline hash above; household/user/Attachment
counts remain 4/4/39, and the Attachment hash is unchanged. Final SQLite integrity is `ok` with
zero foreign-key violations.

The worker completed non-overwriting encrypted backup request
`ea91f75b-0439-4172-81b7-0626b6578001`, run
`325c741a-2378-454c-97f5-200530272f56`. The encrypted database is 12,652,577 bytes with SHA-256
`351b14cdec8409b3c8877a624dd051ac792460e776e4e8a2a313348975c78c7f`; the 24,329-byte
encrypted manifest has SHA-256
`ec2f76f4a74adf6519319f3de769957a6820a75ff97a10b82a9591ab8a3d0341`. The first restore
attempt correctly targeted an isolated container `/tmp`, but that container's bounded 16 MiB tmpfs
returned `OSError: [Errno 28] No space left on device` while copying Attachments. It did not touch
an active path. The same encrypted run then restored successfully to the explicit host-backed
isolated target above, reporting `verified` with 33 referenced Attachments. No restore was
performed over the active database.

Immediately before this combined owner correction, the active runtime was explicitly rechecked at
809 events/high-water 809. Its ordered position/event-identity/checksum hash was
`2352c365c4f34c49b1a375d4ec240f91938490d80a18f3297a545ac466b9647b`; SQLite integrity was
`ok`, foreign-key violations were zero, and counts were four households, four users, 42 Animals,
29 Enclosures, 30 Inventory Items, and 39 finalized Attachment versions. The 40-file Attachment
tree retained the previously recorded hash
`0ce316009a1127871bbe3101849b76df5b898b1c0d3386ec815e570659110c73`.

A fresh, non-overwriting encrypted backup completed before promotion: request
`55340d04-8eee-48dc-8db2-71c3334eabec`, run
`a64ca575-bfdf-4df4-8415-909414cf74be`. The 13,418,529-byte encrypted database has SHA-256
`a3a531ff8d449f5479fe825e5cbb8d304a9dc1fb245f52057ddba2b7aa77d51c`; the 24,489-byte
encrypted manifest has SHA-256 and manifest checksum
`a86cc56428ac93604dde4706de6f894ed96198373b16e02f1cda99bfd5b3b995`. The worker completed
its verification pipeline. Because this correction has no schema migration and the immediately
preceding M6.5-C backup already passed an isolated restore rehearsal, no destructive restore was
repeated and the active runtime was never a restore target.

After promotion, the active database remained exactly at 809 events/high-water 809 with the same
ordered hash, counts, SQLite `ok`, and zero foreign-key violations. The browser qualification made
no live writes. Migration head remains `0018_inventory_stock_roles`.

The corrected owner-review image is native ARM64 `snaketracker:m65-c-owner-correction`, SHA-256
`cb51cc6898606530d24ec6bf3a6128988a9e5994295616040a3528208783cb40`, built and promoted for
UID/GID `1001:1001`. Web, worker, and Nginx are healthy; local and public readiness return `ready`;
web and worker run as UID/GID `1001:1001`; and exactly one three-service Care Keeper Compose stack
remains active.

## Authoritative quality

The exact authoritative path is:

```text
uv sync --frozen
./scripts/quality/check.sh
```

The exact post-correction gate passed formatting across 463 files, Ruff, the 42-ADR accepted
architecture freeze, documentation links across 208 files, strict mypy across 133 source files,
all 619 tests in 801.94 seconds, coverage artifact generation, dependency audit, Compose
validation, and diff checks. JUnit reports zero failures, errors, or skipped tests. Coverage is
94.52% lines and 85.08% branches. `coverage.json`, `coverage.xml`, and `junit.xml` were produced,
and the strict dependency audit reports no known vulnerabilities. The first run had correctly
stopped at 84.99% branch coverage; one focused spending-direction regression test brought the
authoritative gate above its 85% threshold before this final successful run.

## Scope boundary

M6.5-D final milestone qualification and acceptance, M7 formal recovery/deployment qualification,
M8 release qualification, M9 public media, and unrelated UX work have not begun.
