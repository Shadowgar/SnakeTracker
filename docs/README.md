# SnakeTracker Architecture Package

Status: Approved
Acceptance date: 2026-08-04

This package is the approved architecture baseline for SnakeTracker. The decision freeze in [ADR-0028](adr/0028-architecture-governance-and-decision-freeze.md) is active as of 2026-08-04. [ADR-0036](adr/0036-development-and-pi-deployment-qualification.md) separates laptop development qualification from mandatory pre-deployment Raspberry Pi qualification. [ADR-0037](adr/0037-phase-order-minimal-household-events.md) moves only the permanent household-event bootstrap slice into Phase 2 while leaving the general event platform in Phase 3. [ADR-0038](adr/0038-scheduling-and-husbandry-reference-profiles.md) fixes the boundary between owner-configured effective-history scheduling in M5 and optional explainable analytics/reference profiles in M6.

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
- [Requirements traceability matrix](requirements/traceability-matrix.md)
- [Representative dataset](quality/representative-dataset.md)
- [UX information architecture](ux/information-architecture.md)
- [Roadmap and milestone checklist](roadmap/milestones.md)
- [Evidence policy](evidence/README.md)
- [ADR index](adr/README.md)

## Requirement classes

- **RB — Mandatory release blocker:** required for the milestone or release that first introduces the affected capability.
- **RD — Mandatory before remote or public deployment:** required before enabling Cloudflare Tunnel or any non-local user access.
- **QT — Qualified operational target:** measured against the versioned representative dataset and pinned qualification environment; not a universal guarantee.
- **DC — Deferred capability:** deliberately outside the current release scope and prohibited from silently expanding the initial implementation.
- **DDQ — Deferred deployment qualification:** not an intermediate feature-phase gate, but mandatory before the named deployment target is used.

When multiple classes apply, the stricter applicable gate controls.
