# ADR-0043: Own Taxon Identity and Isolate External Species Providers

Status: Proposed for M6.6-A owner review

Decision date: 2026-09-13

## Context

M6.6 introduces biological reference lookups for snakes, lizards, spiders, scorpions, and plants.
Provider names, identifiers, classifications, availability, quotas, and licences can change. These
reference records must not become household authority, rewrite immutable Animal history, disclose
household data, or make ordinary Animal pages depend on the network.

## Decision

Care Keeper assigns every cached taxon an opaque internal UUID. Provider identifiers are mappings
on that record and never its primary identity. Global reference tables own normalized taxa, names,
provider mappings, provenance, refresh state, and permitted image metadata. They are not household
event streams.

The household fact that an Animal is linked to an internal taxon is an append-only
`animal.taxon_linked` event on the Animal stream. It snapshots the confirmed display identity and
provider provenance. A later keeper-confirmed link supersedes current projected state without
rewriting earlier registrations or links. No legacy free-text species is matched automatically.

One provider port returns normalized, validated search/detail results. M6.6-A uses iNaturalist's
public taxon autocomplete as its live discovery adapter because it provides useful common-name,
scientific-name, synonym-match, and broad-group results. Requests send only query text and the
selected biological group; they never send identity, household, Animal, enclosure, care, financial,
attachment, or account data. Catalogue of Life/ChecklistBank and GBIF remain eligible open
backbone/enrichment adapters after mapping and relevance qualification. Care Keeper continues to
work with only its cache and manual species text.

Reptile Database, World Spider Catalog, Trefle, Perenual, Kindwise plant.id, and Kew POWO are not
required for M6.6-A. Their adapters remain disabled unless API access, licence, attribution,
commercial use, and caching/redistribution rights are affirmatively compatible. A technically
queryable site is not permission to scrape or mirror it.

Search uses a minimum two-character query, a client debounce, request cancellation/deduplication,
local-cache-first results, and a bounded provider request only when needed. Successful normalized
records use a 30-day freshness window. Stale records remain available and visibly stale during an
outage; ordinary Animal/profile reads never refresh synchronously. Provider calls have a short
timeout, no automatic retry within an interactive request, bounded response size, fixed HTTPS host,
JSON content requirement, schema and length validation, and explicit handling for quota/rate-limit
responses. Background refresh/retry may be added later only with bounded backoff and quotas.

Provider credentials, if a future adapter needs them, come from runtime secrets and never source,
URLs, logs, browser responses, events, or backups. The primary M6.6-A adapter requires no key.

Accepted-name and classification changes update reference metadata and retain prior names as
searchable synonyms. They do not change the internal taxon UUID or historical household-event
snapshots. Conflicting provider mappings are retained with provenance rather than silently merged.
Unknown fields stay unknown.

Only image metadata with a known source, creator/attribution, and an explicitly permitted licence
may be retained or rendered. M6.6-A permits `CC0`, `CC BY`, and `CC BY-SA` metadata and uses a local
placeholder for missing, incompatible, or ambiguous licences. Remote provider HTML, scripts, and
arbitrary URLs are never rendered or proxied. The production CSP remains unchanged.

External taxonomy is reference knowledge only. It cannot create care guidance, husbandry facts,
schedules, reminders, or household decisions. Those boundaries require later M6.6 tranches and
keeper confirmation.

## Consequences

- Animal creation and legacy linking remain usable offline or during quota/provider failure.
- Selected taxon identity and profile display remain locally available.
- Taxonomic change is auditable without making provider history household event noise.
- A provider migration does not require changing Animal links or making its identifiers canonical.
- Live discovery can be less complete than a paid/specialist source; that is preferable to unclear
  rights or a mandatory commercial dependency.
- The normalized cache and provider response boundary require additive schema, migration,
  deterministic fixtures, outage tests, and explicit operational observability.

## Alternatives considered

### Use a GBIF, Catalogue of Life, or iNaturalist identifier as the primary key

Rejected because providers can merge, split, deprecate, or remap records, and no one provider
covers Care Keeper's desired user experience and licensing boundary permanently.

### Store all provider records as household events

Rejected because reference refreshes are not household decisions and would create unrelated event
volume. Only keeper-confirmed Animal linkage belongs in household history.

### Require a specialist or paid provider

Rejected because registration must work without a subscription, credential, network, or specialist
redistribution grant.

### Copy unknown-licence representative images

Rejected. A local placeholder preserves usability without assuming copyright permission.

## Review boundary

This ADR authorizes only M6.6-A directory, caching, autocomplete, manual fallback, plant reference
browsing, and Animal linking. It does not authorize care guides, suggested schedules, bioactive
enclosures, plant ownership/watering, M7 work, or production acceptance.
