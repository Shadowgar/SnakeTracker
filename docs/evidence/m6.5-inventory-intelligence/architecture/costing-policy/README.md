# M6.5 Architecture and Costing-Policy Review

Status: Proposal complete; owner decision pending

## Scope and baseline

This architecture-only review was performed on branch `phase6.5/inventory-intelligence` from the
owner-accepted M6 merge commit
`8b0c062a39453bd2a4e65cb6ce288eea6298137f`. It covers existing Inventory/Expense contracts,
application services, synchronous projections, feeding compensation, reports, architecture
catalogs, roadmap requirements `R-070` through `R-076`, and accepted ADRs governing aggregates,
contracts, correction, projections, atomic append, migration, time, subjects, and mobile UX.

The complete result is the
[M6.5 architecture proposal](../../../../plans/2026-09-04-m6.5-inventory-intelligence-architecture.md).
The new decision is [ADR-0042](../../../../adr/0042-inventory-purchases-fifo-and-quantity-policy.md),
which remains **Proposed**.

## Proposed result

- One bounded multi-line Purchase represents one real receipt and is the sole cash-spend source for
  that receipt; it does not duplicate an Expense event.
- Purchase lines create immutable receipt/cost lots linked to Inventory Item receipt events.
- FIFO is recommended over weighted average for lot traceability, normal-user explanation, and
  deterministic correction/replay.
- Cash spending, value consumed, expiry/variance value, and current known stock value are distinct;
  unknown-cost quantity stays explicit.
- One enriched physical-count event records expected/actual/variance and applies its balance effect.
- Canonical item units use integer thousandths; M6.5 performs no automatic conversions and retains
  nonnegative stock.
- Existing v1 Inventory/Expense/feeding events remain registered and are not rewritten.

## Safety boundary

No product code, event registration, schema migration, deployment, database command, attachment
operation, backup/restore, replay, fixture, browser journey, or destructive qualification was run.
The active live database and attachment store were untouched. Future destructive checks must name
and validate isolated targets outside active runtime paths.

## Acceptance boundary

This artifact satisfies preparation for `AR-INVINT-01`; it does not satisfy the acceptance review
until the owner approves or amends ADR-0042. `R-070` through `R-076` remain not implemented.

## Documentation qualification

The bounded architecture checks passed on September 4, 2026:

- local documentation links: 202 Markdown files;
- architecture boundary verification: pass;
- architecture freeze: 41 accepted ADRs unchanged and one explicit Proposed ADR;
- requirement uniqueness: 82 table IDs, all unique;
- Ruff format/lint for the adjusted freeze checker: pass; and
- Git whitespace/diff validation: pass.

No application/browser, migration, backup/restore, deployment, or runtime qualification was run
because this tranche contains no product implementation.
