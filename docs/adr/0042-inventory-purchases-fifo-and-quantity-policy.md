# ADR-0042: Model Inventory Purchases and Consumption Value with FIFO

Status: Proposed

## Context

M6.5 requirements `R-070` through `R-076` turn Inventory from a balance list into an
explainable stock and cost system. The accepted Inventory Item aggregate already owns receipts,
reservations, consumption, adjustments, expiry, reorder policy, and archive state. The accepted
Expense aggregate owns standalone cash-spend facts. Neither model records a receipt containing
multiple inventory lines, immutable acquisition costs, physical verification, fractional
quantities, or deterministic consumption value.

The architecture must preserve existing events and live records, prevent systematic double
counting between Purchases and Expenses, remain understandable to a household keeper, and rebuild
deterministically after corrections. The active database and attachment store are live data and
cannot be used for destructive migration, replay, fresh-install, or restoration experiments.

## Proposed decision

### Purchase and cash-spend authority

Introduce a `Purchase` aggregate on `purchase:{purchase_uuid}`. One Purchase represents one receipt
and may contain up to 25 inventory line items. Every line has a stable line ID, exactly one
same-household Inventory Item, a quantity in that item's canonical unit, and a line subtotal. A
Purchase has one currency, vendor, purchase time, reference/note, optional tax, fee, and discount
totals, and a positive total paid.

A Purchase is a specialized cash-spend source; it does **not** create an `expense.recorded` event.
Existing Expense streams remain authoritative for non-purchase spending. A unified read model
contains one row per `(source_kind, source_id)`, where source kind is `purchase` or `expense`, so
the application cannot count a Purchase a second time merely to expose it in Expenses or reports.
The generic expense workflow cannot create an inventory link or use the reserved Inventory
Purchase source kind. The UI directs supply receipts to Add purchase and warns about a same-day,
same-vendor, same-currency, same-amount manual expense, while allowing a keeper to confirm a
legitimate duplicate transaction.

Purchase posting atomically appends the Purchase fact and one version-2 stock-receipt fact per line
to the affected Inventory Item streams under ADR-0011. Multiple lines for the same item share that
item stream. The 25-line bound limits transaction and payload size; M6.5 qualification must prove
the bound on SQLite and the supported Raspberry Pi environment.

### Acquisition cost and FIFO

Each purchase line creates an immutable receipt/cost lot. A lot retains purchase and line IDs,
received time, quantity, currency, and total acquisition cost. Purchase-wide tax and fees, less
discount, are capitalized across positive line subtotals with integer largest-remainder allocation;
ties are resolved by stable purchase-line ID. Allocated line costs exactly reconcile to total paid.
No floating-point money is stored. Unit cost is a derived rational display value, not a mutable
Inventory Item price.

Effective inventory consumption is valued with FIFO. For each item, effective receipt and
uncosted-increase layers are ordered by `(occurred_at, recorded_at, global_position, event_id)`.
Effective consumption depletes the oldest remaining quantity. Integer minor-unit cost for a partial
lot allocation is the change in cumulative proportional cost, so exhausting a lot allocates its
last remainder cent and the lot always reconciles exactly.

Expiry, loss, negative manual adjustment, and negative physical-count variance also deplete FIFO
layers, but their value is classified as expiry or inventory variance rather than consumption cost.
A positive adjustment or count variance without a Purchase creates an uncosted layer. Reports show
known value and unknown-cost quantity separately; unknown is never treated as zero.

### Quantities, units, and negative stock

Each item has one canonical unit. Stored event quantities use signed or unsigned integer
thousandths of that unit. Whole-item units (`each`, `count`, and `package`) require multiples of
1,000; mass and volume units may use up to three decimal places. Existing integer quantities map
exactly to `quantity * 1,000` without rewriting their events.

M6.5 performs no automatic unit conversion. Purchase, use, adjustment, and count inputs must use
the item's canonical unit. A keeper tracking grams enters a kilogram purchase as 1,000 grams.
Changing an item's canonical unit is allowed only before its first stock movement; later conversion
requires a future explicit conversion decision rather than silently mixing units.

