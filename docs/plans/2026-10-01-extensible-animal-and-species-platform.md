# Extensible Animal and Species Platform — controlling implementation plan

Status: M6.6-B Accepted / Complete / Merged; Pre-X1 documentation reconciliation prepared for owner review October 5, 2026. X1–X5 implementation and acceptance remain unstarted. The original extension direction was approved October 1, 2026.
Scope: documentation only. This plan inserts bounded work after M6.6-B corrections and before
M6.6-C. No production migration, dataset import, deployment, or event rewrite is authorized here.

## Authority and intent

This plan adds the implementation sequence to the existing [roadmap](../roadmap/milestones.md) and
[traceability matrix](../requirements/traceability-matrix.md). It extends accepted
[ADR-0039](../adr/0039-multispecies-animal-capabilities.md),
[ADR-0041](../adr/0041-four-group-capability-expansion-and-neutral-molt-contracts.md), and
[ADR-0043](../adr/0043-universal-species-directory.md), plus accepted
[ADR-0044](../adr/0044-versioned-sourced-care-guides.md). Proposed extension decisions are in
[ADR-0045](../adr/0045-extensible-animal-capability-evolution.md),
[ADR-0046](../adr/0046-local-taxonomy-snapshot-and-provider-overlay.md),
[ADR-0047](../adr/0047-natural-history-reference-boundary.md). Accepted
[ADR-0048](../adr/0048-precise-animal-length-measurements.md) governs delivered length v2. Event evolution, backup,
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

The October 1 Spider/no-result and explicit Add/Edit/legacy-link corrections are implemented,
qualified and included in [M6.6-B owner acceptance](../evidence/m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance).
Manual Animal creation remains independent of provider outcomes; free text is never fuzzy-linked.
The final accepted UI supersedes the earlier inline/full-Overview direction: **Overview** is a
compact summary with limited reviewed highlights and a link. The dedicated **Guides & Species
Reference** tab after Care contains compact **Species Overview / Natural History** (locally saved
identity/classification/names), complete **Reviewed Captive Care**, and **Sources / Provenance**,
using Taxonomy, care and source disclosures without dropping content or disagreement positions.
Richer Natural History remains future X3; missing guides say **No reviewed captive-care guide is
available yet.** The reviewed Boa constrictor guide, local-only reads, exact length consumer matrix
and production/backup preservation are accepted B scope. Historical receipts remain unchanged.

### Measurement precision

