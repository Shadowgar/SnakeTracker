# ADR-0040: Trusted Local Demo-Household Provisioning

Status: Accepted
Acceptance date: 2026-08-16

## Context

M6 owner review needs a realistic mixed-species household without changing the owner's real
household or running a second application stack. The production first-run bootstrap correctly
refuses to create another household after installation, and direct relational seeding would bypass
the event-sourced household source of truth, authorization projection, command idempotency, and
security audit.

The approved review environment must therefore host the existing real household and a separate,
fictional demo household in the same database while preserving strict tenancy in both directions.
This is local qualification support, not general multi-household administration.

## Decision

SnakeTracker may expose an internal application use case for trusted demo-household provisioning
only when the composition root explicitly selects a development, test, or local-owner-review
environment. The use case has no browser route or public API. Invocation in any other environment
hard-fails before a write begins.

The provisioner uses a reserved deterministic demo household, user, stream, operation scope, and
idempotency identity. In one database transaction it:

1. creates the relational demo user with the normal Argon2id credential policy;
2. appends canonical `household.created` version 1 and `household.owner_added` version 1 events to
   `household:{uuid}` with the existing envelope, ordering, checksum, and expected-version rules;
3. establishes the current household/owner authorization projection;
4. stores the completed command-idempotency result; and
5. appends a conventional security-audit record identifying trusted local provisioning.

Rerunning the exact provision request returns the stored result without adding records. If a
reserved identifier, email, stream, or household is present in a conflicting state, provisioning
fails closed and modifies nothing. It never adopts, repairs, renames, or deletes an existing
identity or household.

After the household exists, fictional animals and operational history are populated through normal
supported application/domain interfaces. This ADR does not authorize direct database seeding of
general demo data or bypassing capability, authorization, event, inventory, reminder, attachment,
or correction policies.

## Environment and interface boundary

- Allowed environments are explicit allow-listed values owned by the startup composition root.
- Production and unspecified environments fail closed, even if a caller knows the internal entry
  point or reserved identifiers.
- The provisioner is a command-line/development adapter over an application-owned port. It is not
  mounted into FastAPI routing and does not appear in OpenAPI or browser navigation.
- Production first-run household creation remains unchanged and continues to allow exactly the
  initial bootstrap defined by ADR-0015 and ADR-0037.

## Data safety and isolation

The mechanism requires no schema migration, event-contract change, upcaster, projection rewrite,
or mutation of existing events. The real user, household, animals, attachments, streams, sessions,
and audit history remain untouched. Qualification captures real-household counts and a verified
backup before provisioning and compares them afterward.

Tests exercise real-to-demo and demo-to-real denial for list queries, direct object identifiers,
URLs, attachments, search, reports, and commands. Every protected request still checks current
authorization projections; deterministic identifiers are never treated as authorization.

## Alternatives considered

- **Keep a separate demo Compose project:** rejected because owner review must exercise the single
  promoted application and encourages runtime/configuration drift.
- **Insert demo rows directly into SQLite:** rejected because it bypasses canonical events,
  idempotency, projections, authorization, and audit.
- **Temporarily relax production first-run bootstrap:** rejected because it expands an Internet-
  facing security boundary and changes production behavior.
- **Copy or modify the owner's household:** rejected because demonstration data must never mutate
  real records.

## Consequences and compatibility

The local composition path adds narrowly scoped test and fixture code plus bidirectional isolation
coverage. It deliberately shares the production application/domain interfaces after household
creation, so the demo remains representative without becoming a second data model. Existing
household events replay unchanged; older application versions can ignore the additional ordinary
household and animal streams.

No invitation, household switcher, household administration UI, arbitrary capability profile, or
public demo endpoint is created. Removing the local adapter later does not require a data
migration; the fictional household remains normal event-sourced data and may be removed only by a
separately reviewed demo-only procedure.

## Governance and roadmap impact

This accepted amendment operates under ADR-0028 and narrows the M6 owner-review fixture strategy.
It preserves ADR-0002, ADR-0012, ADR-0015, ADR-0032, ADR-0033, ADR-0037, and ADR-0039. Requirement
R-054 and the M6 roadmap/evidence entries govern its implementation and verification. It does not
authorize M7 work, remote deployment, production household administration, or M6 owner acceptance.
