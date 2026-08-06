# Phase 3 General Event Platform Implementation Plan

**Status:** Approved August 6, 2026; implementation authorized on `phase3/event-platform`.

**Goal:** Extend the permanent Phase 2 household-event slice into the accepted general event
platform and prove M3 event integrity without adding animal or other Phase 4 product features.

## Scope and boundaries

Phase 3 delivers internal application/domain ports and SQLite adapters for registered event
contracts, deterministic replay, atomic expected-version appends, command idempotency, snapshots,
typed subjects, correction controls, and versioned projection rebuilds. The existing
`household.created` v1 and `household.owner_added` v1 records remain byte-for-byte compatible and
replay through the generalized platform.

No animal profiles/events, husbandry, health, enclosure workflows, inventory workflows, public
event API, product search, reports, dashboards, plugins, jobs/notifications, attachments, remote
access, or Raspberry Pi deployment is authorized. Synthetic test contracts and test-only
projections may exercise multi-stream, correction, FTS5 swap, and recovery behavior without
creating Phase 4 domain functionality.

Synthetic contracts use an unmistakable reserved test namespace, live only in test/fixture
packages, and are injected only into test-created registries. Production composition, startup
scans, exports, Alembic migrations, and public routes cannot discover or register them. Projection
physical identifiers are selected only from code-owned allow-listed definitions and are never
derived from request or user data.

Phase 2 compatibility preserves the canonical envelope, payload, contract identity, global and
stream ordering fields, and checksum behavior; it does not claim identical SQLite file bytes.
Corrupt or incompatible snapshots are ignored or quarantined with diagnostics and replay fallback,
never silently deleted by aggregate loading. Phase 3 outbox scope ends at atomic durable handoff;
delivery workers, jobs, notifications, and external side effects remain excluded. Native Pi
qualification remains deferred and does not block M3.

## Governing requirements

| M3 outcome | Requirements | Accepted ADRs | Threat controls | Evidence |
|---|---|---|---|---|
| Phase 2 household compatibility and historical replay | R-002, R-004, R-043 | 0002, 0005, 0026, 0037 | TM-09, TM-20 | `m3-event-integrity/tests/contracts` |
| Atomic ordered append and idempotent retries | R-011, R-012 | 0011, 0012 | TM-09 | `m3-event-integrity/tests/multi-stream`, `tests/idempotency` |
| Snapshots and deterministic fallback | R-002, R-027 | 0002, 0026 | TM-09, TM-20 | `m3-event-integrity/tests/snapshots` |
| Correction, void, reinstatement, compensation | R-005 | 0006 | TM-09, TM-10 | `m3-event-integrity/tests/corrections` |
| Typed subject validation and UTC semantics | R-031, R-032 | 0030, 0031 | TM-04, TM-09 | `m3-event-integrity/tests/time`, `tests/subjects` |
| Synchronous and asynchronous projection infrastructure | R-006, R-007, R-008 | 0007, 0008 | TM-04, TM-18, TM-20 | `m3-event-integrity/tests/synchronous-projections`, `tests/projection-rebuild` |
| Architecture and evidence integrity | R-029, R-039 | 0028 | TM-20 | M3 evidence index and full quality gate |

## Proposed deliverables and files

- General event domain/application interfaces under `src/snaketracker/platform/events/`, with
  infrastructure implementations under `src/snaketracker/infrastructure/events/`.
- Permanent household contracts, upcasters, and historical fixtures remain under
  `src/snaketracker/domains/households/`; no contract is moved into Alembic.
- Snapshot ports and SQLite adapter under `platform/events` and `infrastructure/events`.
- Projection definitions, handlers, generation/rebuild coordinator, and internal query registry
  under `src/snaketracker/platform/projections/` and `infrastructure/projections/`.
- Alembic revision after `0003_phase2_review_hardening` adding only accepted event-platform,
  snapshot, outbox, and projection-management structures.
- Unit, integration, architecture, migration, concurrency, interruption, and recovery suites under
  matching `tests/` packages.
- Versioned M3 fixtures under `tests/fixtures/events/` and qualification artifacts under
  `docs/evidence/m3-event-integrity/`.

Exact physical table and index names will follow `docs/architecture/database-schema.md`. Any
required semantic deviation stops implementation and invokes ADR-0028 rather than silently
changing the architecture.

## Ordered test-driven tasks

1. **Freeze Phase 2 compatibility.** Copy representative household event rows into permanent
   historical fixtures; first prove the generalized registry, deserializer, checksum, replay, and
   startup scanner read them unchanged and fail safely on unknown newer contracts.
2. **Generalize contract registration.** Add typed registration metadata for owner, payload,
   handlers, subject rules, correction capabilities, renderers, and permanent upcaster chains.
   Test duplicate identities, incomplete registrations, invalid upcast chains, and exact payload
   validation before replacing the closed Phase 2 registry.
3. **Implement stream loading and single-stream append.** Define application-owned ports and a
   SQLite adapter enforcing household scope, contiguous versions, canonical envelope storage,
   checksums, contract validation, and expected-version conflict behavior in one short transaction.
4. **Implement atomic multi-stream append.** Validate every expected version before insert, sort
   streams lexically by household/type/UUID, and atomically commit events, synchronous projection
   writes, outbox handoff, and idempotency result. Test conflict/rollback at every boundary and
   deterministic ordering suitable for PostgreSQL.
