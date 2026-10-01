# Extensible Animal and Species Platform — controlling implementation plan

Status: Owner-approved direction; implementation and owner acceptance pending (2026-10-01).
Scope: documentation only. This plan inserts bounded work after M6.6-B corrections and before
M6.6-C. No production migration, dataset import, deployment, or event rewrite is authorized here.

## Authority and intent

This plan adds the implementation sequence to the existing [roadmap](../roadmap/milestones.md) and
[traceability matrix](../requirements/traceability-matrix.md). It extends accepted
[ADR-0039](../adr/0039-multispecies-animal-capabilities.md),
[ADR-0041](../adr/0041-four-group-capability-expansion-and-neutral-molt-contracts.md), and
[ADR-0043](../adr/0043-universal-species-directory.md), plus proposed
[ADR-0044](../adr/0044-versioned-sourced-care-guides.md). New decisions are in
[ADR-0045](../adr/0045-extensible-animal-capability-evolution.md),
[ADR-0046](../adr/0046-local-taxonomy-snapshot-and-provider-overlay.md),
[ADR-0047](../adr/0047-natural-history-reference-boundary.md), and
[ADR-0048](../adr/0048-precise-animal-length-measurements.md). Event evolution, backup,
migration, compatibility, accessibility, and release governance remain under
[ADR-0005](../adr/0005-event-contracts-and-evolution.md),
[ADR-0018](../adr/0018-backup-and-restoration.md),
[ADR-0026](../adr/0026-migration-and-rollback.md),
[ADR-0028](../adr/0028-architecture-governance-and-decision-freeze.md),
[ADR-0033](../adr/0033-release-compatibility-matrix.md), and
[ADR-0034](../adr/0034-accessibility-and-ux.md). See the
[M5.5 plan](2026-08-11-phase-5-5-multispecies-foundation.md) and
[Care Guide source policy](../operations/care-guide-sources.md) for existing boundaries.

Care Keeper is live. The production database and attachments are irreplaceable household data.
**New capability profiles are additive. Existing versioned capability profiles retain their
historical semantics forever unless a deliberate, separately versioned successor is introduced.**
`snake.v1`, `spider.v1`, `lizard.v1`, and `scorpion.v1` retain their present meaning; an incompatible
Snake model becomes `snake.v2`, and existing Animals remain `snake.v1`. Registration v1 still means
`snake.v1`; Spider-only molt/premolt v1 and neutral v2 retain their distinct semantics. Unknown
profiles and event versions fail safely. No legacy event, taxon link, or registration species is
rewritten. The accepted M5.5/M6 milestones are unchanged.

## Immediate M6.6-B corrections

The current production defect allows Spider creation to stall when taxonomy returns no match.
Taxonomy selection is optional: no result, unknown trade name, outage, timeout, throttle, malformed
or oversized response still allows manual Animal creation with an intentionally unlinked taxon.
An explicit Add/Edit selection must retain the Care Keeper taxon link in that same workflow; a
legacy Animal can link explicitly inline on its profile. Never fuzzy-link free text. The current
[Animal Overview guide summary](../evidence/m6.6-species-aware-husbandry/b-sourced-care-guides/profile-reference/README.md)
is deployed for owner review; finish its correction/review and add future Natural History directly
on the Animal profile, with separate **Your
Records**, **Species Reference**, **Species Overview / Natural History**, **Reviewed Captive Care**,
and **Sources** sections when data exists. The Directory remains for browsing. Complete the Boa
constrictor reviewed guide under [ADR-0044](../adr/0044-versioned-sourced-care-guides.md) and
owner review before declaring B accepted. The [B qualification record](../evidence/m6.6-species-aware-husbandry/b-sourced-care-guides/README.md)
documents implementation and deployment, but still says owner review pending.

### Measurement precision

The reported `48.5` Snake length is an end-to-end correctness case. Current record/correction
[forms](../../src/snaketracker/presentation/templates/animal_care_form.html) use integer mm controls;
[web parsing](../../src/snaketracker/presentation/web.py),
[commands](../../src/snaketracker/application/animals.py),
[contracts](../../src/snaketracker/domains/animals/contracts.py),
[event deserialization](../../src/snaketracker/platform/events/registry.py), and
[analytics](../../src/snaketracker/application/analytics.py) enforce/use integer `length_mm`.
Changing HTML step alone or rounding into v1 cannot preserve all reasonable mm/cm/in inputs.

