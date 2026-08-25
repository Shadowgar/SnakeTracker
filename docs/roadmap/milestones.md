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

Status: M5 operational workflows reliable

Accepted: August 11, 2026

- [x] RB Inventory remains correct under concurrency and compensation. Evidence: [inventory correctness](../evidence/m5-operations/tests/inventory.md).
- [x] RB Expenses enforce authorization and correction policy. Evidence: [expense policy](../evidence/m5-operations/tests/expenses.md) and [authorization](../evidence/m5-operations/security/authorization.md).
- [x] RB Fixed and event-relative reminder facts recalculate from effective history, remain explainable, and deduplicate independently through intent, outbox, jobs, and attempts. Evidence: [reminders](../evidence/m5-operations/tests/reminders.md) and [pipeline boundaries](../evidence/m5-operations/tests/notifications.md).
- [x] RB Lease expiry, crash recovery, retry, reconciliation, and dead letters pass. Evidence: [durable jobs](../evidence/m5-operations/tests/jobs.md) and [crash recovery](../evidence/m5-operations/operations/crash-recovery.md).
- [x] RB External side-effect strategies handle the uncertain crash window. Evidence: [external-effect recovery](../evidence/m5-operations/tests/external-effects.md).

Owner acceptance: [August 11, 2026 owner acceptance record](../evidence/m5-operations/approvals/2026-08-11-owner-acceptance.md).

## Phase 5.5 / M5.5 — Multi-species animal foundation

Status: M5.5 multi-species animal foundation accepted
Accepted: August 15, 2026

M5.5 is an additive compatibility milestone required before M6. It generalizes the existing Animal
module and adds usable Spider care without rewriting accepted snake events or duplicating shared
household systems.

- [x] RB Existing `animal.registered` v1 events and all M0-M5 snake workflows replay unchanged and remain keeper-usable. Evidence: [legacy compatibility](../evidence/m5.5-multispecies-foundation/tests/compatibility/README.md) and [Snake regression](../evidence/m5.5-multispecies-foundation/tests/snake/README.md).
- [x] RB New registrations use a registered animal type/capability profile, and unknown types, profile versions, or contracts fail safely. Evidence: [capability registry](../evidence/m5.5-multispecies-foundation/tests/capabilities/README.md).
- [x] RB One household animal list and enclosure system correctly support mixed Snake and Spider collections, including reassignment and occupancy. Evidence: [mixed collection](../evidence/m5.5-multispecies-foundation/tests/mixed-collection/README.md) and [type-neutral enclosures](../evidence/m5.5-multispecies-foundation/tests/enclosures/README.md).
- [x] RB Spider profiles support shared identity, photos, feeding outcomes/prey, optional weight, enclosure/rehousing, notes, inventory, expenses, reminders, attachments, and effective timeline history. Evidence: [Spider care](../evidence/m5.5-multispecies-foundation/tests/spider-care/README.md) and [browser qualification](../evidence/m5.5-multispecies-foundation/browser/README.md).
- [x] RB Spider molt and premolt history, plus configured enclosure watering/misting and maintenance, are typed, correction-safe, replayable, and human-readable. Evidence: [Spider care](../evidence/m5.5-multispecies-foundation/tests/spider-care/README.md) and [final review](../evidence/m5.5-multispecies-foundation/reviews/README.md).
- [x] RB Capability enforcement prevents snake-only length, shed, and bath actions from appearing or executing for Spider profiles and prevents inapplicable Spider actions for Snake profiles. Evidence: [capability security](../evidence/m5.5-multispecies-foundation/security/README.md).
- [x] RB Reminder schedules expose only registered subject capabilities while retaining owner-configured intervals and M5 deduplication/recovery behavior. Evidence: [applicable reminders](../evidence/m5.5-multispecies-foundation/tests/reminders/README.md).
- [x] RB Migration upgrade/downgrade/re-upgrade, deterministic projection rebuild, backup/restore, feeding/inventory compensation, authorization, and compatibility suites preserve existing data. Evidence: [migration lifecycle](../evidence/m5.5-multispecies-foundation/operations/migrations/README.md), [backup and restore](../evidence/m5.5-multispecies-foundation/operations/backup-restore/README.md), and [shared inventory](../evidence/m5.5-multispecies-foundation/tests/inventory/README.md).
- [x] RB Mixed-collection browser journeys pass desktop/mobile, keyboard, screen-reader, and WCAG 2.2 AA checks. Evidence: [browser qualification](../evidence/m5.5-multispecies-foundation/browser/README.md) and [accessibility qualification](../evidence/m5.5-multispecies-foundation/accessibility/README.md).
- [x] QT Development-environment mixed-collection replay, response, database-growth, and container measurements are retained as non-production evidence. Evidence: [laptop/container measurements](../evidence/m5.5-multispecies-foundation/performance/laptop-container/README.md) and [container qualification](../evidence/m5.5-multispecies-foundation/containers/README.md).
- [ ] RD Remote access remains disabled until all RD controls through M7 are accepted.

Owner acceptance: [August 15, 2026 owner acceptance record](../evidence/m5.5-multispecies-foundation/approvals/2026-08-15-owner-acceptance.md).

## Pre-M6 capability extension — Four supported animal groups

Status: Implementation-qualified August 24, 2026; M6 owner acceptance remains pending

This additive extension follows accepted M5.5 history. It adds `lizard.v1` and `scorpion.v1`,
neutral molt/premolt schema v2, and four-group owner-review data under ADR-0041 without claiming
that M5.5 originally qualified more than Snake and Spider.

