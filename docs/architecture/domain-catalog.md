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
- **Owns:** animal identity, lifecycle, profile, current enclosure assignment, husbandry history, health history
- **Invariant examples:** archived animals cannot receive ordinary husbandry entries without an explicit override; measurement units must be valid; correction targets must belong to the same stream and household

Husbandry and health are not peer bounded contexts. They issue commands through animal-owned application ports and cannot import one another. Common types live in `animals.domain.common`. Reports, reminders, and search consume public event contracts.

### Enclosures

- **Aggregate:** Enclosure
- **Stream:** `enclosure:{enclosure_uuid}`
- **Owns:** enclosure identity, status, capacity policy, cleaning and water-maintenance history
- **Does not own:** current animal occupancy

The Animal aggregate owns current enclosure assignment. Occupancy is a projection of animal streams. Enclosure events may use related-animal subject references.

### Inventory

- **Aggregate:** Inventory item
- **Stream:** `inventory-item:{item_uuid}`
- **Owns:** item definition, units, acquisitions, reservations, consumption, adjustments, expiry, reorder policy
- **Invariant:** an operation cannot produce an invalid balance unless an explicitly authorized adjustment policy permits it

A feeding that consumes stock uses one atomic multi-stream operation across the animal and inventory-item streams.

### Expenses

- **Aggregate:** Expense
- **Stream:** `expense:{expense_uuid}`
- **Owns:** amount, currency, category, payee/reference, subject associations, correction and void state

### Reminders

- **Aggregate:** Reminder rule
- **Stream:** `reminder-rule:{rule_uuid}`
- **Owns:** schedule policy, subject, activation, channel preferences
- **Does not own:** derived reminder facts, notification intent, jobs, or attempts

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