5. **Complete command idempotency.** Enforce the unique household/actor/scope/key boundary,
   canonical command hash, status, result events and versions, schema-versioned sanitized response,
   correlation, completion, and 90-day expiry policy. Test equivalent retry, hash mismatch,
   transaction crash, stored-response compatibility, and concurrent duplicate submission.
6. **Add rebuildable snapshots.** Store schema/implementation versions, stream version, boundary
   event, checksum, and state; use the measurable policy from the architecture. Test compatible
   load, incompatible/corrupt deletion or ignore, replay fallback, and equivalence with full replay.
7. **Add typed subject validation and time rules.** Register subject resolvers owned by application
   ports; verify registration, existence, household ownership, permission, required roles, UTC
   microsecond precision, household-time interpretation, DST ambiguity, and future-skew rejection.
8. **Implement correction controls.** Add registry-enforced correct/void/reinstate/compensate
   policies and generic historical-control contracts. Test role and age policies, target contract,
   same-stream ownership, duplicate void prevention, reinstatement, correlation/causation lineage,
   and effective-state reversal using synthetic fixtures only.
9. **Implement projection generations.** Add definition/generation/checkpoint catalogs and
   synchronous handler orchestration. Build asynchronous shadow replay to a high-water mark, tail
   catch-up, validation, atomic catalog activation, rollback, retained previous generation, and
   resumable cleanup.
10. **Prove every swap strategy.** Integration-test ordinary tables, same-generation foreign keys,
    interdependent groups, views, and synthetic FTS5 content/virtual tables for successful swap,
    validation failure, interruption before/around activation, writes during catch-up, rollback,
    optimization, and cleanup. No user-facing search is introduced.
11. **Qualify performance and growth gates.** Run replay, append, multi-stream contention,
    snapshot, and rebuild measurements against the versioned representative dataset on the pinned
    laptop Docker environment. Record p50/p95, busy failures, database/WAL growth, rebuild
    headroom, and whether any 10,000-event/100 ms/1 MiB/five-stream threshold is crossed.
12. **Close M3 evidence only after verification.** Run the complete quality, migration, Docker,
    amd64, and ARM64 gates; retain exact commands, revisions, environment, results, reviewer, and
    checksums. Mark M3 items complete only with evidence and owner acceptance; keep M4–M8 unchecked.

## Test and acceptance map

| M3 checklist criterion | Primary acceptance tests |
|---|---|
| Household contracts extend without rewrite | historical fixture bytes/checksums, generalized registry replay, fresh and upgraded DB |
| Historical fixtures replay deterministically | repeated full replay and upcast-chain golden-state comparisons |
| Unknown contracts restrict startup | newer type/version compatibility and readiness integration tests |
| Multi-stream failures leave no partial state | expected-version, injected write/projection/outbox failures, concurrency tests |
| Duplicate commands return one result | equivalent/hash-mismatch/concurrent retry and crash-boundary tests |
| Snapshot failure falls back to replay | corrupt, incompatible, missing, stale, and valid snapshot matrix |
| Corrections produce correct effective state | role/age/target/duplicate/reinstate/compensation fixtures |
| Projection rebuild and FTS swap recover safely | swap, tail, interruption, FK/group/view/FTS rollback and cleanup matrix |
| Qualification targets retained | reproducible benchmark manifest and raw/summary evidence |

## Commit sequence

1. `docs: add Phase 3 event platform implementation plan`
2. `test: preserve Phase 2 household event compatibility`
3. `feat: generalize event contracts and stream storage`
4. `feat: add atomic multi-stream append and idempotency`
5. `feat: add snapshots subjects and correction controls`
6. `feat: add projection generation rebuilds`
7. `test: qualify Phase 3 event integrity and recovery`
8. `docs: record Phase 3 qualification evidence`
9. `docs: accept M3 event integrity` only after explicit owner acceptance

Each behavior begins with a failing test or is added alongside its executable contract. Commits stay
reviewable; no squash, history rewrite, or architecture change is assumed.

## Risks and rollback points

- Phase 2 event incompatibility is a release blocker; preserve the existing adapter until fixture
  parity passes, then switch through application-owned ports.
- SQLite lock growth is controlled by short transactions, deterministic stream order, bounded
  synchronous handlers, and contention tests. A measured breach stops expansion.
- Projection activation never destroys the prior generation. Pre-activation failure drops only the
  shadow generation; post-activation failure restores the retained catalog pointer.
- Alembic changes use expand-first revisions. Binary rollback is allowed only when the prior binary
  understands every stored contract; otherwise use the accepted backup/restore procedure.
- FTS5 is exercised only as projection infrastructure. Search authorization and product UX remain
  Phase 6.

## Review decisions requested

1. Approve `phase3/event-platform` as the branch name and this twelve-task order.
2. Approve synthetic internal contracts/projections for multi-stream, correction, compensation,
   and FTS rebuild tests so no Phase 4 animal contract is introduced early.
3. Approve a forward Alembic revision after 0003 rather than modifying the accepted Phase 2
   migrations.

Implementation was explicitly approved August 6, 2026. Any semantic conflict with an accepted ADR
or database contract remains a stop condition under ADR-0028.