- [x] RB Four trusted profile matrices expose only the approved care, reminder, and analytics capabilities. Evidence: [four-group qualification](../evidence/m6-product-experience/four-group-expansion/README.md).
- [x] RB Historical Spider molt/premolt v1 and neutral Spider/Scorpion v2 replay, correct, rebuild, report, search, and analyze side by side. Evidence: [four-group qualification](../evidence/m6-product-experience/four-group-expansion/README.md).
- [x] RB One-time reminder overrides are consumed by later qualifying effective care, and standalone reminder choices are profile-aware. Evidence: [four-group qualification](../evidence/m6-product-experience/four-group-expansion/README.md).
- [x] RB Profile corrections retain animal type in household-isolated search documents. Evidence: [four-group qualification](../evidence/m6-product-experience/four-group-expansion/README.md).
- [x] RB Backup/restore and the deterministic demo-only reset preserve all four groups while the real household remains unchanged. Evidence: [four-group qualification](../evidence/m6-product-experience/four-group-expansion/README.md).
- [x] RB Four-group browser, accessibility, compatibility, migration, integrity, and Raspberry Pi ARM64 runtime qualification pass on the promoted port-8081 instance. Evidence: [four-group qualification](../evidence/m6-product-experience/four-group-expansion/README.md).

This extension does not authorize the deferred M6 UX redesign, M6 owner acceptance, PR #8 merge,
or M7 work.

## Phase 6 / M6 — Product experience complete

Status: M6 implementation-qualified; owner acceptance pending

M6 begins only after M5.5 acceptance. Its search, reports, dashboards, analytics, reference profiles,
and explainable suggestions must consume the registered animal type/capability identity, effective
feeding history, applicable measurements, snake shed history, Spider/Scorpion molt history, reminder facts,
neutral enclosure care, and versioned species/life-stage reference profiles. M6 does not redefine
the Animal aggregate or infer that every care fact applies to every type.

- [x] RB FTS5 search cannot disclose unauthorized records. Evidence: [search authorization](../evidence/m6-product-experience/security/search-authorization/README.md).
- [x] RB Reports reconcile with authoritative event fixtures. Evidence: [report tests](../evidence/m6-product-experience/tests/reports/README.md).
- [x] RB Projection freshness is visible when material. Evidence: [freshness and rebuilding behavior](../evidence/m6-product-experience/tests/async-freshness/README.md).
- [x] RB Strict CSP passes without unsafe directives. Evidence: [CSP evidence](../evidence/m6-product-experience/security/csp/README.md).
- [x] RB PWA performs no offline writes and persists only allow-listed drafts. Evidence: [read-only PWA evidence](../evidence/m6-product-experience/tests/pwa/README.md); zero forms are allow-listed.
- [x] RB Critical journeys meet WCAG 2.2 AA. Evidence: [accessibility qualification](../evidence/m6-product-experience/accessibility/critical-journeys/README.md).
- [x] QT Dashboard, search, UI, memory, and storage meet development-environment targets. Evidence: [laptop qualification](../evidence/m6-product-experience/performance/laptop-container/README.md).
- [x] RB Weight/length trends, husbandry-frequency statistics, and feeding and shed interval analytics are presented from effective history. Evidence: [analytics evidence](../evidence/m6-product-experience/tests/measurement-analytics/README.md) and [husbandry evidence](../evidence/m6-product-experience/tests/husbandry-analytics/README.md).
- [x] RB Suggested feeding and shed windows use sufficient effective history, expose deterministic provenance, and are labeled as estimates rather than requirements. Evidence: [suggestion-policy evidence](../evidence/m6-product-experience/tests/husbandry-analytics/README.md).
- [x] RB Optional species/life-stage husbandry reference profiles are curated and versioned with sources, prefer ranges, never invent missing guidance, and never silently replace owner schedules. Evidence: [reference infrastructure and content gate](../evidence/m6-product-experience/references/provenance/README.md); production guidance remains unavailable pending separate owner source approval.
- [x] RB The promoted local owner-review instance contains the unchanged real household and one ADR-0040 fictional household, with trusted event-sourced provisioning, bidirectional isolation, and exactly one Compose listener on port 8081. Evidence: [consolidated owner-review runtime](../evidence/m6-product-experience/owner-review/consolidated-demo/README.md).
- [x] RB Mobile-first Care Keeper navigation, Today actions, animal collection/profile hierarchy, forms, and plain-language analytics pass the approved owner-review correction and accessibility suite. Evidence: [mobile-first browser qualification](../evidence/m6-product-experience/browser/mobile-first/README.md) and [accessibility requalification](../evidence/m6-product-experience/accessibility/critical-journeys/mobile-first.md).
- [x] RB Production self-service registration creates an isolated owner household atomically and remains distinct from one-time bootstrap and ADR-0040 trusted demo provisioning. Evidence: [correctness/account lifecycle tranche](../evidence/m6-product-experience/correctness-account-lifecycle/README.md).
- [x] RB Today/reminder state advances from effective qualifying care for fixed and event-relative schedules across the four trusted profiles, with correction/void/reinstate and one-time override coverage. Evidence: [correctness/account lifecycle tranche](../evidence/m6-product-experience/correctness-account-lifecycle/README.md).
- [x] RB Inventory items edit, adjust, archive, leave active feeding choices, retain history, and restore; event-sourced item identity is never hard-deleted. Evidence: [correctness/account lifecycle tranche](../evidence/m6-product-experience/correctness-account-lifecycle/README.md).

Owner acceptance is not yet recorded. M7 and M8 remain unstarted.

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
