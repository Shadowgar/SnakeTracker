# Care Keeper Architecture Package

Operations guide: [Platform Administration and Support Console](operations/platform-admin-console.md).

Status: Approved
Acceptance date: 2026-08-04

This package is the approved architecture baseline for the Care Keeper application (whose
repository and internal package retain the historical SnakeTracker name). The decision freeze in
[ADR-0028](adr/0028-architecture-governance-and-decision-freeze.md) is active as of 2026-08-04.
[ADR-0036](adr/0036-development-and-pi-deployment-qualification.md) separates laptop development
qualification from mandatory pre-deployment Raspberry Pi qualification.
[ADR-0037](adr/0037-phase-order-minimal-household-events.md) moves only the permanent
household-event bootstrap slice into Phase 2 while leaving the general event platform in Phase 3.
[ADR-0038](adr/0038-scheduling-and-husbandry-reference-profiles.md) fixes the boundary between
owner-configured effective-history scheduling in M5 and optional explainable analytics/reference
profiles in M6. [ADR-0039](adr/0039-multispecies-animal-capabilities.md) inserts the additive
multi-species Animal capability foundation before M6 without rewriting existing snake events.
[ADR-0040](adr/0040-trusted-local-demo-household-provisioning.md) permits one fail-closed,
event-sourced fictional household only in trusted local M6 review environments.
[ADR-0041](adr/0041-four-group-capability-expansion-and-neutral-molt-contracts.md) adds trusted
Lizard and Scorpion profiles and preserves historical Spider-only molt/premolt v1 contracts while
introducing capability-neutral v2 contracts.

[ADR-0042](adr/0042-inventory-purchases-fifo-and-quantity-policy.md) is the accepted M6.5 decision
covering structured Inventory, Inventory-authoritative Feeding, multi-line Purchases, cash-spend
authority, FIFO valuation, canonical quantities, and physical counts. A1 implements only the
structured Inventory and Feeding foundation; the financial/intelligence tranches remain pending.

[ADR-0043](adr/0043-universal-species-directory.md) records Accepted status for stable
Care Keeper taxon UUIDs, normalized optional provider mappings/cache, licensing, request privacy,
and manual/offline species behavior. A was integrated in PR #14; standalone milestone owner
acceptance remains unverified in repository evidence (see the [roadmap](roadmap/milestones.md)).
[ADR-0044](adr/0044-versioned-sourced-care-guides.md)
remains Proposed pending M6.6-B owner review. [ADR-0045](adr/0045-extensible-animal-capability-evolution.md),
[ADR-0046](adr/0046-local-taxonomy-snapshot-and-provider-overlay.md),
[ADR-0047](adr/0047-natural-history-reference-boundary.md), and
[ADR-0048](adr/0048-precise-animal-length-measurements.md) are Proposed for the owner-approved
pre-M6.6-C extension. M6.6 was inserted after M6.5 and before M7.

## Document map

- [Complete architecture specification](architecture/system-architecture.md)
- [Final diagrams](architecture/diagrams.md)
- [Domain catalog](architecture/domain-catalog.md)
- [Event catalog](architecture/event-catalog.md)
- [Projection catalog](architecture/projection-catalog.md)
- [Database schema recommendations](architecture/database-schema.md)
- [Folder structure](architecture/folder-structure.md)
- [Threat model](security/threat-model.md)
- [Security architecture](security/security-architecture.md)
- [Backup and restoration runbook](operations/backup-and-restoration.md)
- [Operations runbook](operations/runtime-operations.md)
- [Planned taxonomy snapshot refresh procedure](operations/taxonomy-snapshot-refresh.md)
- [Requirements traceability matrix](requirements/traceability-matrix.md)
- [Representative dataset](quality/representative-dataset.md)
- [UX information architecture](ux/information-architecture.md)
- [Roadmap and milestone checklist](roadmap/milestones.md)
- [M6.5 Inventory Intelligence architecture proposal](plans/2026-09-04-m6.5-inventory-intelligence-architecture.md)
- [Extensible Animal and Species Platform controlling plan](plans/2026-10-01-extensible-animal-and-species-platform.md)
- [Raw owner problem log and roadmap triage](problems/README.md)
- [Evidence policy](evidence/README.md)
- [ADR index](adr/README.md)

## Requirement classes

- **RB — Mandatory release blocker:** required for the milestone or release that first introduces the affected capability.
- **RD — Mandatory before remote or public deployment:** required before enabling Cloudflare Tunnel or any non-local user access.
- **QT — Qualified operational target:** measured against the versioned representative dataset and pinned qualification environment; not a universal guarantee.
- **DC — Deferred capability:** deliberately outside the current release scope and prohibited from silently expanding the initial implementation.
- **DDQ — Deferred deployment qualification:** not an intermediate feature-phase gate, but mandatory before the named deployment target is used.

When multiple classes apply, the stricter applicable gate controls.
