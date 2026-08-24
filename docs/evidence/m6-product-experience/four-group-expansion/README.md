# Four-Group Capability Extension Evidence

Status: **implementation-qualified on the promoted Raspberry Pi 5; M6 owner acceptance remains pending**

Qualified: August 24, 2026

[ADR-0041](../../../adr/0041-four-group-capability-expansion-and-neutral-molt-contracts.md)
extends the trusted Animal capability registry to Snake, Spider, Lizard, and Scorpion. It does not
reinterpret the accepted M5.5 record: historical Spider molt/premolt schema v1 remains supported
exactly as stored, while new Spider and Scorpion writes use the capability-neutral schema v2.

## Approved profiles and contract boundary

| Profile | Care | Reminders | Analytics |
|---|---|---|---|
| `snake.v1` | Feeding, weight, length, shed, bath | Feeding, weight, length, bath, cleaning, water | Feeding, weight, length, shed |
| `spider.v1` | Feeding, weight, molt, premolt, misting | Feeding, weight, molt, misting, cleaning, water | Feeding, weight, molt |
| `lizard.v1` | Feeding, weight, length, bath, misting | Feeding, weight, length, bath, misting, cleaning, water | Feeding, weight, length |
| `scorpion.v1` | Feeding, weight, molt, premolt, misting | Feeding, weight, molt, misting, cleaning, water | Feeding, weight, molt |

The profile registry is the single applicability boundary. Species text does not select care
behavior, and no EAV model, plugin framework, or duplicated household subsystem was added.
`lizard.v1` deliberately has no shed capability. `scorpion.v1` deliberately has no length, shed,
or bath capability.

The registry deserializes schema-v1 and schema-v2 molt/premolt contracts as distinct typed
identities. New molt, molt-correction, and premolt commands write schema v2. Compatibility tests
cover v1 and v2 together through aggregate replay, effective corrections, reminders, timelines,
reports, search, analytics, backup/restore, and deterministic projection rebuild. The existing
event-envelope schema already supports this evolution, so no database migration was added.

## Correctness qualification

- A one-time reminder override is consumed by the latest qualifying effective care event at or
  after the override. The regression fixture with an August 11 override, accepted feeding on
  August 16, and five-day interval produces August 21; correction, void, and reinstatement replay
  deterministically.
- Standalone reminder forms derive options separately for every Animal or enclosure subject.
- Animal profile corrections retain immutable type/profile identity in the household-scoped FTS5
  document.
- Browser tests cover four-group registration, profile actions, mixed collection, enclosure moves,
  care, corrections, reminders, reports, search, analytics, photos, and household isolation.
- Native ARM64 Chromium 151 exercised ten affected routes in 14 mobile/desktop viewport checks.
  It reported zero console warnings or errors, horizontal overflows, duplicate IDs, missing image
  alt attributes, unlabeled controls, or pages without exactly one primary heading.
- Migration qualification passed fresh upgrade, downgrade to `0010`, re-upgrade to
  `0011_product_experience`, projection rebuild, SQLite integrity, and foreign-key checks.
- The final repository suite passes 421 tests with 95.04% line coverage, 85.11% branch coverage,
  and 93.21% combined coverage. Formatting, lint, architecture boundaries/freeze, typing,
  documentation links, dependency locking, and strict `pip-audit` also pass.

## Deterministic owner-review household

The disposable reserved demo was explicitly replaced with scenario
`four-group-owner-review.v1`, as of August 24, 2026. The whole database was not reset.

| Measure | Qualified value |
|---|---:|
| Animals | 13 |
| Snakes / Spiders / Lizards / Scorpions | 4 / 3 / 3 / 3 |
| Enclosures | 11 |
| Domain events | 248 |
| Distinct 640×480 profile photos | 13 |

The fixture contains Juniper, Atlas, Nova, and Cedar (Snakes); Ember, Pip, and Pearl (Spiders);
Sol, Bramble, and Dune (Lizards); and Onyx, Cobalt, and Saffron (Scorpions). Ember, Juniper, Nova,
Onyx, Pearl, and Sol have prediction-ready histories. Bramble, Cobalt, and Pip intentionally have
insufficient histories. Onyx supplies seven schema-v2 molt/premolt facts, and all 21 new demo
molt/premolt facts are schema v2.

Direct analytics verification is more specific: Sol has a Lizard feeding estimate, while Bramble
and Dune remain below the feeding-estimate threshold. Onyx has both Scorpion feeding and molt
estimates, while Cobalt and Saffron remain below both estimate thresholds. Dune and Saffron retain
coherent care histories even though they are not designated sparse fixtures.

The reset accepts only the deterministic ADR-0040 demo household ID, retains its canonical
household/owner events and backup records, removes only disposable demo product streams,
projections, sessions, audit state, and attachments, then rebuilds the demo. Its regression test
proves that a shared database backup record and the separate real household survive exactly.

## Preservation and recovery evidence

Before the reset, a real-household backup completed as run
`bb68a3f7-3ffb-4141-a565-a3d5f4434056`; its manifest checksum is
`c4679c2a2ca571a3710a3bb3f32e7798775f21e53c7bc4a185ea13ce27828ad9`. A restore rehearsal to a
separate directory verified the database and all 13 attachments present in that pre-reset archive.

The real household was hashed immediately before and after the demo replacement. Counts remained
21 domain events, one Animal, two enclosures, one expense, two inventory balances, two reminder
rules, and one attachment. The exact matching hashes are:

- Event history: `d30fc149221a05a097aa9035fb2f0f4d83e66a64fc28cc62b01bebe5d66472bd`
- Core state: `196aeae39c7f1841532f8fdb136b79e16b3f9020341d6811d8f30e6c16b53e36`
- Identity and membership: `9d1a4036d1b6e657924f9845ee2ed6eaa82249438f414c56cf200d658b4409e2`
- Attachment content: `1b061498c023525ae3ced752a15b97d69f2433f80486aeab4ecd8cbc70820f38`

Live demo-session checks return 404 for the real Animal and attachment, exclude the real Animal
from collection and reports, and return no search match. Automated authorization fixtures cover
the inverse real-to-demo direction and all mutation boundaries.

## Promoted ARM64 runtime

The image is native `linux/arm64`, runs as non-root UID/GID 1001, and has digest
`sha256:255d912c9d4bbb36ff94b8155aab980457ab67882f333b5aa86b6df202c73c17`. Fresh-container startup
passed before promotion. The same image now runs healthy web and worker containers on a Raspberry
Pi 5 Model B; nginx is healthy and is the only Care Keeper listener, bound to
`127.0.0.1:8081`. `/health/ready` returns `{"status":"ready"}`.

This evidence qualifies the additive four-group extension and its ARM64 runtime only. Major M6 UX
redesign remains paused. M6 owner acceptance, remote/public deployment approval, M7 performance
qualification, and PR #8 are not complete.