The original `48.5` correctness case exposed integer-mm-only controls and v1 consumers.
The accepted correction now supports exact mm/cm/in input using canonical integer `length_um`,
retained entered value/scale/unit, and mixed v1/v2 readers. V1 history is unchanged; no authoritative
binary float, truncation or silent rounding is introduced. Implementation evidence is the
[B correction consumer matrix](../evidence/m6.6-species-aware-husbandry/b-corrections/README.md#exact-length-consumer-matrix--at-measure-01).

[ADR-0048](../adr/0048-precise-animal-length-measurements.md) is the sole authority for v2 exact
representation, precision, unit conversion/consistency, bounds, correction and display/export rules.
M6.6-B implements and qualifies that contract through every consumer below; original v1 events stay unchanged.
The current Animal identity projection has no length column: review actual persistence needs before
proposing Alembic. Event/deserializer/projection-handler changes still require compatibility evidence.
Accessible forms expose unit selection, decimal entry, validation errors and mobile input.

### Length v2 consumer qualification

`AT-MEASURE-01` exercises mixed v1/v2, number-only/unit-only/both corrections, invalid redundant
payloads and precision/bounds from ADR-0048. Each row must have implementation evidence before B
acceptance; a v2 correction of v1 must remain an effective fact and reminder source.

| Consumer | Accepted M6.6-B deliverable / preserved contract |
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
care actions, reminder kinds, analytics kinds, visual fallback category, and stable workflow-group
metadata. Commands and events remain typed and domain-validated. A new broad group should normally
register one profile and its focused adapters. **If adding a broad Animal group requires widespread
unrelated `if animal_type == ...` edits, the extensibility design has failed.** Future candidates
include chelonians, other reptiles, insects, arachnids, fish, and other invertebrates; do not
register speculative profiles now.

| Location | Current assumption / class | Future mechanism | Risk | Tranche |
|---|---|---|---|---|
| `domains/animals/capabilities.py`, `presentation/web.py` `_animal_type_options` and v1 label lookup | Four enum members; all readable identities become form options; assumed v1 labels | Separate read support, eligibility and one group default; render persisted version | Duplicate choices / semantic drift | X1 |
| `platform/events/registry.py`, `bootstrap/compatibility.py` | Four taxon-link groups; startup checks only event type/schema version | Embedded-identity scan and release manifest; retain old validators; X4 registration v3 downgrade barrier | Partial startup / replay crash | X1/X4 |
| `application/species_directory.py`, `infrastructure/taxonomy/repository.py` | Four Animal groups plus plant; validation | Qualified taxon-to-workflow mapping consumes X1 group interface; taxonomy implementation belongs to X2 | Wrong taxon link | X2 |
| `migrations/versions/0019_universal_species_directory.py` and taxa FKs in 0020/0023 | Non-null five-value `supported_group` CHECK and limited status CHECK; Plant/guide/Animal references share `taxa` | Permanent identity FK target plus generation content; optional mapping for ancestors/unenabled/future groups and qualified status/mapping states, independently validated registration eligibility | Lost references / rejected broad tree | X2 |
| `application/care_guides.py` `GuideGroup`, `glance_claims`, `profile_reference_claims` | Separate five-group enum and literal selectors; existing biological claims in immutable guides | Qualify guide group/selector extension independently; ADR-0047 coexistence presentation | Rejected guide / duplicate authority | X1 audit; X3/X5 delivery |
| `infrastructure/taxonomy/inaturalist.py` `ANCESTOR_BY_GROUP` | Five literal provider ancestor IDs; provider mapping | Configured/qualified ancestry for each group, including Amphibia | False match or omission | X2/X4 |
| `presentation/web.py` `type_order` and list filters | Four literal group order; presentation ordering | Registry display order with stable old ordering | Invisible new group | X1 |
| `presentation/templates/admin.html` | Unknown Animal falls back to Snake image; fallback visual mapping | Registry fallback key and honest neutral unknown fallback | Misleading identity | X1/X4 |
| `presentation/animal_visuals.py`, `application/species_directory.py` `reference_image`, fallback assets | Unknown group falls back to Snake; profile resolver now uses local cached imagery; explicit acquisition remains separate | Preserve local-only resolver and image serving; explicit bounded fetch outside read path; validated Amphibian fallback | Provider delay / misleading image | B correction/X3/X4 |
| `application/animals.py` length and capability checks | Capability-specific validation and accepted exact length v2; legitimate behavior | Retain capability checks; version length separately | Wrong action/precision | B correction/X1 |
| `tests/unit/domains/test_animal_capabilities.py`, `tests/architecture/test_phase_scope.py`, browser fixtures | Exact four-profile assertions; test fixtures | Historical four-profile compatibility plus additive-profile tests | False failure or missing coverage | X1/X4 |

Audit other selectors in reminders, analytics, search, form choices, Admin, CSS and fixtures during
X1. Preserve legitimate specialized behavior (snake shed, spider v1 molt); generalize only group
enumeration and presentation selection. Registry metadata must be trusted code, not user JSON or a
plugin. Profile version is persisted at registration; taxon edits never alter it.

### X1 scope and lifecycle qualification

X1 is a workflow/capability foundation. Preserve the exact `snake.v1`, `spider.v1`, `lizard.v1`
and `scorpion.v1` semantics. Separate exact readable profiles, registration eligibility, one
eligible default per enabled workflow group, stable group metadata, exact profile-to-group membership
and trusted presentation. Existing Animals retain their original profile for editing, actions,
reminders, analytics and replay after that profile becomes registration-ineligible. For example,
future `snake.v2` may become the default while existing `snake.v1` Animals remain usable. Never
silently upgrade or validate historical records against today's registration policy.

Completed identical registration retries return the original Animal/result using the stored
operation's resolved profile/default, even after a default change. Resolve that operation before
computing today's default; do not rewrite command hashes or make an original success conflict.
Changed requests under the same key still conflict. `AT-CAPREG-01` covers these cases and retained
profile semantics; `AT-PRODCOMP-01` reconstructs real Animals, not just contract scanner results.

X1 implements no provider IDs/ancestry, archive/generations, broad taxonomy changes, Natural History,
Amphibians or new Care Guides. Auditing current taxonomy constraints/guide selectors does not bring
their implementation into X1.

### Interface contracts between tranches

| Boundary | Owned data / local interface | Consumer constraint |
|---|---|---|
| X1 capability foundation | Exact persisted profile, stable workflow group, read support, eligibility/default policy, trusted presentation | X2 cannot assume every readable profile is eligible or every group enabled |
| X2 taxonomy foundation | Permanent UUID; selected scientific/common names, hierarchy/classification, provider mappings/status evidence, provenance/freshness; qualified taxon-to-workflow mapping | Biological classification cannot grant capabilities; a taxon may have no registerable group |
| X2 → X3 local ports | Resolve permanent UUID, selected taxonomy summary/provenance, qualified workflow-group mappings, and taxonomy provider/source references with their qualification/conflict state | X3 displays X2-selected identity/names/classification and uses references to resolve and validate candidate content sources; X3 owns durable Natural History source associations after its separate migration |
| X3 Natural History | UUID → source association → retained content version → publication/withdrawal selection | Generation is acquisition context only, never identity, required FK, selection or cleanup dependency |

**Taxonomy owns identity/classification/names. Natural History owns descriptive biological content.**
Care Guide coverage is independent of both taxonomy existence and Animal registration eligibility.

X2 does not create or own Natural History source associations. An iNaturalist provider mapping,
taxonomy archive source, Wikipedia URL candidate or provider provenance alone does not create
such an association. X3 validates candidate content sources under its own identity, scope,
provenance, rights and publication rules before creating or retaining the durable UUID-attached
association. X2 does not own or require X3 content versions, publication selection or rights/publication state.

### Compatibility preflight before mutable startup

[ADR-0045](../adr/0045-extensible-animal-capability-evolution.md) owns the supported-profile manifest
and identity extractors. Inspect all events, including voided/corrected history, and fail closed on
unknown contracts, unsupported required embedded identities or failed/malformed inspection.
For existing storage the required order is:

1. Open storage for read-only compatibility inspection.
2. Check schema/Alembic compatibility, event contracts, required embedded profile identities and
   projection catalog, in that order.
3. Check active X2 reference structures when implemented, then X3 selected-content/publication
   structures when implemented. X1 provides extension points, not future validators.
4. Only after all checks pass initialize the mutable engine, replay/catch up projections, change
   generation state, start schedulers/workers, claim jobs or serve ordinary traffic.

Verified at baseline `4be4deb`: `bootstrap/application.py` calls `create_sqlite_engine` before
`inspect_startup_compatibility`; `infrastructure/database/engine.py` applies WAL/profile setup and
initial vacuum initialization. The future order above is not delivered behavior. Initial database
creation and explicit migrations are separate authorized workflows. Qualification must prove
unsupported identity rejection occurs before mutable initialization, not merely before HTTP readiness.

X1 expects no Alembic migration; that does not prove older-binary compatibility. Embedded profiles,
event versions, projections and runtime formats all matter. X1 introduces deliberate embedded-
identity rejection. Registration v3, expanded taxon-link v2 and `amphibian.v1` remain X4: retain
historical v1/v2 decoders, do not make X4 contracts readable early and test actual declared rollback
binaries after the first unreadable write. A mocked scanner is insufficient.

## Taxonomy and reference architecture

The current cache contains encountered taxa, not a complete tree.
[ADR-0046](../adr/0046-local-taxonomy-snapshot-and-provider-overlay.md) owns durable identity,
generation/overlay semantics, concurrency, promotion and rollback. X2 implements a permanent Taxon
Identity Catalog for Animal/Plant/guide/media and X3 references, replaceable indexed archive
content, and basic live identity/overlay coexistence **before** X3 adds descriptive content. Useful retained labels,
provenance, mappings and fallback search survive absence, rename, refresh, promotion, rollback and
cleanup; opaque-UUID-only retention is insufficient. Never merge identities by name alone.
Broad reference ancestors and Amphibia
can exist in X2 without becoming eligible Animal registrations until X4.

The [refresh runbook](../operations/taxonomy-snapshot-refresh.md) owns download/staging/promotion
operations. `AT-TAXBAS-01` proves B-introduced taxon → Animal link → rollback A still resolves;
live discovery during B import survives promotion/search; cleanup cannot delete referenced
identities. Include Plant/guide references, namespaced homonyms, split/lump conflicts, duplicate
mapping races, missing entries and older snapshot versus fresher overlay. Failed bounded final
reconciliation leaves A active. Do not delete/recreate UUIDs or automatically relink Animals.

Replaceable generations contain snapshot names/hierarchy/classification/search; the durable catalog
and overlay retain UUIDs, mappings, useful labels, live discoveries, conflicts and fallback search.
Use one SQLite transaction for bounded final reconciliation and the active-generation/search pointer;
no distributed lock is needed. Rollback preserves discoveries made after the older generation,
including X3 content attached to those UUIDs.

Search indexed local names/ancestry plus overlay/catalog fallback first, then bounded explicit live
lookup where useful. Include qualified aliases/synonyms only where supported. Household-private
FTS, global taxonomy search and Natural History prose stay distinct; initially exclude prose from
taxonomy indexes and all global reference content from household-private FTS. Manual entry is
always available. Use SQLite indexes/FTS rather than archive
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
source responsibility and immutable Care Guide coexistence. X3 implements permanent-UUID source
associations, retained versions and explicit publication/withdrawal selection with provenance and
presentation precedence, without copying/rewriting legacy versions or showing equivalent facts
as competing authorities. `AT-NATHIST-01` covers available/missing/conflicting Natural History,
legacy biological claims, captive-context claims, actual-origin deduplication, generation
independence, source/licence attribution and no household/reference read mutations. A small trusted
semantic/context adapter compares taxon, fact kind, life stage, wild/captive context, geography, sex,
value/unit, qualifiers and originating source. Equivalent qualified biological facts display once
with combined provenance; distinct contexts/disagreements stay separate, and unknown legacy
classification stays in original guide context. One source through two intermediaries counts once.
No second Care Guide system or mutable legacy payload is introduced.
Captive guidance follows the [reviewed guide policy](../operations/care-guide-sources.md).

### Required X3 qualification: Central American Boa

`AT-NATHIST-01` must include an Animal explicitly linked to **Central American Boa / Boa imperator**,
with iNaturalist taxon mapping **`539399`**, and **no reviewed captive-care guide**. X3 must prove
that its Guides & Species Reference page displays locally stored/cached Species Overview / Natural
History independently of guide availability: taxonomy/classification, preferred/common names,
a useful sourced species description, preferably revision-specific Wikipedia acquisition with
actual Wikipedia origin/revision and applicable attribution/license/modification evidence. Qualified
conservation, range/distribution and other Natural History claims may appear where approved sources
support them; prose alone is not converted into structured habitat, lifespan, diet, adult size or
range. Structured facts require a specifically qualified source/workflow. Unavailable facts remain
unknown; the missing-guide message specifically states “No reviewed captive-care guide is available
yet.” Biological reference is not classified as captive husbandry or duplicated as a competing
authority over legacy guide claims; ADR-0047's presentation precedence applies.

X2 supplies the ADR-0046 local taxonomy/reference baseline from the iNaturalist Taxonomy DarwinCore
Archive, Care Keeper-owned taxon UUIDs and namespaced provider mappings; X3 adds separately qualified
descriptive content. Bounded iNaturalist discovery can supply
source associations, with revision-specific origin acquisition where required. Content versions and
publication selection do not depend on the active taxonomy generation. Qualification must show
zero outbound calls
during ordinary Overview and Guides & Species Reference reads, including with providers unavailable;
enrichment runs outside rendering and sends no household/private data externally. This is a required
future X3 acceptance case, not X2/X3 implementation within the M6.6-B presentation correction.

### Ordinary Animal profile reads: zero outbound calls

Accepted B rendering uses `SpeciesDirectoryService.cached_reference_image`; the explicit
`reference_image` acquisition workflow remains separate. X3 preserves local-only rendering while
adding content. Rendering and its image-serving paths use already-local keeper photos, cached eligible reference assets,
local taxonomy/guide facts or fallback artwork only. Enrichment/retrieval runs in an explicit
bounded fetch/refresh workflow outside the ordinary read request. Stale/missing optional data
renders an honest local fallback; no synchronous refresh is triggered by viewing the profile.

`AT-PROFILE-REF-01` instruments all outbound provider/download transports and asserts zero calls
for warm cached, missing reference image, and cold/missing optional reference state, including
locally served image requests. With providers unavailable, profiles remain responsive and usable;
absence/outage cannot block Your Records or trigger a retry delay.

Ordinary Animal/reference/local-image reads trigger no provider acquisition or household/domain,
projection, schedule, reminder, notification-intent, Inventory, expense, catalog/mapping/generation/
overlay/search, Natural History/publication, acquisition-job, reference-image-cache or keeper-media
mutation. Existing auth/session/security bookkeeping (last-seen, CSRF, rotation, security audit)
remains permitted under current policy. This is not a zero-SQL-write rule. Instrument forbidden
state changes separately from legitimate authentication writes; do not change authentication here.

Keeper-owned attachments remain mandatory recovery content; reference-image metadata/provenance
are durable. Optional cached reference bytes may be reacquirable only under an accepted recovery
contract. When absent, use a keeper photo, else eligible bundled/group fallback; taxonomy/text still
render. No hotlink, broken remote image or page-read recovery acquisition is permitted.
Test linked/unlinked Animals,
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
| PR 1 / M6.6-B correction | Spider manual/no-result flow, retained Add/Edit link, local-only profile/visual reads, owner-accepted compact Overview and dedicated reference tab, Boa guide, complete length consumer matrix/report-export and `AT-SPDIR-MANUAL-01`, `AT-MEASURE-01`, `AT-PROFILE-REF-01` |
| PR 2 / X1 | Exact readable profiles, eligibility/defaults, completed-retry invariants, stable workflow/presentation metadata and pre-mutable startup; no taxonomy implementation or expected Alembic; `AT-CAPREG-01` and normal-worker backup qualification |
| PR 3 / X2 | Separate migration preserving catalog/reference FKs and guide triggers, staged generations, durable overlay, transactional promotion/rollback/search and `AT-TAXBAS-01`; synthetic development before production import qualification |
| PR 4 / X3 | Separate additive migration after accepted X2: UUID source association/version/publication, rights/provenance, immutable-guide coexistence and local-only reference integration; `AT-TAXOVER-01`, `AT-NATHIST-01` |
| PR 5 / X4 | `amphibian.v1` frozen matrix, registration v3 and actual-old-binary rejection, Amphibia mapping, unique fallback, end-to-end care and `AT-AMPH-01` |
| PR 6 / X5 | Representative reviewed Amphibian guides, browser/owner review and `AT-AMPHREF-01` |

### Production import, jobs/provider and complexity gates

X1 introduces no external-content rights dependency or new job types. X2 development uses synthetic
fixtures; production import qualifies the actual archive, intended use, provenance and attribution/
rights policy. Do not assert archive CC0 without evidence. X3 can develop against synthetic/qualified
fixtures, but production publication requires material-specific rights, attribution and modification
handling: applicable Wikipedia text and Wikidata structured-data terms; iNaturalist per material/
source; direct IUCN content remains unqualified. Owner approval cannot replace missing rights.
Acquisition success does not imply approved publication.

Initial X2 import may remain a bounded operator workflow. Before the second queued workload,
likely X3 enrichment, extend one existing SQLite durable queue with type-filtered claiming and lease
recovery, typed payload validation, handlers and retries. Keep taxonomy/Natural History/media adapters
separate; when required their transport shares User-Agent, host/endpoint allowlists, timeout/response
bounds, aggregate rate/concurrency, Retry-After, bounded retry, deduplication and private-data-safe
telemetry. Independent adapters cannot each consume the full provider allowance. These are future
prerequisites, not X1 work; no Redis, broker or second queue without demonstrated need.

X2's own migration replaces restrictive parent constraints while preserving every Animal/Plant link,
UUID, taxon name, provider mapping, image metadata, guide version/source/claim and immutability trigger.
X3's separate additive migration follows accepted X2. Do not build a universal source/version framework
in X2 to save a migration. Essential X1 metadata/preflight, X2 catalog/generation/overlay/transactional
pointer/local indexes and X3 association/version/selection/provenance fit the Pi/small-user context.
Defer general job expansion until needed, Natural History FTS, extra providers, mass enrichment,
speculative profiles and streaming backup redesign. No distributed locks or new household event stream.

### Backup and operational release gates

The [qualified private recovery point](../evidence/m6.6-species-aware-husbandry/b-corrections/backup-completeness/README.md)
proves finalized-attachment completeness. It does not qualify normal worker reliability under the
known 16 MiB temporary-space constraint. **Before X1 release acceptance**, qualify the ordinary
production-equivalent backup/verification path under intended runtime constraints; if scratch space
prevents completion, make and qualify the smallest operational correction. Do not automatically
redesign streaming backup. Before production-sized X2 import, measure database/generation/index size,
WAL, backup scratch high water, backup/restore memory and duration, restore compatibility/replay and
impact on normal duties. Streaming remains measurement-driven. See the
[backup runbook](../operations/backup-and-restoration.md#extension-release-gates).

Production PCRE2/Perl package findings remain a separate security/operations follow-up in the
[runtime runbook](../operations/runtime-operations.md#separate-production-security-follow-up).
No package/base-image upgrade, host restart or deployment is part of this documentation task or X1
architecture. Fresh CI image success is not evidence that the running production image was patched.

### Three different rollback operations

| Operation | Compatibility / data boundary |
|---|---|
| Application rollback | Actual older binary must support schema, events, embedded identities, projections and runtime formats; no Alembic does not establish safety |
| Taxonomy generation rollback | Change the reference/search pointer transactionally; preserve household state, permanent catalog/mappings/overlay/labels/links, X3 content and guides |
| Disaster recovery restore | Explicitly authorized verified historical backup restore into new storage, with stated RPO and accepted loss of post-backup writes; never equivalent to pointer rollback |

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

One compatibility framework uses the common manifest above with tranche-specific extensions:

| Tranche | Additional `AT-PRODCOMP-01` evidence |
|---|---|
| X1 | Frozen four-profile semantics; read support vs eligibility/defaults; completed retries; pre-mutable identity rejection; actual Animal reconstruction; applicable actual rollback binary |
| X2 | FK-preserving migration; catalog/mapping uniqueness; reference-only taxa; concurrent archive/API identity allocation; overlay/search; promotion, rollback and cleanup; production-scale backup/restore |
| X3 | Source/version integrity; publication/withdrawal; immutable guides; origin deduplication; generation independence; read purity; missing content; rights/provenance |

Do not create three unrelated compatibility systems or treat a scanner fixture as complete replay
qualification. Each tranche additionally needs the frozen quality gate, browser/accessibility qualification,
applicable Pi measurements, production-safe deployment and explicit owner acceptance. Tests and
deployment do not equal acceptance. Accepted M6.6-B → Pre-X1 Architecture Reconciliation → X1 → X2 → X2 production import/
qualification → small job/provider prerequisite if required → X3 → X4 → X5 → M6.6-C is the
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
That October 1 authorization did not accept ADRs 0044–0048, M6.6-A or M6.6-B, or authorize
PR 1 implementation. The separate October 5 B record accepts only delivered B/ADR-0044/0048.
The [Pre-X1 documentation direction](../evidence/m6.6-species-aware-husbandry/README.md#pre-x1-documentation-direction)
binds this bounded documentation amendment under ADR-0028; it does not accept ADR-0045/0046/0047
or future implementation. The supplied owner reconciliation instruction is retained as authority;
no missing audit transcript or review evidence is reconstructed.

The extension remains Proposed and unimplemented. This Pre-X1 reconciliation prepares the
implementation contracts for owner review; X1 has not started. Future implementation qualification
and explicit owner acceptance govern ADR promotion under repository policy, not architecture-review
conclusions alone. Accepted ADR-0044/0048 and the historical M6.6-A acceptance caveat are unchanged.
