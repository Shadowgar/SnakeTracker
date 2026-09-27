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
