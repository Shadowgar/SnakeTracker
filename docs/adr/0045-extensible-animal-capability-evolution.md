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
- **Registration default:** exactly one eligible default per enabled biological group. Ordinary
  Add Animal shows one group choice and resolves its default; any supported advanced version
  choice must have a distinct label. Commands validate eligibility as well as read support.

For example, `snake.v1` remains readable when new Snake registration defaults to `snake.v2`.
Existing Animals keep their persisted profile forever; editing taxonomy never upgrades it.
Removing registration eligibility does not remove read support or change a profile's meaning.

A trusted group mapping interface relates provider ancestry to Care Keeper biological group keys,
then to eligible/default profiles. Provider namespace/ancestor IDs are qualified adapter data;
free text, a matching name, and mere existence in the taxonomy tree cannot select a profile.
Historical event validation uses retained versioned mappings, rather than today's registration
eligibility. Reference taxonomy may include ancestors and groups with no eligible Animal profile.

### Supported-profile release manifest and startup

Extend the [ADR-0033 release matrix](0033-release-compatibility-matrix.md) with readable profile
identities, eligible/default identities, writable registration contract per identity, and required
extensible identities embedded in otherwise-known contracts (including taxon-link group keys).
Each such contract has a version-specific identity extractor/validator. Registration v1 implies
`snake.v1`; v2 combines persisted type/version, without substituting today's default.

Before normal traffic, mutable startup work or replay serving, conservatively scan all persisted
events, including corrected/voided history, for unknown type/version pairs **and** unsupported
required identities. Malformed identities or failed inspection also fail closed. Recovery mode
reports the offending contract/profile and compatible-release requirement through operator
diagnostics, with safe public wording. No partial normal startup or later deserialization crash
is an acceptable compatibility result. Projection/schema checks remain independently required.

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

## Qualification and consequences

`AT-CAPREG-01` verifies retained four-profile meaning, read-only historical eligibility, one group
default, distinct version choices, and known-contract/unknown-identity startup rejection.
`AT-AMPH-01` and `AT-PRODCOMP-01` qualify current pre-Amphibian release → upgrade → create
`amphibian.v1` → start the actual older binary: intentional restricted recovery, no normal traffic,
replay or writes. Test every declared downgrade target, not a mocked replacement scanner.
See the [controlling plan](../plans/2026-10-01-extensible-animal-and-species-platform.md).
