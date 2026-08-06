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

- [ ] RB General event platform extends and replays the Phase 2 household contracts without rewriting stored events.
- [ ] RB Historical fixtures replay deterministically.
- [ ] RB Unknown event contracts enter restricted recovery mode.
- [ ] RB Atomic multi-stream failures leave no partial state.
- [ ] RB Equivalent duplicate commands return one stored logical result.
- [ ] RB Snapshot incompatibility/corruption falls back to replay.
- [ ] RB Corrections, voids, reinstatements, and compensations produce correct effective state.
- [ ] RB Projection rebuild, interruption, rollback, FTS swap, and cleanup tests pass.
- [ ] QT Replay, append, and rebuild measurements are retained on the pinned development environment.

## Phase 4 / M4 — Internal minimum usable baseline

This is an internal operational release, not final production and not approval for remote/public deployment.

- [ ] RB Secure local household access works for approved internal users.
- [ ] RB Animal profiles and lifecycle are usable.
- [ ] RB Feedings, weight/length measurements, and sheds are recorded and corrected safely.
- [ ] RB Enclosures, assignment, and cleaning are usable.
- [ ] RB Animal timeline accurately reflects effective history.
- [ ] RB Basic on-demand and scheduled database/attachment backup works and verifies.
- [ ] RB Feature slices use animal-owned ports with no circular domain imports.
- [ ] RB Attachment active-content and resource-exhaustion tests pass for included upload flows.
- [ ] RB Core mobile, keyboard, and screen-reader workflows meet acceptance criteria.
- [ ] RB Internal operator completes a basic restore rehearsal.
- [ ] RD Remote access remains disabled until all RD controls through M7 are accepted.

## Phase 5 / M5 — Operational workflows reliable

- [ ] RB Inventory remains correct under concurrency and compensation.
- [ ] RB Expenses enforce authorization and correction policy.
- [ ] RB Reminder facts, intent, outbox, jobs, and attempts deduplicate independently.
- [ ] RB Lease expiry, crash recovery, retry, reconciliation, and dead letters pass.
- [ ] RB External side-effect strategies handle the uncertain crash window.

## Phase 6 / M6 — Product experience complete

- [ ] RB FTS5 search cannot disclose unauthorized records.
- [ ] RB Reports reconcile with authoritative event fixtures.
- [ ] RB Projection freshness is visible when material.
- [ ] RB Strict CSP passes without unsafe directives.
- [ ] RB PWA performs no offline writes and persists only allow-listed drafts.
- [ ] RB Critical journeys meet WCAG 2.2 AA.
- [ ] QT Dashboard, search, UI, memory, and storage meet development-environment targets.

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
