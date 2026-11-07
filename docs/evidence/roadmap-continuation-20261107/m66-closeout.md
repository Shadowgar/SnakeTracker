# M6.6 — current closeout and remaining owner acceptance

Status: November 7, 2026. Integrated functionality is deployed; **M6.6 final owner
acceptance remains pending**. This current-status note supplements historical
receipts without rewriting their dates, source attribution or architectural approvals.

The November 7 PR #34/#35 deployment attempt ended **ROLLED BACK — PRODUCTION
HEALTHY** at `2026-11-07T10:15:48.404552+00:00`. The previous source/image identified
below remains live. PR #34's Plant Detail correction is merged and qualified but
**not live**; a new attempt requires an owner decision. The
[incident receipt](production-rollback-20261107.md) records the operator check
failure, preserved data and recovery outcome. No milestone acceptance follows
from that rollback or the retained candidate qualification.

## Completed evidence to reuse

[PR #33](https://github.com/Shadowgar/SnakeTracker/pull/33) merged normally as
`71eb88c01390d3672c470c1a50a80e707233c181`. Its tree
`142752c8e58f72c0c2fe69a80aa95cd7e42c1eda` equals qualified application source
`8ebffb6287742f3aef5ad985ef99cf1036a3c623`, deployed in ARM64 image
`sha256:ab0ddd40f4d54db63b6945146e163a0431670a62e8a112c5b06a675c1c5818f4`.
Schema is `0027_bioactive_plant_care`. Production activation occurred November 4;
the completed live verification and truthful combined release entry were recorded
November 6, 2026, America/New_York.

The operator receipts are `output/combined-production-deploy-20261104/REPORT.md`
and `COMPLETE.json` in the shared repository workspace. They record 109 pre-existing
data tables preserved across migrations, 35 final protected-table comparisons,
event high-water 1,051 → 1,051, all 46 attachment versions preserved, and a verified
encrypted backup plus isolated restore. Follow-up live checks covered four existing
account memberships, ten Smart Care previews, seven enclosures, an existing plant,
reminder subject scoping, mobile navigation and PWA assets. The initial smoke 502
and subsequent successful checks remain recorded; they are not silently erased.

Reuse [X5](../m6.6-species-aware-husbandry/x5-amphibian-reference/README.md),
[Smart Care](../m6.6-species-aware-husbandry/c-smart-care-setup/README.md),
[Bioactive](../m6.6-species-aware-husbandry/d-bioactive-plant-care/README.md) and
[integrated qualification](../m6.6-species-aware-husbandry/e-final-qualification/README.md)
for their stated source revisions and scope. Their historical “not merged/deployed”
wording describes those earlier candidates, not the current release. The later
production receipt establishes deployment; it does not retroactively change an
earlier test's revision or create milestone acceptance.

## Only unfinished closeout items

| Item | Remaining evidence or owner decision |
| --- | --- |
| Plant Detail presentation defect | PR #34's bounded correction and regression are merged and qualified with PR #35, but the November 7 deployment attempt was rolled back. The defect remains live on the previous release. Correct and verify the operator configuration-comparison check, then obtain a new owner deployment decision; no retry is authorized by this note. |
| Physical device and screen reader | Walk the changed guide, Smart Care edit/preview/confirmation, plant and history screens on the owner's actual device and with a screen reader; record platform, focus/control names, errors and outcome. Chromium viewport and automated accessibility results do not substitute for this acceptance. Use isolated fixtures for deliberate business writes. |
| Frog Guide source/content publication | Decide the [exact two-guide publication proposal](frog-guide-publication.md). Code and presentation are live, but the reviewed guide content remains unpublished in the production receipt. Import requires separate explicit authorization and exact qualified taxa. |
| Full taxonomy archive and Natural History content | The bounded local catalog/provider overlay is deployed; production-sized full-archive source/rights/import/capacity qualification is still unperformed. Decide whether to require it for closeout or explicitly defer it through the existing governance process. X3 code is deployed, but development Natural History content has not been published. Neither import is authorized by this closeout. |
| Consolidated owner acceptance | Review the corrected UI, remaining device/accessibility evidence, content decision and documented product limits, then explicitly accept or retain open items. The [historical standalone M6.6-A acceptance gap](../m6.6-species-aware-husbandry/a-universal-directory/README.md) remains unverified; integration or an ADR status assertion cannot fabricate that owner record. Existing M6.6-B acceptance and all historical approvals remain unchanged. |

The annotated Swiss Cheese Plant asset is a content-suitability finding separate
from its layout defect: the cached near-square photograph contains Czech captions
and magenta annotations. Its creator/license/source provenance must remain intact;
any replacement requires the existing qualified acquisition process, not a remote
fetch during ordinary viewing. This note does not authorize a production replacement.

Known product limits remain explicit: guided feeding intervals/frequencies only;
manual setup for other supported care tasks or missing guidance; keeper-entered
plant-watering intervals; visit-only skip/decline; existing schedules change only
after explicit confirmation. No unsupported universal Frog guidance or automatic
plant/animal safety assertion is introduced.

M7/M8 formal storage, recovery and release-readiness limitations remain separate;
this closeout does not promote those milestones, Proposed ADRs or public sharing.
No unchanged feature suite, migration, production import or recovery operation was
repeated to write this note.