Stock remains nonnegative, and reserved quantity cannot exceed on-hand quantity. Insufficient use,
receipt correction, void, or count compensation is rejected with an instruction to verify and
correct stock. M6.5 does not introduce temporary negative balances.

### Physical verification and policy

A single enriched `inventory.stock_counted` event records expected quantity, actual quantity,
derived variance, count context, and count-session correlation. It directly applies the variance;
the command does not also append `inventory.stock_adjusted`, which would record the same fact twice.
The envelope supplies actor and occurred/recorded time. A zero-variance count remains valuable
because it proves verification.

Counts are saved one item at a time with a shared workflow ID. Full, category, and single-item
counts are application selections, not new stock aggregates. This keeps each stock transition
short and concurrency-safe. A mistaken count is corrected by atomically voiding its effect and
recording a replacement count; reinstatement is explicit where no replacement conflicts.

Reorder minimum, optional target, optional maximum, optional owner-entered lead time, and optional
recount interval remain Inventory Item policy. No husbandry-derived defaults are introduced.

## Alternatives considered

### One purchase per inventory item

This keeps each command to two streams, but makes an ordinary multi-item receipt become several
fake Purchases, repeats vendor/tax/reference data, and cannot reconcile naturally to one payment.
It is rejected in favor of a bounded multi-line receipt.

### Purchase creates an Expense event

Atomically appending both could reuse the current Expense projection, but it stores the same cash
fact in two aggregates and creates coupled correction/void behavior. It also makes accidental
double projection more likely. A Purchase as one specialized cash-spend source is clearer.

### Expense optionally links to a Purchase

This permits unlinked, multiply linked, or separately corrected records unless extensive coupling
rules are added. It is rejected because the Purchase itself already contains the complete cash
fact.

### Weighted-average cost

Weighted average is compact and gives one current pool cost. It is less explainable when prices
change, discards the useful relationship between receipt lots and remaining stock, and either
revalues historical consumption after corrections or requires cost snapshots with additional
rules. Physical-count increases with unknown basis also make an average misleading. It is not
selected.

### FIFO

FIFO requires lot and allocation projections and deterministic remainder handling, but it preserves
purchase history, explains which acquisitions remain, accommodates partial quantities, and makes
correction/rebuild behavior auditable. It aligns directly with `R-074`; it is the proposed policy.

### Physical-count event plus generated adjustment

Two events would duplicate one observation and require permanent coupling. A single enriched count
event records the observation and its balance effect and is selected.

### Automatic unit conversion or floating-point quantities

Conversion requires item-specific package ratios and dimensional compatibility rules; floating
point cannot provide exact replay. Both are rejected for M6.5. Canonical-unit integer thousandths
are selected.

### Permit negative stock

Negative balances hide missed receipts and make FIFO value ambiguous. The existing fail-closed
nonnegative invariant is retained.

## Tradeoffs

- FIFO read models are more complex than weighted average and must be rebuilt for backdated or
  corrected facts.
- One real receipt can touch many Inventory Item streams, so line count, transaction duration,
  idempotency, and conflict behavior require explicit qualification.
- Capitalizing shared charges makes stock value reconcile to payment, but users must understand
  that reported unit cost can include allocated tax/fees and discount.
- Fixed three-decimal quantity precision is deterministic and sufficient for the named units but is
  not arbitrary precision.
- Refusing negative stock can require a recount or correction before a keeper records another use.
- Multi-currency values remain separate because no exchange-rate authority exists.

## Correction, void, and reinstatement

Purchase corrections append a full replacement Purchase fact. Added lines append new receipt
facts; changed quantities append typed receipt corrections; removed lines append permitted generic
void controls. Monetary-only corrections rebuild the affected cost layers without changing stock.
A Purchase void and its receipt controls append atomically. A Purchase may be reinstated only when
all associated receipt effects can also be reinstated without violating stock/reservation
invariants. A correction or void that would make current stock invalid is rejected rather than
partially applied.

Consumption keeps the accepted reversal/compensation pattern. Feeding correction, void, and
reinstatement continue to reverse and replace the linked inventory use atomically. Count
corrections use appended controls and a replacement count. Effective cost allocations consume only
effective, non-reversed facts and rebuild deterministically from their correlation/causation links.