[ADR-0048](../adr/0048-precise-animal-length-measurements.md) is the sole authority for v2 exact
representation, precision, unit conversion/consistency, bounds, correction and display/export rules.
PR 1 implements that contract through every consumer below; original v1 events stay unchanged.
The current Animal identity projection has no length column: review actual persistence needs before
proposing Alembic. Event/deserializer/projection-handler changes still require compatibility evidence.
Accessible forms expose unit selection, decimal entry, validation errors and mobile input.

### Length v2 consumer qualification

`AT-MEASURE-01` exercises mixed v1/v2, number-only/unit-only/both corrections, invalid redundant
payloads and precision/bounds from ADR-0048. Each row must have implementation evidence before B
acceptance; a v2 correction of v1 must remain an effective fact and reminder source.

| Consumer | PR 1 deliverable / planned acceptance |
|---|---|
| Record and correction | Decimal/unit commands, v2 contracts/serialization and exact consistency checks; idempotent writes retain entered precision |
| Void and reinstatement | Existing effective-history rules cover v1, v2, v2-corrected-v1 and correction chains; restore/remove the correct fact and linked effects |
| Timeline/history and current facts | Original vs effective values/units labelled correctly; no stale integer-only formatting or disappearance |
| Analytics and chart API/JavaScript | Normalize mixed versions; one mm numerical series/axis under ADR-0048, original/preferred-unit tooltips; no mixed-unit points grouped solely by kind |
| Reports and CSV | Deliver explicit precise measurement report/export under ADR-0048; preserve existing care CSV separately (it currently has titles/notes, not numeric measurements) |
| Search | Inspect measurement participation in search documents; where present update effective values after correct/void/reinstate; if absent record that verified exclusion rather than claim numeric coverage |
| Reminders | Update v1-only length qualification in `application/reminders.py`; compare source event identity, due time and one-time override consumption across all mixed-history transitions under a fixed clock |
| Replay and projections | Register both contract versions and projection allowlists/handlers; replay/rebuild from immutable history and compare effective state, read models and catch-up state |
| Browser/accessibility | Record/correct examples from ADR-0048 on mobile/desktop, explicit unit, excess-precision rejection without rounding, keyboard and screen-reader errors |

## Capability foundation and read-only code audit

Capability profiles are **Care Keeper workflow/capability identities**, not taxonomic classifications
or ranks. The linked Care Keeper taxon owns biological identity; the profile determines which
application workflows apply. For example, Bitey can retain `snake.v1` while its linked Boa constrictor
taxon has the illustrative ancestry Animalia → Chordata → Reptilia → Squamata → Serpentes → Boidae
→ Boa → Boa constrictor. `spider.v1` does not call Spider a taxonomic class: its taxon may have
Animalia → Arthropoda → Arachnida → Araneae → … ancestry. Provider classification can evolve
independently of the unchanged registered workflow identity.

