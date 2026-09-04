# Domain and Aggregate Catalog

## Boundary rules

One aggregate instance owns one ordered event stream. It enforces invariants decidable from that stream. Cross-stream coordination belongs in application services and uses atomic multi-stream append only when immediate consistency is required. Read-side features never become write aggregates merely because they display combined data.

## Bounded contexts

### Households

- **Aggregate:** Household
- **Stream:** `household:{household_uuid}`
- **Owns:** lifecycle, name/settings, invitations, membership roles, owner continuity
- **Invariant:** a usable household has at least one active owner
- **Synchronous projections:** authorization memberships and household summary

Authentication credentials and sessions are platform records. Membership transitions are business events.

### Animals

- **Aggregate:** Animal
- **Stream:** `animal:{animal_uuid}`
- **Feature slices:** profile, husbandry, health
- **Owns:** animal identity, registered care-capability profile, lifecycle, profile, current enclosure assignment, husbandry history, health history
- **Invariant examples:** archived animals cannot receive ordinary husbandry entries without an explicit override; measurement units must be valid; correction targets must belong to the same stream and household

Husbandry and health are not peer bounded contexts. They issue commands through animal-owned application ports and cannot import one another. Common types live in `animals.domain.common`. Reports, reminders, and search consume public event contracts.

Animal type is modeled by a trusted, versioned care-capability profile within this aggregate, not by
creating a new aggregate per species. The registered profiles are `snake.v1`, `spider.v1`,
`lizard.v1`, and `scorpion.v1`. Profiles declare applicable typed commands, measurements,
husbandry contracts, reminder kinds, analytics, and presentation actions. Application services and
domain handlers both reject inapplicable actions. They do not embed universal husbandry intervals
or permit arbitrary user-defined code.

Legacy `animal.registered` version 1 streams deterministically resolve to `snake.v1`; they are not
rewritten. Version 2 registration records the profile identity for new animals. Common identity,
photos, feeding, enclosure assignment, inventory and expense associations, reminders, attachments,
timeline, backup, and authorization remain shared. Snake shed remains snake-specific because its
contract includes snake semantics. Lizard enables shared length, bath, and misting capabilities but
does not reuse snake shed. Historical molt/premolt schema v1 remains Spider-only; neutral schema v2
is shared by molt-capable Spider and Scorpion profiles. Scorpion does not expose length, shed, or
bath. Enclosure care remains in the neutral Enclosure aggregate.

### Enclosures

- **Aggregate:** Enclosure
- **Stream:** `enclosure:{enclosure_uuid}`
- **Owns:** enclosure identity, status, capacity policy, cleaning and water-maintenance history
- **Does not own:** current animal occupancy

The Animal aggregate owns current enclosure assignment. Occupancy is a projection of animal streams. Enclosure events may use related-animal subject references.
Watering and misting are enclosure-care facts and may reference an occupant through a typed subject;
they do not change enclosure ownership or create type-specific enclosure aggregates.

### Inventory

- **Aggregate:** Inventory item
- **Stream:** `inventory-item:{item_uuid}`
- **Owns:** item definition, units, active/archived lifecycle, acquisitions, reservations, consumption, adjustments, expiry, reorder policy
- **Invariant:** an operation cannot produce an invalid balance unless an explicitly authorized adjustment policy permits it

A feeding that consumes stock uses one atomic multi-stream operation across the animal and inventory-item streams. Archived items remain replayable and visible in historical reads but cannot receive stock changes or new feeding consumption. Restoration is an explicit event. Permanent deletion is intentionally unavailable because registration itself creates immutable item history.

#### Proposed M6.5 extension (not accepted or implemented)

ADR-0042 proposes retaining the Inventory Item boundary while adding canonical scaled quantities,
owner categories/reorder/verification policies, purchase-linked receipt lots, enriched physical
counts, and generic use. Physical counts and all balance-affecting facts remain on the item stream.
FIFO lots, allocations, usage, duration, and valuation remain rebuildable read-side concepts.
Existing v1 integer events remain valid and normalize exactly; historical cost stays unknown where
no Purchase exists. See the [M6.5 architecture proposal](../plans/2026-09-04-m6.5-inventory-intelligence-architecture.md).

The proposal also permits authorized correction/void/reinstate effects against archived item
history while continuing to reject new ordinary movements. Stock remains nonnegative and reserved
quantity cannot exceed on hand.

### Expenses

- **Aggregate:** Expense
- **Stream:** `expense:{expense_uuid}`
- **Owns:** amount, currency, category, payee/reference, subject associations, correction and void state

#### Proposed M6.5 Purchase boundary (not accepted or implemented)

- **Aggregate:** Purchase
- **Stream:** `purchase:{purchase_uuid}`
- **Owns:** one bounded multi-line inventory receipt, vendor, purchase time, currency, monetary
  totals, stable line identities, correction, void, and reinstate state
- **Does not own:** Inventory Item balance, FIFO projection rows, or standalone Expenses

ADR-0042 proposes that a Purchase is the single specialized cash-spend source for its receipt; it
does not append `expense.recorded`. A unified read model presents Purchases and existing standalone
Expenses exactly once. Posting or historically controlling a Purchase coordinates the Purchase and
affected Inventory Item streams through atomic multi-stream append.

### Reminders

- **Aggregate:** Reminder rule
- **Stream:** `reminder-rule:{rule_uuid}`
- **Owns:** schedule policy, subject, activation, channel preferences
- **Does not own:** derived reminder facts, notification intent, jobs, or attempts

Current reminder state is a deterministic calculation from the owner rule and effective qualifying
care history. Event-relative schedules recur from the qualifying event. Fixed schedules advance to
the first cadence occurrence after qualifying care at or after the current occurrence. Corrections,
voids, and reinstatements therefore change reminder state through effective-history replay rather
than a mutable completed-task flag.

### Documents

- **Aggregate:** Document
- **Stream:** `document:{document_uuid}`
- **Owns:** logical document identity, immutable attachment-version association, subject classification, archival
- **Infrastructure:** staged and finalized blob lifecycle

### Notification preferences

- **Aggregate:** Notification preference
- **Stream:** `notification-preference:{preference_uuid}`
- **Owns:** user-facing channel and quiet-time preferences
- **Does not own:** provider credentials or delivery state

## Read-side modules

Dashboard, reports, search, timelines, statistics, reminder facts, and enclosure occupancy are projection/query modules. They have no write aggregates. Administration coordinates platform capabilities and audited operations without bypassing domain services.

## Future bounded contexts

Breeding and incubation should begin with `breeding-project:{uuid}` and related incubation streams after a dedicated ADR. Marketplace, organizations, cloud sync, telemetry, AI, cameras, QR/NFC, and home automation are deferred capabilities. High-frequency telemetry must not enter animal or enclosure streams; only meaningful threshold transitions may become domain events.

## Typed subject references

Each subject reference contains registered `subject_type`, subject UUID, relationship role (`primary`, `related`, `location`, or contract-defined value), and optional display order. Append validation proves registration, existence, same-household ownership, and actor permission. Event contracts declare required subject roles and whether exactly one primary subject is mandatory.

## Package dependency policy

```text
feature presentation -> feature application -> feature domain/common
infrastructure -> application/domain-owned ports
bootstrap -> all concrete registrations
```

Forbidden dependencies include domain-to-framework, domain-to-infrastructure, feature-to-feature sideways imports, projection-to-aggregate internals, and plugin-to-private package paths.
