# SnakeTracker Architecture Package

Status: Approved
Acceptance date: 2026-08-04

This package is the approved implementation-independent architecture baseline for SnakeTracker. It contains no application implementation code. The decision freeze in [ADR-0028](adr/0028-architecture-governance-and-decision-freeze.md) is active as of 2026-08-04. [ADR-0036](adr/0036-development-and-pi-deployment-qualification.md), accepted on 2026-08-05, separates laptop development qualification from mandatory pre-deployment Raspberry Pi qualification.

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
