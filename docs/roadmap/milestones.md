# Roadmap and Final Milestone Acceptance Checklist

## Classification legend

- **RB:** Mandatory release blocker for the milestone/release introducing the capability.
- **RD:** Mandatory before remote or public deployment.
- **QT:** Qualified operational target for the pinned environment and representative dataset.
- **DC:** Deferred capability.
- **DDQ:** Deferred deployment qualification; mandatory before the named target deployment.

## Phase 0 / M0 — Architecture approved

Status: M0 architecture approved
Accepted: August 4, 2026

- [x] RB Complete architecture, diagrams, catalogs, threat model, runbooks, traceability, dataset, UX IA, ADRs, and roadmap exist. Evidence: [architecture package index](../README.md) and [M0 evidence](../evidence/m0-architecture/README.md).
- [x] RB Document links and required sections validate. Evidence: [M0 verification record](../evidence/m0-architecture/README.md#criterion-verification).
- [x] RB Owner approves assumptions and unresolved decisions. Evidence: [owner approval](../evidence/m0-architecture/2026-08-04-owner-approval.md).
- [x] RB ADRs transition from Proposed to Accepted. Evidence: [ADR index](../adr/README.md) and [ADR-0036 amendment approval](../evidence/m0-architecture/2026-08-05-qualification-timing-amendment.md).
- [x] RB Architecture decision freeze is recorded under `/docs/evidence/m0-architecture`. Evidence: [owner approval and freeze record](../evidence/m0-architecture/2026-08-04-owner-approval.md).

## Phase 1 / M1 — Platform reproducible

Status: M1 development-platform qualified
Accepted: August 5, 2026

- [x] RB Pinned laptop Docker development environment builds reproducibly. Evidence: [locked toolchain](../evidence/m1-platform/environment/README.md) and [M1 evidence index](../evidence/m1-platform/README.md).
- [x] RB Container images support the target architecture and run non-root. Evidence: [container and ARM64 evidence](../evidence/m1-platform/containers/README.md).
- [x] RB amd64 Compose lifecycle and linux/arm64 multi-architecture image builds pass. Evidence: [container and Compose evidence](../evidence/m1-platform/containers/README.md).
- [x] RB SQLite uses the approved pragmas on a supported local development filesystem. Evidence: [SQLite profile evidence](../evidence/m1-platform/operations/sqlite-profile.md).
- [x] RB Compatibility scan fails safely for unsupported data. Evidence: [AT-COMP-FOUNDATION-01](../evidence/m1-platform/tests/README.md#at-comp-foundation-01).
- [x] RB CI enforces formatting, typing, tests, dependency integrity, architecture freeze, and documentation checks. Evidence: [quality evidence](../evidence/m1-platform/tests/README.md) and [GitHub Actions evidence](../evidence/m1-platform/tests/github-actions.md).
- [x] QT Development-host startup and resource measurements are retained as non-production evidence. Evidence: [development-host measurement](../evidence/m1-platform/performance/development-host-warm/summary.md) and [M1 interpretation](../evidence/m1-platform/README.md#outcome).
- [x] RB Milestone status is recorded explicitly as `M1 development-platform qualified`. Evidence: [M1 owner review](../evidence/m1-platform/approvals/m1-review.md).

Native Raspberry Pi execution, Pi SSD/ext4 verification, thermal/throttling tests, and native Pi
performance budgets are not M1 criteria. They are deferred deployment qualifications governed by
ADR-0036.

## Phase 2 / M2 — Security boundary proven

Status: M2 security boundary proven
Accepted: August 6, 2026

- [x] RB Minimal permanent household events, atomic bootstrap append, idempotency, replay, unknown-contract failure, and synchronous authorization projection pass. Evidence: `m2-security/tests/bootstrap.md`.
- [x] RB Household and initial owner bootstrap atomically. Evidence: `m2-security/tests/bootstrap.md`.
- [x] RB Current authorization projection gates every protected request. Evidence: `m2-security/security/authorization.md`.
- [x] RB Cross-household and role-capability tests pass. Evidence: `m2-security/security/authorization.md`.
- [x] RB Sessions rotate, expire, revoke, and invalidate after restoration as designed. Evidence: `m2-security/security/authentication.md`.
- [x] RB CSRF and security-audit coverage pass. Evidence: `m2-security/security/audit.md`.
- [ ] RD Trusted proxy, host, secure-origin, rate-limit, and remote security tests pass. Deferred while remote access remains disabled; local rate limiting and same-origin validation pass.
- [x] RB Critical identity flows pass accessibility checks. Evidence: `m2-security/browser/README.md`.

## Phase 3 / M3 — Event integrity proven

Status: M3 event integrity proven
Accepted: August 7, 2026

- [x] RB General event platform extends and replays the Phase 2 household contracts without rewriting stored events. Evidence: [contract and migration results](../evidence/m3-event-integrity/tests/README.md#phase-2-compatibility).
- [x] RB Historical fixtures replay deterministically. Evidence: [AT-EVT-02](../evidence/m3-event-integrity/tests/README.md#at-evt-02-contracts-and-replay).
- [x] RB Unknown event contracts enter restricted recovery mode. Evidence: [compatibility results](../evidence/m3-event-integrity/tests/README.md#unknown-contract-recovery).
- [x] RB Atomic multi-stream failures leave no partial state. Evidence: [AT-EVT-04](../evidence/m3-event-integrity/tests/README.md#at-evt-04-atomic-multi-stream-append).
- [x] RB Equivalent duplicate commands return one stored logical result. Evidence: [AT-EVT-05](../evidence/m3-event-integrity/tests/README.md#at-evt-05-idempotency).
- [x] RB Snapshot incompatibility/corruption falls back to replay. Evidence: [snapshot results](../evidence/m3-event-integrity/tests/README.md#snapshots-subjects-and-time).
- [x] RB Corrections, voids, reinstatements, and compensations produce correct effective state. Evidence: [AT-EVT-03](../evidence/m3-event-integrity/tests/README.md#at-evt-03-correction-controls).
- [x] RB Projection rebuild, interruption, rollback, FTS swap, and cleanup tests pass. Evidence: [AT-PRJ-03](../evidence/m3-event-integrity/tests/README.md#at-prj-03-projection-recovery).
- [x] QT Replay, append, and rebuild measurements are retained on the pinned development environment. Evidence: [one-million-event qualification](../evidence/m3-event-integrity/performance/laptop-container/summary.md).

## Phase 4 / M4 — Internal minimum usable baseline

Status: M4 internal minimum usable baseline accepted
Accepted: August 10, 2026

This is an internal operational release, not final production and not approval for remote/public deployment.

- [x] RB Secure local household access works for approved internal users. Evidence: [core workflows](../evidence/m4-internal-baseline/core-workflows/README.md).
- [x] RB Animal profiles and lifecycle are usable. Evidence: [core workflows](../evidence/m4-internal-baseline/core-workflows/README.md).
- [x] RB Feedings, weight/length measurements, and sheds are recorded and corrected safely. Evidence: [core workflows](../evidence/m4-internal-baseline/core-workflows/README.md).
- [x] RB Enclosures, assignment, and cleaning are usable, including correct current occupancy after reassignment. Evidence: [core workflows](../evidence/m4-internal-baseline/core-workflows/README.md).
- [x] RB Animal timeline accurately reflects effective history and identifies enclosure-assignment targets. Evidence: [browser timeline](../evidence/m4-internal-baseline/browser/README.md).
- [x] RB Basic on-demand and scheduled database/attachment backup works and verifies. Evidence: [backup drill](../evidence/m4-internal-baseline/operations/backups/README.md).
- [x] RB Feature slices use animal-owned ports with no circular domain imports. Evidence: [domain boundaries](../evidence/m4-internal-baseline/tests/domain-boundaries/README.md).
- [x] RB Attachment active-content and resource-exhaustion tests pass for included upload flows. Evidence: [attachment security](../evidence/m4-internal-baseline/security/attachments/README.md).
- [x] RB Core mobile, keyboard, and screen-reader workflows meet acceptance criteria. Evidence: [accessibility](../evidence/m4-internal-baseline/accessibility/README.md).
- [x] RB Internal operator completes a basic restore rehearsal. Evidence: [restore rehearsal](../evidence/m4-internal-baseline/operations/backups/README.md).
- [ ] RD Remote access remains disabled until all RD controls through M7 are accepted.

Owner acceptance: [August 10, 2026 owner acceptance record](../evidence/m4-internal-baseline/approvals/2026-08-10-owner-acceptance.md).

## Phase 5 / M5 — Operational workflows reliable

Status: M5 implementation-qualified; owner acceptance pending

- [x] RB Inventory remains correct under concurrency and compensation. Evidence: [inventory correctness](../evidence/m5-operations/tests/inventory.md).
- [x] RB Expenses enforce authorization and correction policy. Evidence: [expense policy](../evidence/m5-operations/tests/expenses.md) and [authorization](../evidence/m5-operations/security/authorization.md).
- [x] RB Fixed and event-relative reminder facts recalculate from effective history, remain explainable, and deduplicate independently through intent, outbox, jobs, and attempts. Evidence: [reminders](../evidence/m5-operations/tests/reminders.md) and [pipeline boundaries](../evidence/m5-operations/tests/notifications.md).
- [x] RB Lease expiry, crash recovery, retry, reconciliation, and dead letters pass. Evidence: [durable jobs](../evidence/m5-operations/tests/jobs.md) and [crash recovery](../evidence/m5-operations/operations/crash-recovery.md).
- [x] RB External side-effect strategies handle the uncertain crash window. Evidence: [external-effect recovery](../evidence/m5-operations/tests/external-effects.md).

Owner acceptance is not yet recorded. Phase 6 has not started.

## Phase 6 / M6 — Product experience complete

- [ ] RB FTS5 search cannot disclose unauthorized records.
- [ ] RB Reports reconcile with authoritative event fixtures.
- [ ] RB Projection freshness is visible when material.
- [ ] RB Strict CSP passes without unsafe directives.
- [ ] RB PWA performs no offline writes and persists only allow-listed drafts.
- [ ] RB Critical journeys meet WCAG 2.2 AA.
- [ ] QT Dashboard, search, UI, memory, and storage meet development-environment targets.
- [ ] RB Weight/length trends, husbandry-frequency statistics, feeding and shed intervals, and due/overdue care are presented from effective history.
- [ ] RB Suggested feeding and shed windows use sufficient effective history, expose deterministic provenance, and are labeled as estimates rather than requirements.
- [ ] RB Optional species/life-stage husbandry reference profiles are curated and versioned with sources, prefer ranges, never invent missing guidance, and never silently replace owner schedules.

## Phase 7 / M7 — Recovery and compatibility proven

- [ ] RB Backup lease prevents overlap and manifest derives from completed DB copy.
- [ ] RD Encrypted off-device backup and independent key recovery are proven.
- [ ] RB Isolated restoration validates data and meets qualified recovery targets.
- [ ] RB Upgrade, rollback, event, projection, plugin, and backup compatibility paths pass.
- [ ] RB Missing plugins and unknown newer contracts fail safely.
- [ ] RD Proxy chain, headers, upload delivery, security scanning, monitoring, and runbooks pass.
- [ ] DDQ/RB Native Raspberry Pi 5 execution passes on the candidate release before Pi deployment.
- [ ] DDQ/RB Local SSD/ext4 placement is verified for database, attachments, Docker data, and backup staging before Pi deployment.
- [ ] DDQ/RB Cold/warm performance, CPU, memory, thermal, and throttling budgets pass against the versioned dataset before Pi deployment.
- [ ] DDQ/RB SQLite durability/persistence and backup/restoration behavior pass natively before Pi deployment.
- [ ] DDQ/RB Status is recorded explicitly as `Raspberry Pi deployment qualified` before Pi deployment.

## Phase 8 / M8 — Production release accepted

- [ ] RB Fresh install and every supported upgrade path pass.
- [ ] RB Release compatibility matrix is complete.
- [ ] RB Signed artifacts, SBOM, scans, documentation, and milestone evidence are retained.
- [ ] RB No unresolved critical or high-severity defects remain.
- [ ] RB Operator completes restore and incident exercises.
- [ ] RB Product owner approves security, accessibility, performance, recovery, and data integrity.
- [ ] RB A Raspberry Pi production launch is prohibited unless `Raspberry Pi deployment qualified` is current for the release candidate.

## Deferred capabilities

The following are DC unless promoted through an ADR and roadmap change: organizations/full multi-tenancy, OAuth, MFA, offline writes/background sync, third-party untrusted plugins, marketplace, breeding/incubation, cloud sync, AI assistant, barcode/QR/NFC, ESPHome/Home Assistant, cameras, high-frequency sensor telemetry, tamper-evident event chains, and horizontal scaling/PostgreSQL deployment.
