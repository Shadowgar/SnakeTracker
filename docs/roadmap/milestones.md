# Roadmap and Final Milestone Acceptance Checklist

## Classification legend

- **RB:** Mandatory release blocker for the milestone/release introducing the capability.
- **RD:** Mandatory before remote or public deployment.
- **QT:** Qualified operational target for the pinned environment and representative dataset.
- **DC:** Deferred capability.

## Phase 0 / M0 — Architecture approved

- [ ] RB Complete architecture, diagrams, catalogs, threat model, runbooks, traceability, dataset, UX IA, ADRs, and roadmap exist.
- [ ] RB Document links and required sections validate.
- [ ] RB Owner approves assumptions and unresolved decisions.
- [ ] RB ADRs transition from Proposed to Accepted.
- [ ] RB Architecture decision freeze is recorded under `/docs/evidence/m0-architecture`.

## Phase 1 / M1 — Platform reproducible

- [ ] RB Pinned development and Pi environments build reproducibly.
- [ ] RB Container images support the target architecture and run non-root.
- [ ] RB SQLite is on a qualified local SSD filesystem with approved pragmas.
- [ ] RB Compatibility scan fails safely for unsupported data.
- [ ] RB CI enforces formatting, typing, tests, dependency integrity, and documentation checks.
- [ ] QT Platform meets startup and idle-resource qualification targets.

## Phase 2 / M2 — Security boundary proven

- [ ] RB Household and initial owner bootstrap atomically.
- [ ] RB Current authorization projection gates every protected request.
- [ ] RB Cross-household and role-capability tests pass.
- [ ] RB Sessions rotate, expire, revoke, and invalidate after restoration as designed.
- [ ] RB CSRF and security-audit coverage pass.
- [ ] RD Trusted proxy, host, secure-origin, rate-limit, and remote security tests pass.
- [ ] RB Critical identity flows pass accessibility checks.

## Phase 3 / M3 — Event integrity proven

- [ ] RB Historical fixtures replay deterministically.
- [ ] RB Unknown event contracts enter restricted recovery mode.
- [ ] RB Atomic multi-stream failures leave no partial state.
- [ ] RB Equivalent duplicate commands return one stored logical result.
- [ ] RB Snapshot incompatibility/corruption falls back to replay.
- [ ] RB Corrections, voids, reinstatements, and compensations produce correct effective state.
- [ ] RB Projection rebuild, interruption, rollback, FTS swap, and cleanup tests pass.
- [ ] QT Replay, append, and rebuild meet qualified Pi targets.

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
- [ ] QT Dashboard, search, UI, memory, and storage meet qualified Pi targets.

## Phase 7 / M7 — Recovery and compatibility proven

- [ ] RB Backup lease prevents overlap and manifest derives from completed DB copy.
- [ ] RD Encrypted off-device backup and independent key recovery are proven.
- [ ] RB Isolated restoration validates data and meets qualified recovery targets.
- [ ] RB Upgrade, rollback, event, projection, plugin, and backup compatibility paths pass.
- [ ] RB Missing plugins and unknown newer contracts fail safely.
- [ ] RD Proxy chain, headers, upload delivery, security scanning, monitoring, and runbooks pass.
- [ ] QT Full Pi and versioned-dataset qualification passes or has an approved superseding ADR.

## Phase 8 / M8 — Production release accepted

- [ ] RB Fresh install and every supported upgrade path pass.
- [ ] RB Release compatibility matrix is complete.
- [ ] RB Signed artifacts, SBOM, scans, documentation, and milestone evidence are retained.
- [ ] RB No unresolved critical or high-severity defects remain.
- [ ] RB Operator completes restore and incident exercises.
- [ ] RB Product owner approves security, accessibility, performance, recovery, and data integrity.

## Deferred capabilities

The following are DC unless promoted through an ADR and roadmap change: organizations/full multi-tenancy, OAuth, MFA, offline writes/background sync, third-party untrusted plugins, marketplace, breeding/incubation, cloud sync, AI assistant, barcode/QR/NFC, ESPHome/Home Assistant, cameras, high-frequency sensor telemetry, tamper-evident event chains, and horizontal scaling/PostgreSQL deployment.
