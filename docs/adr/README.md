# Architecture Decision Records

ADR-0001 through ADR-0035 were **Accepted on 2026-08-04**. ADR-0036 and ADR-0037 were
**Accepted on 2026-08-05**, ADR-0038 was **Accepted on 2026-08-10**, ADR-0039 was **Accepted on
2026-08-11**, ADR-0040 was **Accepted on 2026-08-16**, and ADR-0041 was **Accepted on
2026-08-24**, through ADR-0028 governance. ADR-0028's decision freeze is active. Later
architectural changes must create or supersede an ADR and must never silently rewrite accepted
decisions.

[ADR-0042](0042-inventory-purchases-fifo-and-quantity-policy.md) was **Accepted on 2026-09-10**.
M6.5-A1 implements its structured Inventory and Inventory-authoritative Feeding foundation;
Purchase, FIFO, costing, counting, and intelligence remain later M6.5 tranches.

[ADR-0043](0043-universal-species-directory.md) records **Accepted** status dated 2026-09-26. A was integrated in
PR #14; standalone milestone owner acceptance remains unverified in repository evidence (see the
[roadmap](../roadmap/milestones.md)). It records Care Keeper-owned taxon identity, provider/cache
boundaries, licensing, privacy, and
offline behavior. [ADR-0044](0044-versioned-sourced-care-guides.md) was **Accepted on 2026-10-05**
for the immutable guide/source/claim boundary and final dedicated Animal reference presentation;
see [B owner acceptance](../evidence/m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance).

[ADR-0045](0045-extensible-animal-capability-evolution.md),
[ADR-0046](0046-local-taxonomy-snapshot-and-provider-overlay.md),
[ADR-0047](0047-natural-history-reference-boundary.md) remain **Proposed** for the pre-M6.6-C
extension. They propose profile lifecycle/startup compatibility, permanent identity with replaceable
reference generations and Natural History/legacy-guide coexistence.
[ADR-0048](0048-precise-animal-length-measurements.md) was **Accepted on 2026-10-05** for exact
length v2 and mixed-history consumers. No historical meaning is rewritten; Pre-X1 reconciliation
and X1–X5 implementation remain unstarted.

| ADR | Decision |
|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith |
| [0002](0002-event-sourced-business-core.md) | Event-sourced business core |
| [0003](0003-event-sourcing-versus-append-only-history.md) | Event sourcing versus append-only history |
| [0004](0004-aggregate-and-stream-boundaries.md) | Aggregate and stream boundaries |
| [0005](0005-event-contracts-and-evolution.md) | Event contracts and evolution |
| [0006](0006-corrections-and-compensation.md) | Corrections and compensation |
| [0007](0007-projection-consistency.md) | Projection consistency classes |
| [0008](0008-projection-rebuilds.md) | Projection generations and rebuilds |
| [0009](0009-sqlite-and-postgresql-boundary.md) | SQLite and PostgreSQL boundary |
| [0010](0010-sqlite-operational-profile.md) | SQLite operational profile |
| [0011](0011-atomic-multi-stream-append.md) | Atomic multi-stream append |
| [0012](0012-command-idempotency.md) | Command idempotency |
| [0013](0013-durable-jobs.md) | Durable jobs and at-least-once effects |
| [0014](0014-reminder-notification-pipeline.md) | Reminder and notification pipeline |
| [0015](0015-household-tenancy-and-bootstrap.md) | Household tenancy and bootstrap |
| [0016](0016-authentication-and-sessions.md) | Authentication and sessions |
| [0017](0017-immutable-attachments.md) | Immutable attachments |
| [0018](0018-backup-and-restoration.md) | Backup and restoration |
| [0019](0019-fts5-search.md) | FTS5 search |
| [0020](0020-server-rendered-strict-csp-ui.md) | Server-rendered strict-CSP UI |
| [0021](0021-pwa-offline-boundary.md) | PWA offline boundary |
| [0022](0022-trusted-plugin-lifecycle.md) | Trusted plugin lifecycle |
| [0023](0023-observability-and-health.md) | Observability and health |
| [0024](0024-pi-qualification-budgets.md) | Pi qualification budgets |
| [0025](0025-api-versioning-and-concurrency.md) | API versioning and concurrency |
| [0026](0026-migration-and-rollback.md) | Migration and rollback |
| [0027](0027-telemetry-boundary.md) | High-frequency telemetry boundary |
| [0028](0028-architecture-governance-and-decision-freeze.md) | Architecture governance and freeze |
| [0029](0029-trusted-proxy-chain.md) | Trusted proxy chain |
| [0030](0030-time-semantics.md) | Time semantics |
| [0031](0031-typed-subject-references.md) | Typed subject references |
| [0032](0032-security-audit.md) | Security audit facility |
| [0033](0033-release-compatibility-matrix.md) | Release compatibility matrix |
| [0034](0034-accessibility-and-ux.md) | Accessibility and UX |
| [0035](0035-release-gates-and-internal-baseline.md) | Release gates and internal baseline |
| [0036](0036-development-and-pi-deployment-qualification.md) | Development and Raspberry Pi deployment qualification |
| [0037](0037-phase-order-minimal-household-events.md) | Phase-order amendment for minimal Phase 2 household events |
| [0038](0038-scheduling-and-husbandry-reference-profiles.md) | Effective-history scheduling and versioned husbandry reference profiles |
| [0039](0039-multispecies-animal-capabilities.md) | Multi-species Animal capability profiles and compatibility |
| [0040](0040-trusted-local-demo-household-provisioning.md) | Trusted local demo-household provisioning |
| [0041](0041-four-group-capability-expansion-and-neutral-molt-contracts.md) | Four-group capability expansion and neutral molt contracts |
| [0042](0042-inventory-purchases-fifo-and-quantity-policy.md) | Structured Inventory, Inventory-authoritative Feeding, multi-line Purchases, FIFO valuation, canonical quantities, and physical counts |
| [0043](0043-universal-species-directory.md) | Care Keeper-owned taxon identity, normalized provider mappings/cache, licensing, privacy, and offline species discovery |
| [0044](0044-versioned-sourced-care-guides.md) | Versioned sourced Care Guides as global reference data, with atomic reviewed import and explicit disagreement |
| [0045](0045-extensible-animal-capability-evolution.md) | Profile read/registration lifecycle, supported identities, startup checks and downgrade barrier |
| [0046](0046-local-taxonomy-snapshot-and-provider-overlay.md) | Permanent taxon catalog, replaceable generations and reconciled live overlay/promotion |
| [0047](0047-natural-history-reference-boundary.md) | Natural History authority, immutable guide coexistence and presentation precedence |
| [0048](0048-precise-animal-length-measurements.md) | Exact length v2 scale/units/consistency and complete mixed-history consumer semantics |
