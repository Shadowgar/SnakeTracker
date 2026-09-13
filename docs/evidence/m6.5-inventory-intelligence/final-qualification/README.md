# Final M6.5 qualification

Status: **Technical qualification passed; M6.5 owner-accepted September 13, 2026**

The owner accepted M6.5-C on September 13, 2026. M6.5-D adds no product capability and does not
begin M7: it consolidates the accepted A1, A2, B, and C tranches and qualifies the complete M6.5
candidate against the final roadmap gate.

## Live-data safety and recovery

The active database, Attachment store, and backup store were explicitly resolved as
`/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`,
`/home/rocco/SnakeTracker/runtime/phase2/attachments`, and
`/home/rocco/SnakeTracker/runtime/phase2/backups`. No destructive command targeted those paths.

The worker completed a new non-overwriting encrypted backup, request
`69716e57-08a7-4ae9-9fea-5ce4fdb2dd18`, run
`0263b1a8-69c1-4c23-b7bf-75cd874f2c32`. The encrypted database is 13,451,297 bytes with SHA-256
`d9897a397097a3bac777f7e64bf3972e45b57fa5ee3fed23fbb262e54897cba6`; the 24,569-byte
encrypted manifest has checksum
`188dfbf936065e1743c4667888e58b0f8a873db6e37b03d738d0f618600e8cec`.

Restore targeted only `/tmp/carekeeper-m65-d-restore.65Ouqo`, while the active runtime was mounted
read-only. The first attempt wrote nothing and stopped on temporary-directory permissions; after
granting container UID 1001 access to that same isolated directory, restore returned `verified`
with 33 Attachment artifacts. The restored database is at migration
`0018_inventory_stock_roles`, contains 810 events, has SQLite integrity `ok`, zero foreign-key
violations, zero sessions, and zero password-reset credentials. Operational details are retained in
[`operations.json`](operations.json).

The live baseline contained 809 events with ordered position/identity/checksum hash
`2352c365c4f34c49b1a375d4ec240f91938490d80a18f3297a545ac466b9647b`. A real user recorded
one body weight at position 810 before the backup began. The final live database contains exactly
those 810 events, preserves the first-809 prefix hash, and matches the restored snapshot hash
`9c9104d103d4a2bba99c2394cff953fe9fa554f5c7c381d5dec94d808031e76c`.
Qualification appended zero live domain events.

## Compatibility, replay, corrections, and authorization

The authoritative 619-test suite passed. It covers zero-to-head and historical upgrade migration
lifecycle, registered V1/V2 event coexistence, integer-to-scaled Inventory compatibility, V1/V2
Feeding and decimal-weight replay, deterministic projection rebuild, idempotency, immutable
correction/void/reinstate compensation, Purchase/receipt/cost allocation reconciliation, physical
count replacement, reporting corrections, unknown-cost handling, CSV protection, direct-ID
household denial, and demo-household isolation.

All six production projection groups were rebuilt cold and warm from the isolated 810-event
snapshot. Every group reached high-water 810 without changing the event hash. The slowest rebuild
was 1.887 seconds and peak RSS was 45.98 MiB, within the existing 30-second and 512 MiB qualified
targets. Details are in [`performance.json`](performance.json).

## Browser and accessibility

Native ARM64 Chromium 1208 exercised Care Stock, Add inventory, Check stock, Expenses, collection
and Item Inventory & spending reports, and Inventory-authoritative Feeding at both 390×844 and
1440×900. All 14 pages returned HTTP 200, navigation p95 was 753.059 ms, all eight report charts
had sensible non-zero dimensions, and keeper-facing accounting implementation jargon was absent.

Fourteen axe WCAG A/AA scans reported zero violations. Every page had no horizontal overflow,
application console diagnostic, page error, failed request, or unexpected HTTP error. The browser
used only the isolated restored database and made no live write. Machine-readable results are in
[`browser.json`](browser.json). The complete owner-reviewed screenshots remain indexed by the
[A1](../a1-structured-inventory-feeding/README.md),
[A2](../a2-purchases-fifo/README.md), [B](../b-inventory-intelligence/README.md), and
[C](../c-expense-reports/README.md) tranche evidence.

## Authoritative quality and runtime

The exact final gate ran:

```text
uv sync --frozen
./scripts/quality/check.sh
```

Formatting across 463 files, Ruff, the 42-ADR architecture freeze, documentation links across 208
files, strict mypy across 133 source files, all 619 tests in 802.40 seconds, coverage artifact
generation, dependency audit, Compose validation, and diff checks passed. Coverage is 94.52% lines
and 85.08% branches; the dependency audit found no known vulnerabilities.
After adding this evidence record, the focused documentation-link check passed across 209 files and
`git diff --check` remained clean; no product code changed after the complete gate.

The promoted image remains native ARM64 `snaketracker:m65-c-owner-correction`, SHA-256
`cb51cc6898606530d24ec6bf3a6128988a9e5994295616040a3528208783cb40`. Web, worker, and Nginx
are healthy; local and public readiness return `ready`; web and worker run as UID/GID `1001:1001`;
all nine active projection definitions are current at position 810; and exactly one Care Keeper
Compose stack is active.

## Owner acceptance and boundary

The owner explicitly accepted M6.5 on September 13, 2026; the decision is retained in the
[owner-acceptance record](../approvals/2026-09-13-owner-acceptance.md). M7 deployment/recovery
qualification, M8 release qualification, M9 public media, and unrelated feature work have not
begun.
