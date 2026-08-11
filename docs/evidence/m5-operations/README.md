# M5 Operational Workflow Evidence

Status: **M5 implementation-qualified; owner acceptance pending**

- Qualification date: August 11, 2026
- Source branch: `phase5/operational-workflows`
- Qualified implementation revision: `567887cc95702fa0407cebdf12d33e22b11dd8fb`
- Environment: approved laptop/Docker development environment

This package proves the Phase 5 inventory, expense, reminder, notification-pipeline, and durable-job
release blockers on the supported local development topology. The corrected keeper workflow now
configures ordinary care intervals from each animal profile and presents calculated care in an
overdue/due-today/upcoming agenda. It does not record owner acceptance, authorize M6, approve
remote/public deployment, or claim Raspberry Pi deployment qualification.

## Evidence inventory

- [Inventory correctness](tests/inventory.md)
- [Expense policy](tests/expenses.md)
- [Reminder effective-history behavior](tests/reminders.md)
- [Pipeline deduplication](tests/notifications.md)
- [Durable jobs](tests/jobs.md)
- [External-effect crash recovery](tests/external-effects.md)
- [Authorization](security/authorization.md)
- [Crash recovery runbook evidence](operations/crash-recovery.md)
- [Migration and compatibility](operations/compatibility.md)
- [Docker and ARM64](containers/README.md)
- [Browser workflows](browser/README.md)
- [Accessibility](accessibility/README.md)
- [Review disposition](reviews/README.md)
- [Release gate](approvals/release/README.md)

`evidence-manifest.json` records the qualification provenance. `checksums.sha256` covers every
retained evidence artifact except the checksum file itself.

## Qualification disposition

All five applicable M5 release blockers have passing implementation evidence. The authoritative
roadmap records them as technically complete while explicitly retaining the owner-acceptance gate.
M6 through M8 remain unchecked. Native Raspberry Pi execution, SSD/ext4 placement, thermal tests,
and deployment performance remain deferred to Phase 7/pre-deployment.
