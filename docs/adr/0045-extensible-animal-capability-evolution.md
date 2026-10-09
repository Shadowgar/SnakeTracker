# ADR-0045: Extensible Animal profile lifecycle and release compatibility

Status: Proposed
Decision date: 2026-10-01

## Context

[ADR-0039](0039-multispecies-animal-capabilities.md) and
[ADR-0041](0041-four-group-capability-expansion-and-neutral-molt-contracts.md) already establish
trusted versioned profiles, capability-driven workflows and permanent historical semantics.
This decision adds lifecycle and release compatibility rules. The current startup scanner checks
only event type/schema version: an understood `animal.registered` v2 can still contain an unknown
profile. Enumerating every readable profile in Add Animal would also expose indistinguishable
old/current choices when a successor exists.

## Decision

### Capability identity is independent of taxonomy

`snake.v1`, `spider.v1`, `lizard.v1`, `scorpion.v1` and planned `amphibian.v1` are **Care Keeper
capability/workflow profile identities**, not biological taxonomic classifications or ranks.
The profile answers which application workflows/capabilities apply; the linked Care Keeper taxon
owns biological identity. A taxon link never substitutes for or redefines the registered profile.
The [controlling plan's examples](../plans/2026-10-01-extensible-animal-and-species-platform.md#capability-foundation-and-read-only-code-audit)
illustrate these independent concepts.

Immutable production registration events already encode the existing four v1 identities (explicitly
or through their type/version fields; registration v1 implies `snake.v1`). Do not rename them to
resemble taxonomy: that creates compatibility risk without improving biological correctness.
Historical workflow semantics remain permanent; incompatible behavior requires a successor such
as `snake.v2`, never a redefinition of `snake.v1`.

Future profile names primarily describe Care Keeper workflow/capability semantics, not taxonomic
rank. A broad profile can serve several taxonomic subgroups with genuinely compatible workflows.
`amphibian.v1` may initially serve compatible taxa under Amphibia; materially different future
Frog/Salamander behavior can justify separate versioned profiles. Do not pre-create a profile for
every order or common name. This naming policy does not change the existing trusted profile model.

### Lifecycle and group mapping

The application-owned registry separates:

- **Read support:** all identities the release can replay/render, including historical profiles.
- **Registration eligibility:** the explicit subset permitted for new Animals.
- **Registration default:** exactly one eligible default per enabled workflow group. Ordinary
  Add Animal shows one group choice and resolves its default; any supported advanced version
  choice must have a distinct label. Commands validate eligibility as well as read support.

For example, `snake.v1` remains readable when new Snake registration defaults to `snake.v2`.
Existing Animals keep their persisted profile forever; editing taxonomy never upgrades it.
Removing registration eligibility does not remove read support or change a profile's meaning.
Their edit, action, reminder, analytics and replay paths use that exact historical profile,
not today's registration policy. Historical events are not revalidated against current eligibility.

X1 owns stable workflow-group metadata, exact profile-to-group membership, trusted presentation,
read support, eligibility and defaults. It implements no provider IDs, ancestry, taxonomy archive,
generations, Natural History, new Care Guides or Amphibian profile. X2 separately owns qualified
taxon-to-workflow-group mappings under ADR-0046. Biological classification cannot automatically
grant application capabilities. A reference taxon may have no registerable group; a group may be
disabled; a readable profile may be ineligible for registration. Historical mapping validation uses
the retained version-specific contract, not today's registration choices.

### Completed registration retries

A completed registration operation retains its resolved profile/default and original result.
An identical request retried under the same idempotency key after a default change returns that
original Animal and response. Resolve the stored operation before applying today's default;
do not recompute its command identity using the new default, rewrite stored hashes or turn a
previous success into a conflict. A changed request under the same key still conflicts under
[ADR-0012](0012-command-idempotency.md). New operations alone use today's eligibility/default.

### Supported-profile release manifest and startup

Extend the [ADR-0033 release matrix](0033-release-compatibility-matrix.md) with readable profile
identities, eligible/default identities, writable registration contract per identity, and required
extensible identities embedded in otherwise-known contracts (including taxon-link group keys).
Each such contract has a version-specific identity extractor/validator. Registration v1 implies
`snake.v1`; v2 combines persisted type/version, without substituting today's default.

Before mutable engine initialization, normal traffic or replay, conservatively scan all persisted
events, including corrected/voided history, for unknown type/version pairs **and** unsupported
required identities. Malformed identities or failed inspection also fail closed. Recovery mode
reports the offending contract/profile and compatible-release requirement through operator
diagnostics, with safe public wording. No partial normal startup or later deserialization crash
is an acceptable compatibility result. Projection/schema checks remain independently required.

The required startup sequence for existing storage is: read-only inspection → schema/Alembic
compatibility → event-contract compatibility → required embedded profile identities → projection
catalog → X2 active-reference structures when present → X3 selected-content/publication structures
when present → mutable engine initialization, replay/catch-up, generation-state changes, schedulers,
workers, job claiming and traffic. X1 supplies extension points, not unimplemented X2/X3 validators.
Initial database creation and explicit migrations are separately authorized workflows.

At the reconciled baseline, `build_application` calls `create_sqlite_engine` before compatibility
inspection; that factory applies mutable SQLite setup. The sequence above is a future X1 contract,
not a claim that current startup already satisfies it.

### Downgrade barrier

A new identity must never be written solely inside a contract pair understood by an older binary
that cannot validate that identity. **X4 introduces `animal.registered` schema v3**, carrying an
explicit `capability_profile` identity replacing the v2 type/version pair, plus the other existing
registration facts. It is introduced with
`amphibian.v1`, not made readable in the pre-Amphibian release. Historical v1/v2 remain readable
and unchanged. The prior binary's existing unknown-event-contract scan therefore rejects the v3
registration before normal operation; the new binary additionally checks its embedded identity.
The release manifest binds profile write eligibility to this barrier. Future unreadable identity
additions require a new contract version at their release boundary wherever an older binary's
identity scan cannot enforce rejection. A new metadata field that older code ignores is insufficient.

X4 also versions `animal.taxon_linked` as v2 for the expanded group validator; its four-group v1
decoder remains unchanged. The new validator checks the link group against the Animal's persisted
profile and qualified taxonomy mapping, without changing the registered profile. Read/write
manifests and embedded-identity extractors cover both registration v3 and taxon-link v2.

After the first older-unreadable fact is written, normal binary downgrade is prohibited under
[ADR-0026](0026-migration-and-rollback.md). Do not remove the barrier, rewrite registration or
strip events to enable downgrade. Recovery follows that ADR's restore/RPO rules. This event barrier
does not itself require Alembic; any independent relational evolution has its own compatibility gate.
X1 expects no Alembic migration, but embedded identities, event contracts, projection requirements
and runtime formats can still make an older binary unsafe. X1 must deliberately reject unsupported
embedded profiles. Registration v3, expanded taxon-link v2 and Amphibians remain X4 work.

## Qualification and consequences

`AT-CAPREG-01` verifies retained four-profile meaning, existing-Animal edit/actions/reminders/
analytics/replay after registration ineligibility, one group default, distinct version choices,
completed retries across default changes, changed-request conflicts and known-contract/unknown-
identity rejection before mutable startup. `AT-PRODCOMP-01` additionally reconstructs real Animals
and runs the applicable actual rollback binary; a scanner-only fixture is insufficient.
`AT-AMPH-01` and `AT-PRODCOMP-01` qualify current pre-Amphibian release → upgrade → create
`amphibian.v1` → start the actual older binary: intentional restricted recovery, no normal traffic,
replay or writes. Test every declared downgrade target, not a mocked replacement scanner.
See the [controlling plan](../plans/2026-10-01-extensible-animal-and-species-platform.md).
