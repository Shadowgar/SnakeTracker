# M3 Test Evidence

The authoritative local gate passed with 175 tests, line coverage above 95%, branch coverage above
85%, Ruff, mypy, architecture boundaries, architecture freeze, documentation links, dependency
integrity, Compose configuration, and zero known dependency vulnerabilities. The retained
`quality-gate.log` is the raw result; focused logs make each acceptance boundary independently
reviewable.

## Phase 2 compatibility

`contracts-and-compatibility.log` proves the permanent Phase 2 fixture checksums, canonical
envelope and payload reconstruction, deterministic household replay, fresh migration lifecycle,
and a real `0003_phase2_review_hardening` database upgraded through `0004_event_platform` without
changing any household event or subject row.

## AT-EVT-02 contracts and replay

The contract registry tests cover exact identities, typed payloads, duplicate rejection,
contiguous permanent upcasters, reserved-test isolation, corruption checksums, and deterministic
historical replay. Unknown newer contracts fail closed.

## Unknown-contract recovery

Startup compatibility scans every distinct stored `event_type + schema_version`, not only
household streams. An unknown contract in any stream yields `RECOVERY_REQUIRED` with reason
`event_contract_unknown`; supported Phase 2 records remain normally readable.

## AT-EVT-04 atomic multi-stream append

`atomicity-and-idempotency.log` proves lexical stream ordering, expected versions for every stream,
precondition conflicts, concurrent writers, and rollback of events, stream heads, synchronous
projections, outbox handoff, and idempotency result when any transaction boundary fails.

## AT-EVT-05 idempotency

The same suite proves the household/actor/scope/key uniqueness boundary, canonical command hash,
90-day expiry, stored response schema version, result event IDs and versions, equivalent retries,
hash mismatch rejection, and concurrent duplicate collapse to one logical result.

## Snapshots, subjects, and time

`snapshots-subjects-time-corrections.log` proves the measurable snapshot policy, checksum and
schema/implementation compatibility, diagnostic quarantine, non-deletion, and deterministic full
replay fallback. It also covers structural subject requirements, in-transaction existence,
household ownership and current actor permission, UTC storage, five-minute future skew, household
reporting, nonexistent local times, and explicit DST folds.

## AT-EVT-03 correction controls

The correction suite proves capability, role and age policy; same-stream/household targets;
permitted correction contracts; duplicate-void prevention; explicit reinstatement; immutable
history; effective-state replacement/reversal; and required compensation correlation/causation
lineage. Synthetic correction contracts remain test-only.

## AT-PRJ-03 projection recovery

`projection-recovery.log` proves synchronous transaction rollback and asynchronous high-water
replay, tail catch-up, validation, atomic catalog activation, interruption before and after
activation, retained rollback, failed and retained cleanup, ordinary tables, same-generation
foreign keys, interdependent groups, views, and FTS5 generations. All physical identifiers come
from registered definitions.
