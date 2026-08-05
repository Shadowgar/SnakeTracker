# Requirements Traceability Matrix

This matrix is authoritative for architecture acceptance. Evidence paths are relative to `/docs/evidence`. Test IDs name acceptance specifications that Phase 1+ must implement; M0 document checks are reproducible immediately.

| ID | Requirement | Class | Governing ADR | Threat-model control | Implementation phase | Acceptance test/procedure | Evidence artifact | Milestone |
|---|---|---|---|---|---|---|---|---|
| R-001 | Modular monolith with inward dependencies and startup composition root | RB | 0001 | TM-14 | 1 | AT-ARCH-01 dependency-boundary test | m1-platform/tests/dependencies | M1 |
| R-002 | Business transitions event sourced; operational state relational | RB | 0002, 0003 | TM-09 | 3 | AT-EVT-01 source-of-truth/replay suite | m3-event-integrity/tests/event-boundary | M3 |
| R-003 | Explicit aggregate/stream ownership; no animal/husbandry/health cycles | RB | 0004 | TM-09 | 3–4 | AT-ARCH-02 import and ownership tests | m4-internal-baseline/tests/domain-boundaries | M4 |
| R-004 | Typed, versioned event contracts and permanent upcasters | RB | 0005 | TM-20 | 3 | AT-EVT-02 historical contract replay | m3-event-integrity/tests/contracts | M3 |
| R-005 | Corrections, voids, reinstatement, and compensation are append-only | RB | 0006 | TM-09, TM-10 | 3 | AT-EVT-03 correction-chain suite | m3-event-integrity/tests/corrections | M3 |
| R-006 | Authorization, invariants, current state, and inventory are synchronous projections | RB | 0007 | TM-04 | 2–5 | AT-PRJ-01 synchronous consistency tests | m3-event-integrity/tests/synchronous-projections | M3 |
| R-007 | Search, reports, statistics, and snapshots are asynchronous | RB | 0007 | TM-18 | 3–6 | AT-PRJ-02 lag/freshness behavior | m6-product-experience/tests/async-freshness | M6 |
| R-008 | Projection generation rebuild, validation, atomic swap, rollback, and cleanup | RB | 0008 | TM-09, TM-20 | 3 | AT-PRJ-03 rebuild recovery matrix | m3-event-integrity/tests/projection-rebuild | M3 |
| R-009 | SQLite v1 with explicit PostgreSQL migration boundary | RB | 0009 | TM-18 | 1 | AT-DB-01 adapter and concurrency qualification | m1-platform/tests/database-boundary | M1 |
| R-010 | SQLite WAL/durability/maintenance profile; supported local development filesystem at M1 and local SSD/ext4 before Pi deployment | RB | 0010, 0036 | TM-09, TM-18 | 1, 7 | OP-DB-01 pragma/filesystem development check; OP-DB-02 Pi SSD/ext4 qualification | m1-platform/operations/sqlite-profile; m7-recovery-compatibility/performance/pi/storage | M1; Pi deployment |
| R-011 | Atomic multi-stream append with all expected versions and deterministic ordering | RB | 0011 | TM-09 | 3 | AT-EVT-04 atomicity/deadlock-order suite | m3-event-integrity/tests/multi-stream | M3 |
| R-012 | Atomic command idempotency with canonical hash and versioned stored result | RB | 0012 | TM-09 | 3 | AT-EVT-05 crash-boundary/idempotency suite | m3-event-integrity/tests/idempotency | M3 |
| R-013 | Durable leased jobs; external delivery explicitly at least once | RB | 0013 | TM-11 | 5 | AT-JOB-01 lease/crash/reconciliation suite | m5-operations/tests/jobs | M5 |
| R-014 | Reminder facts, intent, outbox, jobs, attempts have separate dedupe boundaries | RB | 0014 | TM-11 | 5 | AT-NOT-01 pipeline deduplication suite | m5-operations/tests/notifications | M5 |
| R-015 | Multi-user household and atomic initial-owner bootstrap | RB | 0015 | TM-04 | 2 | AT-AUTHZ-01 bootstrap atomicity | m2-security/tests/bootstrap | M2 |
| R-016 | Current authorization projection checks every protected request | RB | 0015 | TM-04, TM-16 | 2 | AT-AUTHZ-02 role/tenant matrix | m2-security/security/authorization | M2 |
| R-017 | Secure password, session, CSRF, reset, and invitation handling | RB/RD | 0016 | TM-01, TM-02, TM-03 | 2 | AT-AUTHN-01 security suite | m2-security/security/authentication | M2 |
| R-018 | Immutable finalized attachment versions and safe delivery | RB/RD | 0017 | TM-06, TM-07 | 4 | AT-UP-01 adversarial upload/delivery suite | m4-internal-baseline/security/attachments | M4 |
| R-019 | Single backup initiator, lease, coherent manifest, encryption, restore validation | RB/RD | 0018 | TM-12, TM-13 | 4, 7 | OP-BK-01 backup and restore drill | m7-recovery-compatibility/operations/restore | M7 |
| R-020 | SQLite FTS5 search with authorization and generation rebuild | RB | 0019 | TM-04 | 6 | AT-SRCH-01 leakage and swap suite | m6-product-experience/tests/search | M6 |
| R-021 | Server-rendered strict-CSP UI using Jinja/HTMX/Alpine CSP/Chart.js | RB/RD | 0020 | TM-05 | 4–6 | AT-CSP-01 browser policy regression | m6-product-experience/security/csp | M6 |
| R-022 | PWA offline read-only; draft persistence deny-by-default | RB | 0021 | TM-19 | 6 | AT-PWA-01 offline/draft suite | m6-product-experience/tests/pwa | M6 |
| R-023 | Plugins are trusted, verified, compatible, retained for historical handlers, not sandboxed | RB when enabled | 0022 | TM-15, TM-20 | 7 | AT-PLG-01 lifecycle/compatibility suite | m7-recovery-compatibility/tests/plugins | M7 |
| R-024 | Structured observability, health, redacted logs, and security audit | RB/RD | 0023, 0032 | TM-16, TM-17 | 1–2 | AT-OBS-01 health/audit/redaction suite | m2-security/security/audit | M2 |
| R-025 | Reproducible native Pi performance, thermal, storage, SQLite, backup, and restoration qualification before Pi deployment | DDQ/RB | 0024, 0036 | TM-12, TM-13, TM-18 | 7/pre-deployment | PERF-PI-01 pinned native qualification suite | m7-recovery-compatibility/performance/pi | Raspberry Pi deployment |
| R-026 | Versioned API, stable errors, ETags/If-Match and expected-stream semantics | RB | 0025 | TM-09 | 3–6 | AT-API-01 compatibility/concurrency suite | m6-product-experience/tests/api | M6 |
| R-027 | Expand-migrate-contract; event upcasters outside Alembic; controlled rollback | RB | 0026 | TM-20 | 1–7 | AT-MIG-01 upgrade/downgrade matrix | m7-recovery-compatibility/tests/migrations | M7 |
| R-028 | High-frequency telemetry excluded pending separate ingestion architecture | DC | 0027 | TM-18 | Future | AR-REV-01 ADR approval | m0-architecture/approvals/telemetry | Future |
| R-029 | Architecture decision freeze and ADR consequence analysis | RB | 0028 | TM-20 | 0–8 | DOC-ARCH-01 ADR governance audit | m0-architecture/approvals/freeze | M0 |
| R-030 | Trusted proxy/header/host/secure-origin validation | RD | 0029 | TM-08 | 7 | AT-PROXY-01 spoofing integration suite | m7-recovery-compatibility/security/proxy | M7 |
| R-031 | UTC storage and household-timezone reporting semantics | RB | 0030 | TM-09 | 3–6 | AT-TIME-01 DST/skew/precision suite | m3-event-integrity/tests/time | M3 |
| R-032 | Typed subject registration, existence, tenancy, and authorization validation | RB | 0031 | TM-04 | 3 | AT-SUB-01 subject-validation suite | m3-event-integrity/tests/subjects | M3 |
| R-033 | Conventional append-oriented security audit separate from domain events | RB/RD | 0032 | TM-16, TM-17 | 2 | AT-AUD-01 coverage/immutability/redaction suite | m2-security/security/audit | M2 |
| R-034 | Per-release compatibility matrix and safe startup for newer data | RB | 0033 | TM-20 | 1–8 | AT-COMP-01 startup compatibility matrix | m7-recovery-compatibility/tests/compatibility | M7 |
| R-035 | WCAG 2.2 AA and touch-friendly mobile-first workflows | RB | 0034 | TM-05 | 2, 4, 6 | AT-A11Y-01 automated/manual critical journeys | m6-product-experience/accessibility/critical-journeys | M6 |
| R-036 | Internal minimum usable baseline after Phase 4 | RB | 0035 | TM-03–TM-07, TM-09, TM-13 | 4 | UAT-M4-01 internal baseline checklist | m4-internal-baseline/approvals/release | M4 |
| R-037 | Remote/public deployment waits for all RD controls | RD | 0035 | All RD controls | 7 | GATE-RD-01 deployment readiness review | m7-recovery-compatibility/approvals/remote | M7 |
| R-038 | Full production launch waits for M8 evidence and owner approval | RB | 0035 | All applicable | 8 | GATE-M8-01 production acceptance | m8-production/approvals/launch | M8 |
| R-039 | Evidence is structured, retained, and reproducible | RB | 0028 | TM-20 | 0–8 | DOC-EV-01 evidence manifest audit | each milestone root | Each |
| R-040 | OAuth, MFA, organizations, offline writes, marketplace, AI, telemetry and similar expansions are deferred | DC | 0021, 0022, 0027, 0035 | Varies | Future | AR-REV-02 approved promotion ADR | m0-architecture/approvals/deferred | Future |
| R-041 | Laptop Docker is the primary development environment; amd64 tests/Compose and ARM64 image builds qualify M1 without native Pi hardware | RB | 0036 | TM-18, TM-20 | 1–6 | DEV-PLAT-01 local quality, Compose, amd64 runtime, and ARM64 build suite | m1-platform | M1 |
| R-042 | Native Pi execution, SSD/ext4, cold/warm performance, resources, thermal behavior, SQLite persistence, and backup/restore pass before Pi deployment | DDQ/RB | 0010, 0018, 0024, 0036 | TM-12, TM-13, TM-18, TM-20 | 7/pre-deployment | PERF-PI-01 and OP-BK-01 deployment qualification suite | m7-recovery-compatibility/performance/pi | Raspberry Pi deployment |

## Coverage rule

A mandatory requirement is satisfied only when its governing document is accepted, its acceptance test or procedure passes for the applicable release, and its evidence artifact exists with source revision, environment, exact reproduction method, result, and reviewer. A missing link is itself a release blocker.
