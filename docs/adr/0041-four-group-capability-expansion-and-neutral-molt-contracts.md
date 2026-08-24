# ADR-0041: Four-Group Capability Expansion and Neutral Molt Contracts

Status: Accepted
Acceptance date: 2026-08-24

## Context

ADR-0039 established trusted first-party Animal capability profiles and initially delivered
`snake.v1` and `spider.v1`. That architecture can add profiles without new aggregates, EAV data,
species rules, or a plugin framework. The next product scope adds Lizards and Scorpions, but the
stored schema-v1 molt and premolt contracts were explicitly defined as Spider facts. Reusing those
contracts for Scorpions would silently change historical meaning.

The existing snake shed contract also contains `blue_state`, so it is not a neutral reptile-shed
contract. Lizard support cannot safely inherit that behavior merely because lizards shed.

## Decision

Care Keeper registers four trusted version-1 profiles: `snake.v1`, `spider.v1`, `lizard.v1`, and
`scorpion.v1`. The capability profile—not species text or scattered animal-type conditionals—owns
the available commands, schedules, analytics, and presentation actions. Species remains
keeper-entered identity information and does not select husbandry rules.

The approved additions are:

| Profile | Care actions | Reminder kinds | Analytics |
|---|---|---|---|
| `lizard.v1` | Feeding, weight, length, bath/soak, misting | Feeding, weight, length, bath, misting, enclosure cleaning, water change | Feeding, weight, length |
| `scorpion.v1` | Feeding, weight, molt, premolt, misting | Feeding, weight, molt, misting, enclosure cleaning, water change | Feeding, weight, molt |

`lizard.v1` does not expose shed because the current shed contracts are snake-specific.
`scorpion.v1` does not expose length, shed, or bath/soak. Shared identity, lifecycle, photos,
attachments, enclosure assignment and rehousing, inventory-linked feeding, expenses, timeline,
reports, search, backup, and household authorization remain on their existing neutral boundaries.

## Molt and premolt contract evolution

`animal.molt_recorded` schema v1, `animal.molt_corrected` schema v1, and
`animal.premolt_observed` schema v1 remain historical Spider-only contracts exactly as recorded.
They are not rewritten, migrated, reinterpreted, or upcast.

Schema v2 contracts retain the event-type names and introduce capability-profile-neutral payload
semantics for a molt-capable Animal. All newly recorded Spider and Scorpion molt, correction, and
premolt events use schema v2. The event registry deserializes v1 and v2 as distinct typed contract
identities. Effective history, correction controls, reminders, timeline rendering, reports,
search, analytics, projection rebuilds, and backup/restore consume both versions side by side.

No relational migration is required: the event envelope already stores schema version and the
current Animal projection already stores registered profile identity.

## Reminder and search correctness

A one-time reminder due-date override represents the next occurrence only. If the latest
qualifying effective care event occurs at or after the override, that event consumes the override
and the next due date is the event time plus the recurring interval. Corrections, voids, and
reinstatements recompute the same result from effective history.

Standalone reminder creation derives allowed kinds from the trusted subject profile. Animal
profile corrections merge mutable profile fields with immutable registered type/profile identity
when rebuilding search documents, so a correction cannot erase the animal group.

## Demo and compatibility policy

The reserved fictional ADR-0040 household may be replaced by a four-group, reproducible owner
review fixture. The reset is an explicit local-only operation that targets only the deterministic
demo household, retains its trusted household identity, removes its disposable non-household
streams and derived state, rebuilds product projections, and leaves the real household unchanged.
A whole-database reset is prohibited.

Existing Snake and Spider streams remain release-blocking compatibility fixtures. In particular,
schema-v1 Spider molt/premolt replay must remain byte- and behavior-compatible while new Spider and
Scorpion streams prove schema-v2 recording and deterministic coexistence.

## Alternatives considered

- **Use Spider v1 molt payloads for Scorpions:** rejected because it reinterprets an accepted
  historical contract.
- **Upcast v1 molt events to v2:** rejected because v1 is valid, supported historical meaning, not
  malformed legacy input.
- **Reuse snake shed for Lizards:** rejected because `blue_state` encodes snake-specific semantics.
- **Branch throughout the application on animal type or species:** rejected because it violates the
  trusted capability boundary and would make future profiles unsafe.
- **Add an EAV model or general plugin system:** rejected as unnecessary scope and weaker typing.

## Consequences and governance

The application carries three additive schema-v2 molt/premolt payload classes and dual-version
consumers. Capability and compatibility matrices expand to four profiles. Current authoritative
architecture, roadmap, requirements, fixture, and qualification documents record this extension;
accepted M5.5 evidence remains historical and is not rewritten.

This decision amends ADR-0039's initial allocation without superseding its aggregate, registry,
authorization, and fail-safe rules. It also preserves ADR-0005, ADR-0006, ADR-0033, ADR-0038, and
ADR-0040. It does not authorize the deferred M6 UX redesign, M6 owner acceptance, PR #8 merge, or
M7 work.