[ADR-0045](../adr/0045-extensible-animal-capability-evolution.md#capability-identity-is-independent-of-taxonomy)
owns profile naming and compatibility: the four persisted v1 identities remain unchanged, and
incompatible workflow behavior requires a successor version. `amphibian.v1` may serve compatible
workflows under Amphibia, including Anura/Caudata; distinct future Frog/Salamander behavior may
justify separate versioned profiles. Do not create a profile for every taxonomic order/common name.
The trusted versioned registry should expose identity, version, label, capability set,
care actions, reminder kinds, analytics kinds, visual fallback category, and biological grouping
metadata. Commands and events remain typed and domain-validated. A new broad group should normally
register one profile and its focused adapters. **If adding a broad Animal group requires widespread
unrelated `if animal_type == ...` edits, the extensibility design has failed.** Future candidates
include chelonians, other reptiles, insects, arachnids, fish, and other invertebrates; do not
register speculative profiles now.

| Location | Current assumption / class | Future mechanism | Risk | Tranche |
|---|---|---|---|---|
| `domains/animals/capabilities.py`, `presentation/web.py` `_animal_type_options` and v1 label lookup | Four enum members; all readable identities become form options; assumed v1 labels | Separate read support, eligibility and one group default; render persisted version | Duplicate choices / semantic drift | X1 |
| `platform/events/registry.py`, `bootstrap/compatibility.py` | Four taxon-link groups; startup checks only event type/schema version | Embedded-identity scan and release manifest; retain old validators; X4 registration v3 downgrade barrier | Partial startup / replay crash | X1/X4 |
| `application/species_directory.py`, `infrastructure/taxonomy/repository.py` | Four Animal groups plus plant; validation | Taxonomy group mapping distinct from capability registry | Wrong taxon link | X1/X2 |
| `migrations/versions/0019_universal_species_directory.py` and taxa FKs in 0020/0023 | Non-null five-value `supported_group` CHECK and limited status CHECK; Plant/guide/Animal references share `taxa` | Permanent identity FK target plus generation content; optional mapping for ancestors/unenabled/future groups and qualified status/mapping states, independently validated registration eligibility | Lost references / rejected broad tree | X2 |
| `application/care_guides.py` `GuideGroup`, `glance_claims`, `profile_reference_claims` | Separate five-group enum and literal selectors; existing biological claims in immutable guides | Qualify guide group/selector extension independently; ADR-0047 coexistence presentation | Rejected guide / duplicate authority | X1 audit; X3/X5 delivery |
| `infrastructure/taxonomy/inaturalist.py` `ANCESTOR_BY_GROUP` | Five literal provider ancestor IDs; provider mapping | Configured/qualified ancestry for each group, including Amphibia | False match or omission | X2/X4 |
| `presentation/web.py` `type_order` and list filters | Four literal group order; presentation ordering | Registry display order with stable old ordering | Invisible new group | X1 |
| `presentation/templates/admin.html` | Unknown Animal falls back to Snake image; fallback visual mapping | Registry fallback key and honest neutral unknown fallback | Misleading identity | X1/X4 |
| `presentation/animal_visuals.py`, `application/species_directory.py` `reference_image`, fallback assets | Unknown group falls back to Snake; profile resolver can refresh provider detail/find/download images | Local-only resolver and image serving; explicit bounded fetch outside read path; validated Amphibian fallback | Provider delay / misleading image | B correction/X3/X4 |
| `application/animals.py` length and capability checks | Capability-specific validation plus integer length; legitimate behavior | Retain capability checks; version length separately | Wrong action/precision | B correction/X1 |
| `tests/unit/domains/test_animal_capabilities.py`, `tests/architecture/test_phase_scope.py`, browser fixtures | Exact four-profile assertions; test fixtures | Historical four-profile compatibility plus additive-profile tests | False failure or missing coverage | X1/X4 |

Audit other selectors in reminders, analytics, search, form choices, Admin, CSS and fixtures during
X1. Preserve legitimate specialized behavior (snake shed, spider v1 molt); generalize only group
enumeration and presentation selection. Registry metadata must be trusted code, not user JSON or a
plugin. Profile version is persisted at registration; taxon edits never alter it.

### Profile lifecycle and startup qualification

[ADR-0045](../adr/0045-extensible-animal-capability-evolution.md) owns lifecycle/default selection,
provider-group mapping interface, supported-profile manifest, startup scan and downgrade policy.
`AT-CAPREG-01` must show a readable but registration-ineligible historical profile, exactly one
new-registration default per group, unchanged existing Animal identities, and safe rejection of an
unknown profile inside otherwise-known registration v2 (including voided/historical events).
Scan required extensible identities before normal traffic/replay, not only contract pairs. X1 adds
this capability to the current release; X4 introduces registration v3 with Amphibian as the barrier
that the actual pre-Amphibian binary's existing contract scanner can reject. It must not be made
readable early in X1–X3. Expand taxon-link validation through v2 while retaining the four-group v1
decoder; do not emit Amphibian into a historically invalid v1 payload. Every declared downgrade
target must reject cleanly after the new write.

## Taxonomy and reference architecture

The current cache contains encountered taxa, not a complete tree.
[ADR-0046](../adr/0046-local-taxonomy-snapshot-and-provider-overlay.md) owns durable identity,
generation/overlay semantics, concurrency, promotion and rollback. X2 implements a permanent Taxon
Identity Catalog for all Animal/Plant/guide FKs, replaceable indexed archive content, and basic live
identity/overlay coexistence **before** X3 enriches metadata. Broad reference ancestors and Amphibia
can exist in X2 without becoming eligible Animal registrations until X4.

The [refresh runbook](../operations/taxonomy-snapshot-refresh.md) owns download/staging/promotion
operations. `AT-TAXBAS-01` proves B-introduced taxon → Animal link → rollback A still resolves;
live discovery during B import survives promotion/search; cleanup cannot delete referenced
identities. Include Plant/guide references, namespaced homonyms, split/lump conflicts, duplicate
mapping races, missing entries and older snapshot versus fresher overlay. Failed bounded final
reconciliation leaves A active. Do not delete/recreate UUIDs or automatically relink Animals.

Search indexed local names/ancestry plus overlay/catalog fallback first, then bounded explicit live
lookup where useful. Manual entry is always available. Use SQLite indexes/FTS rather than archive
scans per keystroke. Measure cold/warm autocomplete, exact detail, import time, storage, RAM, CPU
and promotion on the Pi before setting budgets; no guessed threshold becomes acceptance evidence.

Live iNaturalist supports autocomplete freshness and exact detail, active/synonym state, names,
classification, eligible reference images, conservation and other public metadata. Current detail
parsing keeps ancestry, a preferred common name and eligible image metadata but discards
`wikipedia_summary`, `wikipedia_url`, `is_active`, `current_synonymous_taxon_ids`, observation
count and other detail. Evaluate additional common names, conservation status and
native/endemic/introduced metadata only with their geographic context. Evaluate each retained
field for product purpose, actual source, provenance, licence and freshness;
do not persist fields merely because available. Its API is for app requests, not bulk acquisition:
cache, deduplicate, bound timeout/response, back off on 429, and respect the provider's
[recommended practices](https://www.inaturalist.org/pages/api%2Brecommended%2Bpractices).
The [iNaturalist source](https://github.com/inaturalist/inaturalist),
[API source](https://github.com/inaturalist/iNaturalistAPI), and
[API reference](https://api.inaturalist.org/docs) are provider-contract references, not authority
for household identity.
Only public scientific query/group data leaves Care Keeper; never user/email/household/Animal IDs,
notes, history, Inventory, expenses or private attachments. Reptile Database, World Spider Catalog,
Catalogue of Life/ChecklistBank and GBIF are later specialist/fallback evaluations conditional on
identity mapping, terms, licensing and permitted automation, never scraping by default.

| iNaturalist dataset | Decision | Purpose / boundary |
|---|---|---|
| [Taxonomy DarwinCore Archive](https://www.inaturalist.org/pages/developers) | Use in X2 foundation | Local names/ancestry/search; reference snapshot, not household authority |
| [Open Range Map Dataset](https://www.inaturalist.org/pages/range_maps) | Near-future evaluation | Sourced natural range with dataset/model version and licence; never husbandry inference |
| Licensed Observation Images / AWS open data | Later | Better licensed species imagery only; no full Pi mirror |
| Massive observation exports and FGVC training sets | Defer | No current tracker use or model-training need |
| Unpublished computer-vision suggestion interface | Defer | No production dependency |

Image priority stays keeper photo → eligible licensed species photo/illustration → honest group
fallback, as in ADR-0043. Image provenance includes creator, source, media ID, licence and URL.
No new taxonomy image may displace the keeper's photo.

## Species Overview / Natural History

[ADR-0047](../adr/0047-natural-history-reference-boundary.md) owns biological-reference authority,
source responsibility and immutable Care Guide coexistence. X3 implements sourced optional facts
and presentation precedence, without copying/rewriting legacy versions or showing equivalent facts
as competing authorities. `AT-NATHIST-01` covers available/missing/conflicting Natural History,
legacy biological claims, captive-context claims, source/licence attribution and no household writes.
Captive guidance follows the [reviewed guide policy](../operations/care-guide-sources.md).

### Ordinary Animal profile reads: zero outbound calls

Current `AnimalVisualResolver.resolve` calls `SpeciesDirectoryService.reference_image`, which can
refresh detail, query image providers or download on a cold/missing path. PR 1 removes that work
from ordinary rendering; X3 preserves the requirement while adding reference content. Rendering
and its image-serving paths use already-local keeper photos, cached eligible reference assets,
local taxonomy/guide facts or fallback artwork only. Enrichment/retrieval runs in an explicit
bounded fetch/refresh workflow outside the ordinary read request. Stale/missing optional data
renders an honest local fallback; no synchronous refresh is triggered by viewing the profile.

`AT-PROFILE-REF-01` instruments all outbound provider/download transports and asserts zero calls
for warm cached, missing reference image, and cold/missing optional reference state, including
locally served image requests. With providers unavailable, profiles remain responsive and usable;
absence/outage cannot block Your Records or trigger a retry delay. Test linked/unlinked Animals,
photo priority, source labels, mobile/desktop and accessibility.

## `amphibian.v1` qualification

X4 adds one conservative Amphibia profile for initial Frog support. Qualified provider ancestry
may include Anura, Caudata/Urodela and Gymnophiona; use provider IDs rather than a Frog list or
order-name strings as permanent identity. The following is the **exact proposed initial matrix**,
frozen for implementation qualification; it does not assert current implementation/acceptance.

| Axis | Included set |
|---|---|
| Capabilities | `feeding`, `weight`, `length`, `enclosure_assignment`, `photos`, `notes`, `inventory`, `expenses`, `reminders`, `timeline` |
| Care actions | `feeding`, `weight`, `length` |
| Reminder kinds | `feeding`, `weight`, `length`, `cleaning`, `water_change` |
| Analytics kinds | `feeding`, `weight`, `length` |

Feeding records a keeper-observed feeding/outcome and same-household Inventory consumption,
without inferring diet or interval. Weight and length record explicit physical measurements,
without prescribing growth targets. Enclosure assignment, photos, notes, expenses and timeline
retain individual record/ownership semantics; Inventory retains existing stock/FIFO semantics.
Reminders are explicitly keeper-configured. Feeding/weight/length reuse their effective source
facts; cleaning/water-change refer to recorded Enclosure actions and imply neither an aquatic
life stage nor a species-specific schedule. Analytics summarizes only these recorded facts.

Exclude shed, molt/premolt, bath and misting from the initial profile's capability/action/reminder/
analytics sets; do not impose them by reuse. Enclosure misting needs separate future qualification.
Aquatic stages, metamorphosis and water quality are future versioned work and do not block initial
Frogs. `AT-AMPH-01` verifies the exact sets, rejected excluded actions, mixed historical profiles,
Amphibia mapping, registration-v3 barrier and a distinct fallback image. Add/Edit/profile/search/
analytics/browser qualification precedes X5's representative taxon-specific reviewed Frog guides;
never publish generic all-Frog advice. Owner reviews mobile and desktop reference presentation.

## Delivery and release gates

| PR / tranche | Bounded implementation and acceptance focus |
|---|---|
| PR 1 / M6.6-B correction | Spider manual/no-result flow, retained Add/Edit link, local-only profile/visual reads, owner-reviewed inline reference correction, Boa guide, complete length consumer matrix/report-export and `AT-SPDIR-MANUAL-01`, `AT-MEASURE-01`, `AT-PROFILE-REF-01` |
| PR 2 / X1 | Read-support/registration lifecycle, frozen four identities, embedded-identity startup scan/manifest, schema/guide/selector audit, compatibility rehearsal and `AT-CAPREG-01` |
| PR 3 / X2 | Permanent catalog and FK protection, staged reference generations, basic live-overlay reconciliation, rollback/cleanup/search qualification and `AT-TAXBAS-01` |
| PR 4 / X3 | Live metadata overlay, provenance, sourced Natural History, profile integration and `AT-TAXOVER-01`, `AT-NATHIST-01` |
| PR 5 / X4 | `amphibian.v1` frozen matrix, registration v3 and actual-old-binary rejection, Amphibia mapping, unique fallback, end-to-end care and `AT-AMPH-01` |
| PR 6 / X5 | Representative reviewed Amphibian guides, browser/owner review and `AT-AMPHREF-01` |

### Production compatibility manifest: `AT-PRODCOMP-01`

Apply this gate to **every event-contract, profile-registry or provider/reference-model change**,
including PRs with no Alembic migration. Before production change, follow
[ADR-0018](../adr/0018-backup-and-restoration.md),
[ADR-0026](../adr/0026-migration-and-rollback.md) and
[ADR-0033](../adr/0033-release-compatibility-matrix.md): encrypted backup, isolated restore including
attachments, upgrade only the isolated copy, replay immutable events and rebuild/verify projections.

Capture before/after semantic manifests at a common event cutoff. Freeze/control the clock and
household timezone for due/notification calculations; quiesce fixture writers and record fixture,
release, projection generations and cutoff so comparison is reproducible. Compare every household,
with stable IDs and deterministic ordering:

| Manifest area | Required semantic equivalence |
|---|---|
| Events and Animals | Immutable event IDs/envelopes/contents; registrations and persisted profile identities; corrected, voided and reinstated effective history |
| Feeding and Inventory | Inventory-linked Feedings, consumption/FIFO allocations/effects, quantities/balances and valuation; purchases/expenses and ownership |
| Reminders/notifications | Rules, overrides and consumed state, qualifying source event IDs, due times, notification deduplication state |
| Idempotency | Keys/scopes, command hashes and stored responses; retrying a stored command returns its original response without duplicate effects |
| Taxa and media | Animal/Plant taxon UUID links, personal photos, reference-image preferences, attachment IDs/versions/content references and locally resolvable catalog identities |
| Ownership and reads | Accounts/households, Enclosure/Plant ownership, search visibility/content, reports and Admin/support read views with existing authorization boundaries |
| Projections | Handler/generation compatibility, rebuilt effective facts and catch-up positions through the same cutoff; no silent missing events or stale read view |

This is semantic household/business-state equivalence, not byte-identical database files. Enumerate
expected differences in the evidence before comparison: new global reference content, semantically
irrelevant regenerated derived timestamps, or deliberately invalidated sessions only if the migration
procedure requires it. Reference differences may not change household links/preferences/records or
hide their identities. Any other difference blocks release until explained and explicitly accepted.

The compatibility fixtures include v1 registration, all four v1 profiles, Spider-only molt/premolt
v1 and neutral v2, v1/v2 length with mixed correction/void/reinstate, linked/unlinked/manual taxa,
and after X4 registration v3/Amphibian plus taxon-link v2. Test unknown required identities inside
known contracts, unknown event versions, fail-closed startup and actual older-binary downgrade
after unreadable writes.
Taxonomy pointer rollback must preserve new durable identities; it is not household-data rollback.

Each tranche additionally needs the frozen quality gate, browser/accessibility qualification,
applicable Pi measurements, production-safe deployment and explicit owner acceptance. Tests and
deployment do not equal acceptance. B corrections → X1 → X2 → X3 → X4 → X5 → M6.6-C remains the
sequence; C stays unstarted until the required pre-C acceptance gates pass.

| Risk | Impact | Mitigation | Required acceptance evidence |
|---|---|---|---|
| Event replay regression / profile semantic drift | Historical Animals misread | Keep historical handlers and four profiles frozen; add separately versioned contracts | Mixed-version replay, startup/downgrade rejection and state diff |
| Accidental Animal relinking / taxon UUID replacement | Household identity corrupted | Explicit keeper link only; import maps existing UUIDs | Link/UUID before-after diff |
| Bulk corruption / dataset format change | Search outage | Validate staged archive/schema, atomic generation swap, rollback | Import failure and rollback drill |
| Provider outage, throttle, stale data or disagreement | Missing/wrong reference | Local cache, bounded backoff, review ambiguous mappings | Offline, 429 and conflict tests |
| Copyright or licence error | Unusable content | Actual-source attribution, rights gate and removal path | Provenance/licence audit |
| Natural history shown as captive care | Unsafe guidance | Separate model, headings and source policy | Browser/content review |
| Pi search/storage load | Slow or failed autocomplete | FTS/indexes, bounded generations | Cold/warm, storage, RAM, CPU measurements |
| Manual creation regression | Keeper blocked | Manual path independent of provider | Spider no-result/outage browser test |
| Fraction truncation, conversion or mobile entry error | Wrong care history | Decimal conversion to micrometres; retain entered unit/scale | `48.5`, `12.25`, `0.5`, correction/replay/analytics/mobile tests |

Evidence is created only during implementation under future traceability paths; historical
evidence stays unchanged. M6.6-A PR #14 integration and ADR-0043's later Accepted status assertion
are separate from milestone owner acceptance: no standalone A owner record was found in repository
evidence. The roadmap retains that gap without retroactive acceptance.

### Architecture-freeze governance validation

The generic [validator](../../scripts/quality/verify_architecture_freeze.py) implements
[ADR-0028](../adr/0028-architecture-governance-and-decision-freeze.md): **Proposed decisions may be
introduced; promotion or modification of accepted architecture requires traceable approved
amendment/supersession evidence.** It discovers ADRs, validates unique IDs/index/status metadata,
and inspects HEAD, the Git index and working-tree/untracked documentation independently. Accepted
content and frozen package changes require evidence bound to the exact reviewed content. The
[baseline tooling authorization](../evidence/m0-architecture/2026-10-01-generic-governance-baseline.md)
documents the inherited checkpoint, approval record fields, and this task's limited authority.
It does not accept ADRs 0044–0048, M6.6-A or M6.6-B, or authorize PR 1 implementation.

The plan remains a proposal; baseline closure changes documentation and governance tooling only.
