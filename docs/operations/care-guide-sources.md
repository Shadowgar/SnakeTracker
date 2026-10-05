# Reviewed Care Guide source policy and import

Care Guides are reference knowledge, not records or instructions for one keeper's Animal,
Enclosure, Inventory, or schedule. The source bundle is structured reviewed data, not copied
guides. Do not paste substantial source prose, scrape sites against their terms, or assume a public
page grants unrestricted API redistribution rights. If an automated source cannot meet legal and
technical conditions, use this operator-reviewed import path. Ordinary viewing makes no live
provider request.

## Source selection

Prefer veterinary schools and institutions, zoos, universities, botanical institutions,
government and scientific resources, and recognized herpetological or arachnid organizations.
Commercial specialist husbandry sources can supplement these when clearly identified. Review
specific claims and context, not just the organization's reputation. Avoid anonymous blogs,
AI-generated guides, unsourced aggregators, and SEO content farms. A source may describe wild
natural history rather than captive care; the claim must say which. Record the actual affected
species for toxicity, and never generalize a cat/dog assessment to reptiles or bioactive use.

Every material claim has a source ID, concise paraphrase or structured numeric value, scope,
retrieval date, and review date. Use canonical Celsius, percent, centimetres, days, years, or
hours for numeric claims. Preserve life stage, day/night or other context. If two source positions
differ, retain both; do not average them. The deterministic UI states are **Single source** (one
publisher), **Corroborated** (at least two independent publishers with the same contextual
position), and **Sources differ** (different values or qualifications). These are support counts,
not clinical confidence. Older publication dates remain visible and are reviewed, not
automatically declared wrong. Missing facts remain unavailable.

## Reviewed bundle

The versioned [M6.6-B bundle](../../reference/care-guides/reviewed-v1.json) contains 5 public taxa,
8 reviewed sources, and 30 sourced claims. It covers `Python regius`, `Pogona vitticeps`,
`Avicularia avicularia`, `Pandinus imperator`, and `Monstera deliciosa`. RVC and RSPCA provide
distinct bearded-dragon basking ranges; the UI preserves both. RVC and RSPCA separately support
daily UVB lighting. The source facts, publication context, and URLs were checked September 27,
2026. No private production data is in the bundle.

The separate [Boa constrictor version 1 bundle](../../reference/care-guides/reviewed-boa-constrictor-v1.json)
adds one taxon, seven source pages from two publishers, and 34 sourced claims. The existing
`reviewed-v1.json` bytes are preserved so its reviewed versions remain idempotent. Source text was
retrieved and reviewed on October 1, 2026. ADR-0044 is Accepted and M6.6-B is Accepted / Complete
as of the [October 5 owner record](../evidence/m6.6-species-aware-husbandry/b-sourced-care-guides/README.md#owner-acceptance).

Royal Veterinary College's *Boa Constrictor Care* explicitly identifies `Boa constrictor
constrictor`. Its captive care positions cover temperature, qualitative humidity, enclosure/hides,
UVB, rodents, water, substrate safety, lifespan, and hygiene. The official PDF currently returns
HTTP 403 to direct retrieval in this environment; its publisher-hosted indexed text was retrieved
and checked for every included position. No unverified PDF publication date is inferred from the
filename. ReptiFiles' specialist genus guide explicitly distinguishes `Boa constrictor` from
`Boa imperator` and covers the target species as well as related boas. Its six separate pages
provide species/locality context, temperature, humidity, feeding, lighting, and enclosure positions.
Claims retain that broader source context and do not identify an Animal's locality or subspecies.

Cool-end temperature, ambient humidity, overnight guidance, and UVB positions retain **Sources
differ**. RVC's basking spot and ReptiFiles' basking air values keep distinct measurement contexts.
Whole-rodent feeding and daily fresh water are **Corroborated** by the two publishers; other
contextual positions remain **Single source**. The feeding intervals are reference outlines with
life stage and body-condition qualifications. No percentage of support, average range, household
schedule, or Animal-specific recommendation is generated.

Validate the Boa bundle without a database write:

```sh
uv run python -m snaketracker.operations.import_care_guides \
  reference/care-guides/reviewed-boa-constrictor-v1.json
```

For an explicitly authorized import into a verified isolated migrated database, use that bundle
with the same `--database /absolute/path/to/isolated.sqlite3 --apply` arguments documented below.
The cache must contain exactly one existing `snake` taxon named `Boa constrictor`; a cache entry
for `Boa imperator` does not satisfy this requirement. The import changes only the four global
Care Guide reference tables and preserves all household records and events.

Validate without writing:

```sh
uv run python -m snaketracker.operations.import_care_guides reference/care-guides/reviewed-v1.json
```

After migrating a **verified isolated restore** and confirming every named taxon already exists
in its Care Keeper taxon cache, apply only there first:

```sh
uv run python -m snaketracker.operations.import_care_guides \
  reference/care-guides/reviewed-v1.json --database /absolute/path/to/isolated.sqlite3 --apply
```

The importer validates the complete bundle before changing the current guide data, inserts all
new versions atomically, and treats the same reviewed version as an idempotent no-op. A changed
payload under an existing version is rejected. The command cannot create taxa or household facts.
Use the existing directory provider/cache path separately if a public taxon must be cached;
verify the exact scientific identity before importing. Never infer a taxon ID from a household
Animal name. Production promotion requires the milestone's migration, quality, browser, backup,
and data-integrity gates. Once a reviewed version exists, downgrade is intentionally blocked;
restore rehearsal uses an isolated target, and production recovery follows ADR-0026.

## Future Natural History coexistence

[ADR-0047](../adr/0047-natural-history-reference-boundary.md) remains Proposed. X2 taxonomy selects
identity, names/classification and taxonomic provenance; X3 selects sourced descriptive biological
content versions and publication/withdrawal. Wild facts do not establish captive-care guidance.
Existing guide payloads, full detail and provenance remain immutable; X3 is not another Care Guide
system and cannot rewrite or bulk-copy historical claims into a competing authority.

A small trusted presentation adapter may compare qualified biological claims by taxon, fact kind,
life stage, wild/captive context, geography, sex, value/unit, qualifiers and actual originating source.
Equivalent contextual facts display once with combined provenance. One originating source through
two intermediaries counts once. Distinct contexts and true disagreements remain separate; unknown
legacy classifications retain original guide context. Reviewed Captive Care retains its own authority.
Sourced prose does not become structured habitat/lifespan/diet/size/range without a qualified claim
source/workflow. Revision-specific acquisition, actual-origin rights/attribution/modification evidence
and explicit publication selection qualify future content; acquisition alone is insufficient.
