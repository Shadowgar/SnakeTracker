# X4 — Amphibian Expansion development qualification

Owner-authorized implementation from main `4d7d769b804cd2aebafa6d4fc901f5ca4e247c84`.
See the [owner directive](owner-directive.md) and [execution plan](../../../superpowers/plans/2026-10-25-x4-amphibian-expansion.md).
This is an implementation candidate for owner design review, not production deployment acceptance.
No production migration, import/publication, container restart or X5 work is included.

## What keepers can do

Add an Amphibian alongside the existing four groups. Save a photo and notes, assign/change its
enclosure, record observed feedings and precise measurements, use Inventory and expenses, choose
reminders, and review history/trends and linked species information. Initial Frog tracking reuses
the existing Animal and household systems. It never recommends a diet, interval or growth target.

| amphibian.v1 surface | Exact allocation |
| --- | --- |
| Capabilities | feeding, weight, length, enclosure_assignment, photos, notes, inventory, expenses, reminders, timeline |
| Care actions | feeding, weight, length |
| Reminder kinds | feeding, weight, length, cleaning, water_change |
| Analytics | feeding, weight, length |

Shed, bath/soak, molt/premolt and misting remain unavailable. Cleaning and water-change schedules
refer to the assigned enclosure's records. No aquatic-stage, metamorphosis or water-quality
workflows, new Care Guides or species-specific husbandry schedules are enabled.

## Identity and preservation

New Amphibians write `animal.registered` v3 with an explicit `capability_profile`. The four existing
profiles retain writable v2 and unchanged historical semantics. Registration v1/v2 and taxon-link
v1 remain readable; v2 cannot smuggle the new profile and v1 links remain limited to their original
four groups. Amphibian links use the separately validated `animal.taxon_linked` v2 contract.
Completed retries preserve original results across default/eligibility changes.

Qualified iNaturalist ancestry uses Amphibia 20978. Public identity checks also verified Anura 20979
and Rana temporaria 25591. Provider namespace and ancestry, not a common-name list, qualify the
mapping; higher Amphibia ranks and unqualified taxa stay reference-only. Selected accepted species
or subspecies can link to a compatible registered profile. Manual entry remains available offline.
See [source qualification](source-qualification.json). A taxonomy link does not change a profile.

No new relational migration is required: schema remains 0025. Existing permanent taxon UUIDs,
Animal/Plant/media references, source associations and historical immutable Care Guides remain
intact. The actual pre-X4 source at 4d7d769 is archived and executed by the compatibility test;
its web and worker startup reject new v3 facts before mutable initialization/normal operation.
Normal SQLite WAL/SHM bookkeeping is permitted under ADR-0045; the tests protect application
business data, event/media hashes and startup order rather than inventing a zero-sidecar guarantee.

## Acceptance map

| Requirement | Qualification |
| --- | --- |
| AT-AMPH-01 exact matrix/registry | test_x4_amphibian_contracts: exact sets, trusted default, versioned decoders/extractors, required identities, old-contract exclusion and manifests; X1 lifecycle regressions |
| AT-AMPH-01 shared workflows | test_x4_workflows: five groups, two households/private photos, cricket Inventory/outcomes, precise measurements, correction/void, immutable originals, notes, expenses, search/reports/trends, enclosure moves and reminders; excluded direct POSTs reject without writes |
| Biological identity/manual fallback | test_amphibian_taxonomy: provider ancestry, namespace/rank guard, malformed/conflicting lineage; test_amphibian_directory: reference-only/inactive/uncertain selection rejection; actual offline v2 link in compatibility fixture |
| AT-PRODCOMP-01 / historical compatibility | test_x4_registration and test_x4_compatibility: retained v1/v2/v3 facts and v1/v2 links, actual old web+worker restriction, replay, real encrypted backup/restore, media and X3 content hashes, unchanged schema |
| Deferred visual fallback | profile_fallback_visual shared by normal/admin consumers; admin query retains actual version, unknown future profile uses neutral art; distinct original Frog fallback and existing photo priority |
| Actual browser review | 390x844, 320x844, 1440x900 captures for Add Animal, Frog profile, feeding history, measurement history, Care, linked reference and all five groups; no page overflow or visible broken images; keyboard focus/selection, primary touch targets and reduced motion checked |

The existing PWA cache version advances so installed clients can receive the new palette/art.
The generated artwork is a group illustration, not photographic species-identification evidence.
A fictional preview additionally uses it as a keeper-uploaded image; Moss demonstrates the group
fallback and Fern demonstrates personal-image priority. Existing licensed images retain credits.

## Review and test results

Focused qualification passed: 93 domain/registry tests; 9 workflow/registration tests; 25 visual/admin
checks; 2 final admin/PWA cases; provider/archive batch 104 passes with one existing fixture-commit
timeout; focused directory guards; registration-history and due-reminder presenter regressions.
Ruff, formatting, mypy, architecture/freeze and documentation checks passed. Independent whole-branch
review found a missing v3 registration description; it was reproduced/fixed. Actual browser use
found the persisted `due` reminder/calendar bucket mismatch; the presentation fix is tested for Frog
and Snake across household-date boundaries and independently reviewed.

The one local full gate was stopped gracefully after repeated disposable SQLite setup/commit
stalls: 132 passed, 7 failed, 18m49s. One failure was the old exact-four-profile assertion, now changed
to require exactly the owner-approved five; the other six were 30-second timeouts. No timeout,
assertion threshold or coverage gate was weakened. See [local qualification](local-qualification.md).
Final complete qualification uses the unchanged hosted Quality/Container/security checks on the
PR head. Their results and exact SHA are recorded in the PR and delivery report.

## Visual evidence

| View | 390px | 320px | 1440px |
| --- | --- | --- | --- |
| Add Animal | [mobile](screenshots/add-animal-390-full.png) | [narrow](screenshots/add-animal-320-full.png) | [desktop](screenshots/add-animal-1440-full.png) |
| Frog profile | [mobile](screenshots/frog-profile-390-full.png) | [narrow](screenshots/frog-profile-320-full.png) | [desktop](screenshots/frog-profile-1440-full.png) |
| Feeding history | [mobile](screenshots/feeding-history-390-full.png) | [narrow](screenshots/feeding-history-320-full.png) | [desktop](screenshots/feeding-history-1440-full.png) |
| Measurements | [mobile](screenshots/measurement-history-390-full.png) | [narrow](screenshots/measurement-history-320-full.png) | [desktop](screenshots/measurement-history-1440-full.png) |
| Care/reminders | [mobile](screenshots/frog-care-390-full.png) | [narrow](screenshots/frog-care-320-full.png) | [desktop](screenshots/frog-care-1440-full.png) |
| Species reference | [mobile](screenshots/species-reference-390-full.png) | [narrow](screenshots/species-reference-320-full.png) | [desktop](screenshots/species-reference-1440-full.png) |
| Mixed groups | [mobile](screenshots/mixed-animals-390-full.png) | [narrow](screenshots/mixed-animals-320-full.png) | [desktop](screenshots/mixed-animals-1440-full.png) |

All screenshots use a disposable fictional household. Providers are disabled during ordinary
viewing; biological identity was acquired explicitly during fixture preparation. The 1/7-day
intervals are fictional keeper selections, not species recommendations. Source rights and
production content-publication restrictions from X3 remain unchanged. The earlier nonblocking
technical-wording polish remains a separate pre-production follow-up. The authorized unknown-profile
fallback mismatch is corrected here. PR #21 stays open. No production Updates entry was created;
[What's New wording](release-note-draft.md) is explicitly development-only.
