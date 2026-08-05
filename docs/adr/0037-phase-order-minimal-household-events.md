# ADR-0037: Bring Minimal Household Events Forward into Phase 2

Status: Accepted
Acceptance date: 2026-08-05

## Context

ADR-0002 requires meaningful business transitions to be immutable domain events. ADR-0015
requires household creation, initial-owner membership events, and the synchronous authorization
projection to commit atomically. The original roadmap placed the general event platform in Phase
3 while Phase 2 requires a working first-run household bootstrap. Excluding every event-store
capability from Phase 2 would either violate those accepted decisions, create temporary relational
household truth that later needs migration, or make Phase 2 impossible to complete.

## Decision

Change implementation order, not architecture. Phase 2 may implement the minimum permanent event
infrastructure needed for initial household bootstrap:

- the established immutable event envelope fields required by the household contracts;
- stream identity `household:{household_uuid}` and contiguous per-stream versions;
- registered schema-version-1 contracts `household.created` and `household.owner_added`;
- one atomic append containing both bootstrap events;
- correlation and causation identifiers;
- command idempotency with canonical command hash and schema-versioned stored result;
- synchronous household-summary and authorization-membership projections;
- the required relational user credential record;
- one database transaction containing the idempotency result, user record, household events, and
  synchronous projections;
- deterministic replay of the implemented household stream; and
- safe startup/replay failure for unknown implemented household contract identities.

The stored event format, contract identity (`event_type + schema_version`), UUID identity,
timestamps, stream versions, payload typing, technical metadata boundary, and checksum follow the
existing event and database catalogs. This is the first production slice of the permanent event
platform, not a temporary Phase 2 format.

## Explicit exclusions

Phase 2 does not implement animal streams/events, public event APIs, full plugin event
registration, snapshots, generic correction/void/reinstatement/compensation, multi-stream business
workflows beyond bootstrap atomicity, projection shadow rebuilds/generation swaps, analytical
projections, inventory/expense/reminder/notification streams, telemetry, or any other Phase 3
animal-core capability.

## Alternatives

- Temporary relational household state followed by synthesized Phase 3 events. Rejected because
  it creates dual truth, fabricated history, and avoidable migration risk.
- Defer bootstrap until Phase 3. Rejected because identity and household authorization are the
  purpose of Phase 2.
- Bring the full event platform into Phase 2. Rejected because it expands scope beyond the two
  contracts and synchronous projections required for bootstrap.

## Compatibility requirements for Phase 3

Phase 3 must read and replay Phase 2 household events without rewriting, migrating, or changing
their contract identities. General registries and event-store adapters must adopt these same
records. Any added envelope fields must be backward-compatible or derived without mutating stored
events. Unknown newer contracts continue to fail safely. Phase 3 may add contracts and platform
capabilities but cannot replace the Phase 2 household stream with a second source of truth.

## Migration and testing implications

The Phase 2 Alembic revision creates the minimum permanent event, stream-head, idempotency, user,
household-summary, membership-authorization, session, login-rate-limit, and security-audit tables.
Migration upgrade/downgrade tests must prove a fresh bootstrap and clean reversal. Tests must prove
atomic rollback, retry idempotency, hash mismatch conflict, contiguous versions, replay,
unknown-contract failure, current authorization checks, and absence of excluded event families.

There is no migration of existing household data because no household data exists before Phase 2.
Downgrading the Phase 2 schema deletes Phase 2 data and is permitted only for fresh development
installations or after the accepted backup/rollback procedure.

## Security and operational impact

The bootstrap remains local-only. Passwords and sessions remain conventional relational records.
Only token hashes are stored. Security audit records remain separate from domain events. The
transaction must remain short, use the SQLite durability profile, and never store credentials,
session tokens, CSRF tokens, or secrets in event payloads or metadata.

## Roadmap, evidence, and schedule impact

M2 gains a release-blocker criterion for the minimal household event slice and evidence under
`/docs/evidence/m2-security/tests/bootstrap`. M3 remains responsible for the general event
platform and must explicitly prove compatibility with the Phase 2 household fixtures. No animal
or general Phase 3 capability moves into Phase 2. This phase-order amendment does not weaken the
governing event-sourcing architecture.

## Rollback

Superseding this decision requires a compatible data migration and cannot reinterpret existing
household events as relational history. The safe schedule rollback is to delay Phase 2, not to
introduce temporary household truth.
