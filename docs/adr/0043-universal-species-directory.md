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

One taxonomy-provider port returns normalized, validated search/detail results. M6.6-A uses iNaturalist's
public taxon autocomplete as its live discovery adapter because it provides useful common-name,
scientific-name, synonym-match, and broad-group results. Requests send only query text and the
selected biological group; they never send identity, household, Animal, enclosure, care, financial,
attachment, or account data. Catalogue of Life/ChecklistBank and GBIF remain eligible open
backbone/enrichment adapters after mapping and relevance qualification. A separate image-provider
port tries the selected iNaturalist taxon's eligible default photo, Wikimedia Commons, then GBIF.
It retains the provider record, source page, creator, licence, retrieval time, and normalized local
bytes. Care Keeper continues to work with only its cache and manual species text.

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
may be retained or rendered. In its current noncommercial deployment, M6.6-A permits `CC0`,
`CC BY`, `CC BY-SA`, `CC BY-NC`, and `CC BY-NC-SA`. All Rights Reserved, unknown, and `ND`
licences remain ineligible; local normalization may be a derivative, so no-derivatives terms need
separate evaluation before use. Revoked, incompatible, or ambiguous rights remove the image from
eligibility. Eligible bytes are fetched server-side only
from an HTTPS hostname allow-list, without redirects, under strict timeout, response-size,
content-type, decoded-format, pixel, and dimension limits. Care Keeper normalizes verified raster
content to WebP in one global local cache, records its checksum/retrieval metadata, and serves it
only from a same-origin authenticated route. Remote provider URLs are never embedded in keeper
pages, SVG is not accepted, and the production `img-src 'self'` and `script-src 'self'` policy is
unchanged.

Legacy Animal streams may contain `animal.reference_image_preference_changed`; those facts remain
valid history and are not rewritten. The owner-approved display policy now guarantees one visual
decision everywhere: the existing attachment-backed photo of the individual Animal, then an
eligible licensed species photograph, then a species illustration when one is available, then an
honestly labeled local biological-group illustration. A linked animal is no longer visually reduced
to an initial because a legacy preference is false. Uploading a personal photo immediately takes
priority and neither deletes nor rewrites global reference data.
Morph/variant and genetics/lineage remain free-text individual facts. Same-household values for the
same Care Keeper taxon may be offered as optional suggestions, but taxonomy never selects, infers,
normalizes, or erases them.

A linked Enclosure Plant does not use the Animal-specific opt-in preference. When its global taxon
has an eligible, verified local reference image, Plant Directory detail, Enclosure Plant detail,
and the compact Enclosure roster may display that image automatically with attribution and a clear
species-reference label. Manual or image-ineligible plants use the Care Keeper plant placeholder.
This remains global reference imagery and is not evidence that the pictured specimen is the
keeper's individual plant.

Keeper-facing static assets that implement this flow use a release-specific URL key. The PWA shell
uses the same asset generation, installs it before activation, takes control without requiring a
manual cache clear, and deletes older Care Keeper shell generations. Cache-first delivery is safe
only for URLs whose key changes when their bytes or behavior change.

The noncommercial allowance is a business-model condition, not a permanent assumption. Before a
paid, subscription-supported, ad-supported, commercially distributed, or otherwise monetized
release, every cached `cc-by-nc` and `cc-by-nc-sa` image must be located through retained licence
metadata and re-evaluated or removed before that change ships.

External taxonomy is reference knowledge only. It cannot create care guidance, husbandry facts,
schedules, reminders, or household decisions. Those boundaries require later M6.6 tranches and
keeper confirmation.

The M6.6-A owner-review amendment adds a separate household-owned plant instance inside exactly
one Enclosure. An enclosure plant may link to a Care Keeper taxon or retain a manual species/name;
the global provider identifier never becomes its identity. `enclosure.plant_added`,
`enclosure.plant_profile_changed`, and `enclosure.plant_removed` facts preserve its stable UUID,
placement, profile, and non-destructive lifecycle on the Enclosure stream. Moving an Animal does
not move these plants. This amendment does not authorize watering, care guidance, bioactive mode,
schedules, Today, Calendar, or reminders.

## Consequences

- Animal creation and legacy linking remain usable offline or during quota/provider failure.
- Selected taxon identity and profile display remain locally available.
- Licensed reference imagery remains attributable and locally deliverable without weakening CSP or
  exposing a provider URL to the browser.
- Individual-photo attachments remain household-isolated and take display priority over global
  reference imagery.
- Common linked species gain stable visual coverage without a browser dependency on a third-party
  host; unavailable providers degrade to a local, non-species-specific group illustration.
- Linked plants gain compact, attributable visual identity without a new downloader, attachment
  model, household preference event, or CSP allowance.
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

This ADR authorizes only M6.6-A directory, caching, autocomplete, manual fallback, Animal linking,
and basic Enclosure-owned plant roster/lifecycle. It does not authorize care guides, suggested
schedules, bioactive mode, plant watering/care automation, M7 work, or production acceptance.
