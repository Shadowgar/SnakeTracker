# M6.6 requirement and acceptance audit — November 8, 2026

**M6.6 IMPLEMENTED AND DEPLOYED — FINAL OWNER ACCEPTANCE PENDING.** The deployed
application is qualified at the bounded scope recorded below. This status does not
claim that the separately required full taxonomy archive qualification is complete,
that unpublished content is available, or that the owner accepted the milestone.

This audit covers every checkbox in the frozen [M6.6 milestone](../../roadmap/milestones.md#phase-66--m66--species-aware-husbandry-and-bioactive-care),
including its pre-C extension, and all requirements R-086–R-103 in the
[traceability matrix](../../requirements/traceability-matrix.md). Row suffixes identify
checkbox order within each tranche; they do not introduce new requirements. Frozen
documents and their historical status text remain unchanged. Later receipts establish
implementation and deployment; they cannot retroactively create an owner acceptance.

Classification:

- **C — Completed and supported by evidence.** Technical completion unless an explicit
  acceptance record is identified; C is not a claim of standalone tranche acceptance.
- **M — Implemented but awaiting manual acceptance.** Existing automated checks remain
  valid; actual iPhone/VoiceOver checks or required owner presentation review remain.
- **O — Awaiting an explicit owner decision.** No approval or publication is inferred.
- **I — Unimplemented or genuinely incomplete.** Required work/evidence remains absent.
- **D — Explicitly deferred through an existing valid decision.** Only the cited scope
  is deferred; this classification cannot waive another requirement.

## Frozen checkbox coverage

| Checkbox; requirement / acceptance test | Class | Evidence and exact remaining boundary |
| --- | --- | --- |
| A-1; R-086 / AT-SPDIR-01 — five-group common/scientific/synonym search, filtering, owned taxon IDs and provenance | C | [A qualification](../m6.6-species-aware-husbandry/a-universal-directory/README.md) records normalized identity/search; [X2](../x2-local-taxonomy/README.md) adds durable catalog/overlay and bounded local search. A's separate owner acceptance remains O below. |
| A-2; R-087 / AT-SPDIR-02 — accessible Add/Edit prediction and manual entry during provider/network/quota/malformed/no-result failure | C | [A](../m6.6-species-aware-husbandry/a-universal-directory/README.md) records keyboard combobox/provider-failure checks; [accepted B corrections](../m6.6-species-aware-husbandry/b-corrections/README.md) establish Spider/no-result and explicit linking. Actual iPhone/VoiceOver acceptance of the current release remains M below. |
| A-3; R-087 / AT-SPDIR-02 — optional morph/genetics, no inference, explicit same-household/same-taxon prior-value reuse | C | [A architecture/behavior evidence](../m6.6-species-aware-husbandry/a-universal-directory/README.md#architecture-and-behavior) records individual free-text facts and explicitly selected reuse; taxonomy selection does not manufacture them. |
| A-4; R-088 / AT-SPDIR-03 — explicit immutable same-household legacy taxon changes, no history rewrite or fuzzy matching | C | [A](../m6.6-species-aware-husbandry/a-universal-directory/README.md) and [accepted B](../m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance) cover link/change semantics and manual legacy workflows. |
| A-5; R-089 / AT-SPDIR-04 — enclosure plant identity/label/quantity/date/notes, immutable lifecycle, attributed local imagery and placeholder | C | [A](../m6.6-species-aware-husbandry/a-universal-directory/README.md), [D lifecycle/removal corrections](../m6.6-species-aware-husbandry/d-bioactive-plant-care/README.md), and [November 8 live Plant Detail correction](../roadmap-continuation-20261107/production-retry-20261108.md) establish delivery. Historical watering deferral was to D and is now delivered. The annotated Swiss Cheese Plant image remains a separate content-suitability decision, not a failed layout fix. |
| A-6; R-090 / AT-SPDIR-05 — privacy, bounds, timeouts/quota, provenance/rights, stale fallback, CSP, offline reads and release-keyed PWA caches | C | [A provider/cache evidence](../m6.6-species-aware-husbandry/a-universal-directory/README.md), [accepted B local-read evidence](../m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance), and [current PWA/assets smoke](../roadmap-continuation-20261107/production-retry-20261108.md). No new provider acquisition or tests were run for this audit. |
| A-7; R-090 / AT-SPDIR-05 — opt-in approved local species image, checksum/bounds, self-only CSP and personal-photo priority | C | [A image evidence](../m6.6-species-aware-husbandry/a-universal-directory/README.md) retains creator/source/license and personal-photo priority. Its documented later owner-confirmed noncommercial license policy does not remove attribution or authorize an arbitrary replacement. |
| OPS-A-1 — deployment-authorized read-only Overview, Accounts, Households, Animal/Enclosure/Inventory support, Event Inspector, Incident Explorer, System Health and Admin Audit | C | Explicitly accepted September 27 in the [OPS-A owner record](../m6.6-species-aware-husbandry/ops-a-platform-admin/approvals/2026-09-27-owner-acceptance.md); no mutation capability is included. |
| OPS-A-2 — production configuration, readability/build SHA, isolated qualification, encrypted backup and live data integrity | C | Same [September 27 acceptance](../m6.6-species-aware-husbandry/ops-a-platform-admin/approvals/2026-09-27-owner-acceptance.md), with 698 tests and preserved live business data. Later release checks supplement rather than erase this acceptance. |
| B-1; R-091 / AT-CAREGUIDE-01 — versioned Animal/plant values/ranges/units, sources/provider IDs, retrieval/review dates, support/disagreement and non-authority | C | Explicitly **Accepted / Complete October 5**, [B owner acceptance](../m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance). Versioned references remain subordinate to keeper facts. |
| B-2; R-095, R-096, delivered B portions of R-102/R-103 / AT-SPDIR-MANUAL-01, AT-MEASURE-01, AT-PRODCOMP-01, AT-PROFILE-REF-01 — manual/linking, reviewed Boa constrictor guide, exact length v2/mixed consumers, local reads and preservation | C | Same [October 5 acceptance](../m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance) and [consumer/compatibility evidence](../m6.6-species-aware-husbandry/b-corrections/README.md). This does not accept future X1–X5 extensions of R-102/R-103. |
| B-3 — compact Overview; Guides & Species Reference after Care; identity/taxonomy/At-a-Glance, expanded complete facts and provenance | C | [Accepted B reference-density evidence](../m6.6-species-aware-husbandry/b-corrections/compact-species-reference/README.md). B's then-limited Natural History description is historical; X3 functionality subsequently delivered without inventing production prose. |
| X1; R-097, R-102 / AT-CAPREG-01, AT-PRODCOMP-01 — frozen four profiles, eligibility/defaults/retries, original-version usability, presentation, test-only Dog/Fish/colony extension, pre-mutable compatibility/reconstruction, actual rollback binary and ordinary-worker backup | C | [Retained X1 qualification extract below](#retained-x1-qualification-and-integration) binds PR #22's 1,195-test gate and explicitly reused 84/84 browser, actual replay/binary and ordinary-worker recovery evidence. [November 8](../roadmap-continuation-20261107/production-retry-20261108.md) supplies later deployed normal-worker backup/restore at current dataset size. Standalone implementation acceptance is not inferred from architecture approval or merge. |
| X2 foundation; R-098, R-099, R-102 / AT-TAXBAS-01, AT-PRODCOMP-01 — separate FK-preserving migration, permanent UUIDs, names/classification/provenance/mapping, generations/durable overlay/fallback, rollback/cleanup preservation and reference-only taxa | C | [X2 development qualification](../x2-local-taxonomy/README.md) covers isolated migration, identity/concurrency, source selection, local search and generation lifecycle. Schema 24/25 migration and preservation were deployed November 2; later [release history](release-history.md) carries them forward. This does not qualify a real full archive. |
| X2 production import/qualification; R-098, R-102 / AT-TAXBAS-01, AT-PRODCOMP-01 — actual archive intended use/provenance/rights and production-sized Pi search, database/generation/index/WAL, backup scratch/memory/duration, restore/replay and normal-duty impact | I | [X2 receipt](../x2-local-taxonomy/README.md) expressly limits its 10,001-row Pi measurement to synthetic development evidence and preserves the full-archive gates. No actual-archive qualification exists in the reviewed release evidence. [Scope decision](content-decisions.md#x2-full-taxonomy-archive) is O; a proposed deferral is not an existing valid deferral. |
| Conditional job/provider prerequisite; R-099 / AT-TAXOVER-01 — typed SQLite claiming/leases/payload/handlers/retries and shared aggregate provider transport before a second queued workload | D | [Controlling plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md#production-import-jobsprovider-and-complexity-gates) explicitly permits bounded operator import and defers general job expansion until needed. [X2](../x2-local-taxonomy/README.md#offline-operator-workflow) uses no queue; [X3](../../operations/natural-history.md) uses explicit operator retention/publication. No second queued enrichment workload is delivered or claimed. This conditional deferral ends before introducing one; it does not claim the future queue/aggregate-transport extension implemented. |
| X3; R-099, R-100, R-102, R-103 / AT-TAXOVER-01, AT-NATHIST-01, AT-PROFILE-REF-01, AT-PRODCOMP-01 — additive migration, UUID source associations/versions/publication/withdrawal, rights/provenance, immutable-guide coexistence, actual-origin deduplication, reference-only taxa, generation independence/local reads, Boa imperator 539399 without a guide | C | [X3 acceptance map](../m6.6-species-aware-husbandry/x3-natural-history/README.md#acceptance-map) covers those behaviors and the exact Boa case, actual prior-binary rejection and isolated upgrade/restore. Its licensed prose is explicitly a development fixture, excluded from production; production rights/publication and the required tranche acceptance remain separate O items. |
| X4; R-097, R-101, R-102 / AT-AMPH-01, AT-PRODCOMP-01 — amphibian.v1, qualified Amphibia ancestry, exact Frog matrix/exclusions, registration v3, actual older-binary rejection, distinct fallback/cross-profile browser | C | [X4 qualification](../m6.6-species-aware-husbandry/x4-amphibian/README.md) records exact capability exclusions, five-profile lifecycle/browser checks and real old web/worker refusal. The earlier X1 unknown-image fallback mismatch was corrected here; it is not an outstanding deferral. Deployment does not establish standalone X4 owner acceptance. |
| X5; R-101, R-102 / AT-AMPHREF-01, AT-PRODCOMP-01 — representative sourced taxon-specific Frog guides and mobile/desktop owner review | M | [X5](../m6.6-species-aware-husbandry/x5-amphibian-reference/README.md) qualifies the exact two-guide bundle, schema 26, strict species identity, actual SQLite/old-binary/recovery and nine browser cases. Owner source/presentation and actual-device review remain; production import is separately O in [content decisions](content-decisions.md#two-frog-care-guides). Unpublished guides are not represented as live content. |
| C; R-092 / AT-SMARTCARE-01 — supported species/life-stage suggestions, honest labels, explicit keeper confirmation and Today/Calendar/reminder authority | M | [C qualification](../m6.6-species-aware-husbandry/c-smart-care-setup/README.md), [integrated precision/concurrency evidence](../m6.6-species-aware-husbandry/e-final-qualification/README.md), PR #33 corrections and [current live receipt](../roadmap-continuation-20261107/production-retry-20261108.md) establish implementation/deployment. Actual-device and VoiceOver checks remain. Guided choices cover reviewed feeding interval/frequency claims only; unsupported tasks/missing guidance stay manual, skip/decline are visit-only, existing schedules require explicit replacement confirmation. |
| D; R-093 / AT-BIOACTIVE-01 — enclosure-owned mode surviving Animal moves, independent watering/maintenance/cleaning, reference/default/override distinctions and correction-safe history | M | [D qualification](../m6.6-species-aware-husbandry/d-bioactive-plant-care/README.md) covers two independent plant schedules, movement, correction/void/reinstate, removal/delivery suppression, precise previews, actual SQLite migration and old-binary refusal; [Plant Detail fix](../roadmap-continuation-20261107/production-retry-20261108.md) is live. Intervals remain keeper-entered; pot-grown guidance does not assert reptile safety or an enclosure watering interval. Actual-device/VoiceOver review remains. |
| E; R-094 / AT-M66-QUAL-01 — compatibility/provider/migration/replay/auth/privacy/security/browser/a11y/performance/backup/live-data and owner review before explicit milestone acceptance | M | [Consolidated candidate evidence](../m6.6-species-aware-husbandry/e-final-qualification/README.md), [release history](release-history.md) and the exact accepted 1,719-test/ARM64 qualification reused November 8 support delivered technical scope. Manual evidence remains pending; X2 production-scale qualification remains I above and consolidated owner acceptance remains O below. No full-suite rerun, repeated browser pass or fresh production probe is claimed. |

## Acceptance authority and remaining decisions

| Acceptance or scope item | Class | Verified authority / remaining action |
| --- | --- | --- |
| Standalone M6.6-A acceptance | O | [A record](../m6.6-species-aware-husbandry/a-universal-directory/README.md) says “implementation-qualified September 14, 2026; owner review pending.” PR #14 integration and ADR-0043's September 26 Accepted status do not supply the missing milestone acceptance. The owner must supply a preserved approval or explicitly dispose of A in consolidated acceptance; do not invent a historical date. |
| M6.6-OPS-A acceptance | C | [September 27 record](../m6.6-species-aware-husbandry/ops-a-platform-admin/approvals/2026-09-27-owner-acceptance.md): explicit owner acceptance after live visual review, source `f8c429562c2b38ca29ba8ecf6a48b81426a51059`, PR #16. Its scope is read-only OPS-A only. |
| M6.6-B acceptance | C | [Owner Acceptance section](../m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance): “M6.6-B Accepted / Complete,” October 5, 2026, accepted source `04364cc4cad6c600dc167f32f4a9099b84667e98`; authority is the owner's explicit final acceptance/merge/source-synchronization instruction. The separate owner exception for verified GitGuardian SHA-256 false positives is preserved as an exception, not relabeled a passed scan. Earlier September review stops do not negate this later acceptance. |
| Pre-X1 documentation reconciliation / X1 architecture amendment | C | [October 5 documentation direction](../m6.6-species-aware-husbandry/README.md#pre-x1-documentation-direction), subsequently bounded October 8, and [October 16 exact-content architecture approval](../x1-capability-foundation/2026-10-16-owner-approval.md) are actual approvals of their stated documents. The latter explicitly “does not itself establish qualification, milestone acceptance, or production readiness.” ADR-0045/0046/0047 remain Proposed. |
| X1–X5 tranche and pre-C acceptance sequence | O | The frozen plan requires explicit tranche review and applicable import/publication gates. Technical qualification, normal merges and authorized deployment are established separately; no standalone approval record located in this audit warrants marking all extension acceptance boxes complete. Consolidated owner disposition must address that sequence and unmet gates rather than infer approval from downstream C/D delivery. |
| Current iPhone, keyboard and VoiceOver acceptance | M | [Practical checklist](manual-acceptance.md) covers current Animal/Enclosure/Directory/Guide/Smart Care/Plant navigation, labels, focus/order, photos/attribution and history. Automated Chromium/axe results already passed; real-device and screen-reader results are not yet recorded. |
| Exact Frog Guide publication | O | [Content decision](content-decisions.md#two-frog-care-guides): only Pelodryas caerulea and Ceratophrys cranwelli, two versions/five sources/42 claims. Separate explicit publication authorization and qualified exact live taxa are required; neither deployment nor milestone acceptance imports them. |
| Full-archive requirement disposition | O | The frozen requirement remains I. Recommend explicitly approving a bounded scope deferral through normal roadmap governance if the deployed catalog is sufficient; otherwise retain the blocker and authorize separate qualification. No deferral is enacted here. |
| Natural History production prose | O | [Content decision](content-decisions.md#x3-natural-history): implemented X3 versus unpublished development Boa fixture. Recommend keeping development prose unpublished and explicitly disposing of applicable production-content acceptance gates. Additional production content requires exact source/revision/rights qualification; owner approval cannot substitute for missing rights evidence. |
| Consolidated M6.6 acceptance | O | No existing record accepts the whole milestone. Required manual evidence, A/extension acceptance disposition and mandatory archive/publication-gate dispositions must precede an explicit owner acceptance. |
| OPS-B mutation tools | D | [September 27 OPS-A acceptance](../m6.6-species-aware-husbandry/ops-a-platform-admin/approvals/2026-09-27-owner-acceptance.md) explicitly defers Support Notes, session revocation, account disable/reactivation, password-reset actions, job retry, projection rebuild, business correction tools, image refresh and impersonation. |
| Speculative expansion | D | The [controlling plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md#production-import-jobsprovider-and-complexity-gates) already defers general job expansion until needed, Natural History prose FTS, extra providers, mass enrichment, speculative profiles and measurement-unjustified streaming backup. This does not defer full-archive qualification. |

The historical 16 MiB backup scratch concern is not reopened as an assumed current
failure: X1's ordinary-worker qualification and the November 8 supported-worker
backup plus isolated restore provide later positive evidence for the bounded deployed
dataset. They do not establish full-archive capacity or complete M7/M8 off-device,
key-recovery and formal storage qualification. The annotated plant asset needs a
separate qualified content replacement if requested; it does not invalidate the
verified bounded Plant Detail layout. No unrelated security or M9 work is a new
M6.6 implementation prerequisite in this audit.

## Retained X1 qualification and integration

X1's final report is retained in the shared workspace, not the historical evidence
folder referenced by the frozen matrix. This extract supplies its exact identity
without treating a stale path or architecture approval as a test result.

- `output/x1-final-qualification-20261016/REPORT.md`, SHA-256
  `9e6541ae7dadfc8f26d518894dde956bce3ca170e14b0e0c08576db7d14c7b17`:
  published head `8e9522ee22af6f5a6cbbaf114a2a970661fbf0de`, tree
  `e1d0d4dfe1171e4f284a8d45178a2f158568ba77`. [Quality run 38865603689](https://github.com/Shadowgar/SnakeTracker/actions/runs/38865603689)
  passed 1,195 tests, 94.61% lines / 85.55% branches; [Container run 38865603688](https://github.com/Shadowgar/SnakeTracker/actions/runs/38865603688),
  GitGuardian and exact-head Codex review passed. The report explicitly reuses the
  owner's retained 84/84 desktop/mobile result, wheel-to-wheel replay/rollback at
  cutoff 652, and ordinary-worker backup/restore preserving 652 events and 20
  attachment versions on SQLite 3.53.1 and native 3.40.1. Failed later local runs
  remain failed; none is counted as the passing 84/84 run.
- `output/x1-merge-20261017/REPORT.md`, SHA-256
  `441d4f32380e195e87fa513df9426fa619181ed0d16a4aaea27d57f8c72695f3`:
  [PR #22](https://github.com/Shadowgar/SnakeTracker/pull/22) merged normally as
  `a6dc77242a4066864dbe1d72c50b76690a9a1b7e`, approved second parent `8e9522e…`,
  unchanged first parent `8ba5a03ee9bc76fc26fc9ed109471b90cda5f18e`, identical tree.
  It records integration and explicitly leaves production deployment acceptance
  pending at that time; it is not standalone milestone acceptance.
- `output/production-go-live-20261102/REPORT.md`, SHA-256
  `2da7dbf78b2ff5936350e43305eb43facf47b57a9e9c49e41ca85f54c8eb0bb7`:
  subsequent owner-authorized production deployment reached schema 25, preserved
  89 pre-existing data tables, 35 protected inventories, 1,051 events and all 46
  attachment versions, and performed no full taxonomy import or development
  Natural History publication. [November 8's later receipt](../roadmap-continuation-20261107/production-retry-20261108.md)
  establishes the current schema-27 deployed source and fresh supported-worker
  recovery point. These remain dated evidence, not new checks performed here.

No tests, provider requests, content import, deployment, production writes or
milestone approval were performed to prepare this audit.
