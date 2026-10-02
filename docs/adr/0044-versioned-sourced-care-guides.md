# ADR-0044: Versioned sourced Care Guides are global reference data

Status: Proposed for M6.6-B owner review

Decision date: 2026-09-27

## Context

ADR-0038 requires versioned curated husbandry reference profiles with provenance and no silent
schedule changes. ADR-0043 assigns stable Care Keeper taxon IDs and separates global reference
records from household Animal events. M6.6-B must preserve the actual positions of independent
sources, including disagreement, without turning general guidance into a household fact.

## Decision

Reviewed Care Guides attach to the existing global `taxa.taxon_id`. `care_guide_versions` contains
an immutable, digest-identified snapshot for each positive version; `care_guide_current` is the
only movable pointer. Version-specific source and claim tables retain publisher, title, URL,
provider ID where known, source type, retrieval/review/publication times, semantic fact key,
text or structured numeric value/range, canonical unit, qualifier, life stage, context, caution,
scope, and source relationship. Database triggers prevent changing or deleting reviewed versions,
sources, and claims. A future correction is a new reviewed version.

An operator imports a bounded, reviewed JSON bundle. Pydantic validates every guide, source,
claim, unit, numeric bound, HTTPS URL, and relationship before any write. In one database
transaction the importer resolves exact existing Care Keeper taxa, rejects unknown/ambiguous
taxa, rejects changed historical versions and version gaps, inserts new versions, and moves
current pointers. Repeating identical content is a no-op. It never writes household tables or
domain events. The browser has read-only guide routes and no guide-upload form.

Each source has its own claim position. Same semantic key and context from distinct publishers
with equal structured values and qualifiers is **Corroborated**. One publisher is **Single source**.
Different positions are **Sources differ**, displayed separately. These are deterministic support
labels, not an AI confidence score or proof of scientific certainty. Unavailable guidance is
explicit; values are not extrapolated, averaged, or widened. Plant toxicity retains the species
scope of its source; cat/dog toxicity cannot establish reptile or bioactive suitability.

The guide read path uses only local SQLite and the saved taxon cache. Provider failure cannot
make a saved guide disappear. Animal and enclosure-plant views show only a link to the guide;
there is no write path to schedules, reminders, care history, Inventory, Today, or Calendar.
Jinja escapes imported text; source links require HTTPS, use `noopener noreferrer`, and do not
add remote scripts, styles, or CSP exceptions. No household data is sent to guide sources.

## Consequences

- Guide version history and source changes remain inspectable even after the current pointer moves.
- Existing taxonomy cache entries must be present before import; the guide import cannot create
  or silently identify a taxon.
- A migration to revision `0023_sourced_care_guides` is additive. Downgrade is blocked once
  reviewed versions exist; recovery uses the verified pre-migration encrypted backup or a
  forward correction. No production restore-over is permitted during qualification.
- Source reviews are human curation. Source reputation and a shared paraphrase do not guarantee
  clinical consensus; future review can add new sources or new versions.

## Review boundary

This ADR proposes M6.6-B only. M6.6-C keeper-confirmed suggestions, M6.6-D bioactive care,
OPS-B, and M7 are outside this decision. The ADR remains Proposed until owner acceptance.
