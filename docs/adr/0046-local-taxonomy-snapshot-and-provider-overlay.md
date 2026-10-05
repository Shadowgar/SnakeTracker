# ADR-0046: Permanent taxon identity with replaceable reference generations

Status: Proposed
Decision date: 2026-10-01

## Context

[ADR-0043](0043-universal-species-directory.md) establishes Care Keeper taxon UUIDs and provider
boundaries. A broad local snapshot must not make those identities disposable. Animal links,
Enclosure Plants and immutable Care Guide versions already reference taxa; a rollback cannot
hide a taxon introduced after the rollback generation was built. Live discoveries can also occur
while a snapshot is staging.

## Decision

### Permanent Care Keeper Taxon Identity Catalog

Keep a generation-independent catalog containing the Care Keeper UUID, namespaced provider-ID
mappings `(provider, provider_taxon_id)`, mapping state/resolution provenance, and useful retained
identity labels/status needed to resolve durable references. X2 owns selected scientific/common
names, classification/hierarchy, provider taxonomy/status evidence and taxonomic provenance/
freshness. Animal taxon links, Enclosure Plants, media, Care Guides and X3 content references point
to this catalog, never to an active generation row. UUID-only retention is insufficient.
Once referenced, an identity must remain locally resolvable even when missing from the active
snapshot. Historical mappings and alias/conflict decisions remain auditable; ambiguous provider
split/lump replacements require explicit resolution and never silently relink household data.

Exact provider mappings reuse their UUID through transactional get-or-create with unique
namespaced mappings. Scientific/common names alone do not prove identity: homonyms and
cross-provider matches are review candidates, not automatic merges. Missing snapshot entries
mean absent reference content, not deletion. Inactive/synonymous identities retain explicit state.
Generation rollback or cleanup never removes catalog identities/mappings or their durable links.

### Generation-scoped content and durable live overlay

Use the official iNaturalist
[Taxonomy DarwinCore Archive](https://www.inaturalist.org/pages/developers) for indexed, replaceable
hierarchy/ancestry, common-name snapshots, search structures, snapshot metadata and regenerable
provider facts keyed to catalog UUIDs. Reference ancestry may include taxa with no enabled Animal
group; taxonomy existence is independent of registration eligibility under
[ADR-0045](0045-extensible-animal-capability-evolution.md).
Qualified taxon-to-workflow-group mappings belong to X2; profile-to-group membership, readable
profiles and registration policy belong to X1. Mapping cannot enable a group or profile. Reference-
only Amphibia may exist before X4, with no Animal registration or Care Guide coverage implied.

The bounded live overlay is independent of the active snapshot pointer. It retains source,
provider ID, retrieval time, source-effective/snapshot time when known, and monotone local revision.
Snapshot date, retrieval date and import date are distinct. Older snapshot facts cannot overwrite
fresher overlay facts; select by comparable source freshness, retain conflicts/unknown ordering for
review, and never use a later import date as evidence of fresher source content. Active reads/search
combine generation content, durable overlay and catalog fallback. Referenced taxa missing from
the generation remain searchable by retained identity labels and resolvable with honest missing
reference detail. Local assets, guide versions and image preferences are not generation rollback data.

### Import, reconciliation and promotion

While A is active, B builds without blocking ordinary local reads. Import reserves/reuses permanent
UUIDs; only replaceable content is staged. A live discovery transaction creates/maps its permanent
identity and publishes its overlay/search delta atomically. Before B promotion, reconcile all
catalog/overlay revisions since B's starting watermark, including discoveries absent from B.

Use bounded SQLite writer transactions shared by identity/overlay publication and promotion:
capture a final revision cutoff within the transaction, reconcile deltas through that cutoff, verify
every durable reference resolves and the combined search includes these identities, then atomically
activate B and its reconciled search watermark. If reconciliation exceeds the bound, abort/defer
promotion and keep A active. Writers after transaction completion publish against the new active
generation;
they cannot write only to discarded A search state. An import failure may leave harmless unreferenced
catalog identities, never a dangling durable link. Name/mapping conflicts block affected promotion
until explicitly resolved; an unrelated live discovery must not be lost.

Rollback changes only the active **reference generation** and its search pointer, under the same
serialization/reconciliation protocol. It does not revert the catalog, live overlay or household
data. Cleanup removes expired generation content/indexes only, respecting rollback/backup retention.
The [refresh runbook](../operations/taxonomy-snapshot-refresh.md) owns operational steps.

### X3 interface and migration boundary

Application-owned local ports resolve a permanent UUID, its selected taxonomy summary, qualified
workflow-group mappings, selected taxonomic provenance and source associations. X3 may display
these results but cannot independently choose identity, names or hierarchy. X3's source association
→ retained content version → publication/withdrawal selection attaches to that UUID. A generation
may record acquisition context only: it is never X3's identity, required FK, publication selector
or cleanup dependency. Rolling B back to A must leave post-A Natural History usable.

X2 has its own migration/release to replace restrictive current parent-table assumptions. Preserve
existing UUIDs, Animal/Plant links, names/mappings, image metadata, guide versions, sources/claims
and immutable-guide triggers. X3's separate additive migration follows accepted X2; do not build
a universal source/version framework in X2 merely to reduce migration count.

Indexed local taxonomy search covers qualified scientific/common names, supported aliases/synonyms
and classification, combining active content with overlay/catalog fallback. Household-private FTS
is separate; Natural History prose is not initially indexed. Initial import can be a bounded
operator workflow, without new queued workload, distributed locks or another queue.

Development can use synthetic fixtures. Production archive import requires actual archive,
intended-use, provenance and attribution/rights qualification; no CC0 assertion follows merely
from availability. Before production-sized import, measure database/generation/index size, WAL,
backup scratch high water, memory, duration, restore compatibility/replay and normal-duty impact
under the [backup release gates](../operations/backup-and-restoration.md#extension-release-gates).

## Qualification and consequences

`AT-TAXBAS-01` must prove:

1. A lacks a taxon; B introduces it; an Animal links to its permanent UUID; rollback to A preserves
   local identity/link resolution and search fallback. Repeat for Plant and Care Guide references.
2. Live discovery during B staging survives reconciliation/promotion and remains searchable and
   resolvable, including a writer at the promotion boundary and concurrent duplicate mapping requests.
3. Cleanup cannot delete referenced permanent identities, mappings, links, guide versions or assets.
4. Homonyms, namespaced IDs, split/lump conflicts, absent entries and older-snapshot/fresher-overlay
   ordering follow these rules. Failed promotion leaves A usable.

Local indexed search, bounded providers and manual entry follow ADR-0043. Ordinary Animal profiles
perform zero outbound provider/network calls; enrichment/download runs only in an explicit bounded
workflow outside ordinary rendering. Pi cold/warm search, import, storage, CPU and memory evidence
is required; the [controlling plan](../plans/2026-10-01-extensible-animal-and-species-platform.md)
links existing backup, migration, security and compatibility governance.
