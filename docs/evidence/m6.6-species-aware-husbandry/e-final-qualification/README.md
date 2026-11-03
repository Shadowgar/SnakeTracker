# November 3 release candidate — owner decision

This is isolated development qualification for X5, M6.6-C and M6.6-D. It does not mark M6.6, M7 or M8 complete, accept Proposed ADRs, or record production availability. Production services, data, backups and content were not changed.

## What keepers can do

- Read reviewed amphibian care before an empty Natural History section on mobile, with the Animal photograph, cautions and provenance retained.
- Open optional Smart care setup from Animal Care; choose applicable reviewed feeding guidance, adjust a schedule, preview its effect and explicitly confirm. Missing or unsuitable guidance retains manual setup across the registered profiles. Existing schedules remain authoritative until confirmation.
- Mark an enclosure bioactive, configure separate plant-watering and enclosure-maintenance schedules, record care and correct its history. Plants, mode and maintenance stay with the enclosure when animals move. Removed plants retain history but stop future tasks and notification delivery.

The implemented paths use existing Today, Calendar, reminders, immutable history and household boundaries. User-facing draft release notes accompany each tranche; publish them through the existing Updates/release-ledger mechanism only after verified deployment.

## Integration and evidence

Integration order is X5 PR #30 → Smart Care PR #31 → the dependent Bioactive PR (base `feat/m66c-smart-care-setup`). Each later PR explicitly targets its preceding branch. None is merged. The maintained execution checkpoint and PR descriptions identify exact submitted heads and hosted gate results.

| Area | Evidence and limit |
| --- | --- |
| X5 | [Bounded mobile qualification](../x5-amphibian-reference/README.md#mobile-completion), 21 focused tests, nine Chromium cases and six captures on 5e0e3f3. Unchanged source/runtime/recovery evidence explicitly retained from 382d9cc. |
| Smart Care | [Qualification](../c-smart-care-setup/README.md), focused security/retry/source/due tests and a complete real-browser journey with six representative captures. |
| Bioactive | [Qualification](../d-bioactive-plant-care/README.md), independent plant schedules, maintenance corrections, removal/notification suppression, populated migration preservation and actual older-binary refusal. |
| Required gates | Existing Quality (including coverage, architecture, links, audit), Container (AMD64/ARM64 and vulnerability scan) and GitGuardian remain unchanged. Exact-head results are recorded on each PR. Pending is not passing. |
| Accessibility and devices | Automated WCAG and overflow checks cover changed screens. Physical-device and screen-reader owner acceptance are outstanding. |
| Operations | Existing qualified recovery procedure is reused. No fresh production-sized archive, recovery exercise or production migration was run during development. A future deployment needs its approved current recovery point and live preservation checks. |

## Code and content proposed for a later deployment

The candidate includes the three stacked tranches and forward migrations `0026_amphibian_care_guides` and `0027_bioactive_plant_care`, from the owner's stated production schema `0025_natural_history`. No deployed migration history or PR #28 compatibility correction is rewritten. Smart Care itself adds no schema.

The X5 bundle is `reference/care-guides/reviewed-amphibians-v1.json`: two version-1 guides, White's tree frog (*Pelodryas caerulea*) and Cranwell's horned frog (*Ceratophrys cranwelli*), retaining their qualified source positions and contexts. Bundle SHA-256: `441e3d03e41072a4a307ae90b136adf3828fc18a2353f64b038cef6308839e66`. Existing bundles are unchanged. No C/D guidance bundle, generic Frog rule, inferred plant-watering interval or animal-safety claim is added.

Import is a separate explicit operator action against qualified exact taxa. Shipping code does not publish guides, populate missing Natural History or perform a full taxonomy archive import. Restricted reference publication, full taxonomy/archive qualification and applicable milestone prerequisites remain separate owner decisions.

Schema 27 prevents older binaries from starting mutably. Downgrading 27 is blocked after any retained mode/watering/correction history or plant-targeted reminder history, even disabled schedules. Schema 26 separately blocks downgrade after amphibian guides are retained. A historical restoration has a recovery-point/data-loss boundary; a binary rollback is not a substitute.

## Smallest owner decision

Review the submitted UX and source applicability, then decide whether to accept and integrate the stacked PRs in order. Separately authorize any migration, selected guide publication/import and deployment with the established recovery and preservation procedure. Until that authorization, all production operations and release-ledger publication remain pending.

Known limits: guided suggestions currently map reviewed feeding intervals/frequencies; other supported tasks use manual entry. Skip/decline are visit-only and explained as such. Plant intervals are keeper-entered. No sensors, cloud integration, mass enrichment, public profiles or future modules are included.

## Integrated source receipt

Source `fd7819601a28172a085dfdff82fa69f3a9b6ca49` contains final C source `fa52d569e9f6e1169a6997317dcc26e397e95113` and X5 `5e0e3f3ffeefd801b5345b6a13b2be139a9eef66`. The final D source adds atomic enclosure-history expectations and browser-valid datetime fields with exact retained instants. The C/D focused overlap passed 64 tests; static checks passed. Actual Chromium passed the three precise timestamp form round trips, using actual input values, native form submission and read-only SQLite oracles. [Precision results](precision-browser-results.json) identify the exact source.

The populated migration wrapper was rerun successfully on this integrated source with actual SQLite 3.40.1 and `trusted_schema=OFF`; its [raw log](../d-bioactive-plant-care/sqlite340.log) covers preservation, foreign keys, immutable triggers and blocked unsafe downgrade. The ordinary bioactive UI journey and seven screenshots remain attributed to 4fd8829, and unchanged X5/C evidence retains its original source attribution.

Required final hosted gates and independent delta dispositions are recorded against the submitted PR heads. This receipt records executed local/runtime/browser checks, not pending hosted passes or production approval.

The complete Smart Care real-browser journey was also rerun on integrated source fd781960: source choice, edit, confirmation, Today/Calendar/reminders, accepted feeding and updated due state all passed, with zero checked axe violations, overflow, external requests or page errors. [Integrated journey results](smart-care-browser-results.json). Layout captures from the earlier source are retained rather than adding a duplicate image collection.