## Migration and backward compatibility

Implementation requires an expand-only migration after this ADR is accepted; none is created or
run by this proposal. It will add parallel scaled-quantity state and new purchase/cost/read-model
tables, populate scaled current quantities as exact multiples of 1,000, retain legacy columns for
the compatibility window, and build new projections without destructive event rewriting.

Historical version-1 receipts become uncosted FIFO layers. Historical version-1 consumption and
feeding links remain effective and normalize to scaled quantities. Existing Expenses remain
standalone cash-spend facts and are never inferred to be Purchases. Existing reorder thresholds map
to reorder minimum; target, maximum, lead time, recount interval, cost, and last verification start
as unavailable. Items with historical unit changes require canonical-unit review and a physical
count before duration/value claims are trusted.

Migration-from-zero, upgrade, downgrade/re-upgrade, replay, and restore rehearsals use isolated
temporary databases or copied snapshots outside active runtime paths. The live database is never a
qualification target and is never restored over.

## Event, data, and plugin compatibility

Version-1 Inventory and Expense contracts remain registered and replay unchanged. Additive version-2
Inventory handlers normalize old integer quantities in memory; stored history is not rewritten.
Unknown Purchase or Inventory contracts continue to trigger restricted recovery mode. Plugins may
consume only registered public contracts and cannot supply costing policy, currency conversion, or
unit conversion. Removal remains prohibited while a plugin handler is required by stored history.

## Projection and operational consequences

Balance, effective receipt state, Purchase current state, and invariant inputs remain synchronous.
FIFO allocations, usage intelligence, unified cash-spend facts, and reports are versioned,
rebuildable asynchronous projections with visible freshness. Backdated/corrected facts enqueue a
bounded per-item recalculation and eventually a generation rebuild; templates never calculate cost
from raw event JSON.

No deploy, migration, backup, restore, or runtime change is authorized by this Proposed ADR. Formal
M7 recovery/deployment and M8 release qualification remain separate.

## Security and privacy consequences

Purchase and valuation data are private household financial data. Every command, subject reference,
projection row, query, export, and direct-ID route remains household-scoped and authorized. Writes
retain CSRF, idempotency, expected-version, typed-subject, audit, bounded-input, and output-encoding
controls. Cost data is never exposed through M9 public profile/media routes or unsafe logs.

## Testing and evidence required before acceptance of M6.5

- Historical v1 replay, v2 contract fixtures, unknown-contract failure, and deterministic rebuild.
- Atomic multi-line Purchase success/failure/idempotency/conflict tests through the 25-line bound.
- Cash-spend uniqueness and Purchase/Expense correction/void/reinstate reconciliation.
- FIFO examples across changing prices, shared-cost allocation, partial quantities, remainder cents,
  uncosted layers, backdated facts, and multiple currencies.
- Physical-count zero/positive/negative variance, correction, conflict, verification, and due-state
  tests.
- Feeding-linked accepted/refused/corrected/voided/reinstated and generic-use compensation tests.
- Household direct-ID denial, role, CSRF, report/export, and no-public-exposure tests.
- Isolated migration lifecycle, projection generation swap/rollback, backup/restore, performance,
  responsive browser, keyboard/screen-reader, and WCAG 2.2 AA evidence.

Evidence belongs under `docs/evidence/m6.5-inventory-intelligence`; it must identify isolated paths
for every destructive rehearsal and prove the active database and attachment store were not used.

## Schedule, roadmap, and milestone consequences

This proposal establishes the M6.5-A through M6.5-D sequence documented in the M6.5 architecture
plan. `R-070` through `R-076` remain not implemented. Work on event contracts, schema, migration,
or product UI cannot begin until the owner accepts or amends this ADR. M7, M8, and M9 ordering and
scope do not change.

## Approval required

The owner must approve the combined domain decision: bounded multi-line Purchases as the sole
purchase cash-spend fact, capitalized shared-cost allocation, FIFO valuation, fixed-precision
canonical quantities without conversion, enriched count events, and retained nonnegative stock.
Until that approval is recorded, this ADR remains Proposed and the accepted architecture remains
authoritative.
