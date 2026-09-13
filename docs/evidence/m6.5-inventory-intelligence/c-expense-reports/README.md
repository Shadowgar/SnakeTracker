# M6.5-C Expense Integration and Inventory Reports

Status: **implemented and qualified; owner review pending**

Requirement `R-076`; acceptance procedure `AT-INVINT-06`. Branch
`phase6.5/expense-reports`. M6.5 is not complete or owner-accepted.

## Implemented boundary

- Expenses and its CSV present every effective Purchase once as a **Supply purchase** and every
  independent Expense once as an **Other expense**. A Purchase is not duplicated as an editable
  Expense.
- The household Inventory & spending report has explicit 30/90 complete-day and currency controls.
  It keeps supply cash, other-expense cash, FIFO consumption value, expiry/variance value, and
  current known stock value distinct.
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

No event contract, domain write behavior, schema migration, CSP, or live-user record changes are
part of M6.5-C.

The bounded cost-activity reader groups effective FIFO allocations into consumption, expiry, and
variance for an explicit household, Item, half-open time range, and currency. Unknown-cost stock is
always reconciled separately.

## Automated qualification

Focused unit, projection, purchase, report, authorization/isolation, CSV, and browser tests cover
the representative `$65 / 50` acquisition and `$23.40 / 18` consumption reconciliation,
expiry/variance classification, multiple currencies without mixing, unsupported estimate states,
formula-safe export, invalid period/currency input, and cross-household direct Item/CSV denial.

Native ARM64 Chromium 1208 ran against the isolated restored database at
`/tmp/carekeeper-m65-c-restore-host-325c741a/verified/325c741a2378454c97f5200530272f56/snaketracker.sqlite3`.
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

The owner-review image is native ARM64 `snaketracker:m65-c-owner-review`, SHA-256
`e8e457e4c06b2ad896bacdd7d1660a6acc405fae9e507a795b2a9ec0a4e47a8f`, built for UID/GID
`1001:1001`. It is promoted without a schema change: migration head remains
`0018_inventory_stock_roles`. Web, worker, and Nginx are healthy; local readiness returns `ready`;
web and worker run as UID/GID `1001:1001`; and exactly one three-service Care Keeper Compose stack
remains active.

## Authoritative quality

The exact authoritative path is:

```text
uv sync --frozen
./scripts/quality/check.sh
```

The first complete suite passed all 602 tests but exposed 84.91% branch coverage against the
85.00% gate, so it correctly stopped before the later quality steps. Focused tests were added for
the unsupported dependency, invalid period, absent/stale price, and zero-replenishment branches.
The completed post-correction gate passed formatting and Ruff across 461 files, the 42-ADR accepted
architecture freeze, documentation links across 208 files, strict mypy across 132 source files,
all 604 tests in 795.10 seconds, coverage, dependency audit, Compose validation, and diff checks.
JUnit reports zero failures, errors, or skipped tests. Coverage is 94.49% lines, 85.03% branches,
and 92.60% combined. `coverage.json`, `coverage.xml`, and `junit.xml` were produced, and the strict
dependency audit reports no known vulnerabilities.

## Scope boundary

M6.5-D final milestone qualification and acceptance, M7 formal recovery/deployment qualification,
M8 release qualification, M9 public media, and unrelated UX work have not begun.
