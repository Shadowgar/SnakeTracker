# ADR-0047: Natural History authority and immutable Care Guide coexistence

Status: Proposed
Decision date: 2026-10-01

## Context

[ADR-0043](0043-universal-species-directory.md) establishes taxonomy identity;
[ADR-0046](0046-local-taxonomy-snapshot-and-provider-overlay.md) extends that foundation in X2.
Accepted [ADR-0044](0044-versioned-sourced-care-guides.md) owns reviewed captive Care Guides.
Immutable guide versions already contain biological/reference claims. X3 must coexist with them
without rewriting versions, duplicating authority or depending on a replaceable taxonomy generation.

## Decision

### Ownership and durable attachment

**Taxonomy owns identity/classification/names. Natural History owns descriptive biological content.**
X2 owns permanent Care Keeper taxon UUIDs, selected scientific/common names, hierarchy/classification,
provider mappings, taxonomy/status evidence and taxonomic provenance/freshness. X3 may display that
selected metadata through application-owned local ports; it cannot independently select taxon
identity, scientific name, common names or hierarchy.

X3 owns optional sourced descriptive prose and qualified biological Natural History claims, retained
content versions/provenance and publication/withdrawal selection. Attach its durable model to the
permanent UUID: taxon → source association → retained content version → publication selection.
Taxonomy generation is acquisition context only, never identity, a required FK, publication selector
or cleanup dependency. B → A generation rollback preserves content acquired after A. Missing or
withdrawn content is explicit; successful acquisition is not publication approval. No extra
household event stream is introduced. Taxa without an active Animal profile can have Natural History;
reference coverage does not enable registration or imply a reviewed Care Guide.

### Source strategy and publication gates

Prefer revision-specific Wikipedia acquisition for descriptions, retaining exact source/revision,
identity match, retrieval context and applicable attribution/license/modification handling. An
iNaturalist intermediary does not replace the actual Wikipedia origin. Sourced prose is not
automatically authoritative structured habitat, lifespan, diet, adult size or range. Display those
as structured facts only through a specifically qualified structured-claim source/workflow. Retain
geographic/life-stage/context qualifiers, origin, rights and disagreement; absent facts remain unknown.
Conservation/range claims need their own qualified sources and dataset/model context where applicable.

Development may use synthetic or qualified fixtures. Production publication requires source-specific
rights evidence: applicable Wikipedia text terms; Wikidata structured-data terms; iNaturalist rights
per material/source. Direct IUCN content remains unqualified until separately resolved. API access,
an archive's availability or owner approval cannot substitute for missing source rights. These are
engineering publication gates, not unsupported legal conclusions.

Taxonomy, content and media keep separate domain adapters. Future transport coordination shares
application User-Agent, allowed endpoints/hosts, timeouts/response bounds, aggregate rate/concurrency,
Retry-After, bounded retry, deduplication and privacy-safe telemetry. Each adapter cannot consume
the entire provider allowance independently. Before a second queued workload, likely X3 enrichment,
extend the existing SQLite durable queue with typed claiming and lease recovery, payload validation,
handlers and retry semantics. No Redis, broker or parallel queue is justified without measured need.
These prerequisites are future work, not X1 implementation.

### Immutable Care Guide coexistence

Captive temperature, humidity, UVB, substrate, feeding intervals, enclosure and schedules remain
ADR-0044's responsibility under the [reviewed source policy](../operations/care-guide-sources.md).
Wild facts cannot generate husbandry rules, household history or reminders. Your Records remain
independently authoritative. Do not create a second Care Guide system or copy legacy claims into a
competing authoritative store. Immutable payloads, provenance and full detail remain available.

A small trusted semantic/context adapter may compare legacy and new biological claims by permanent
taxon, fact kind, life stage, wild/captive context, geography, sex, value/unit, qualifiers and actual
originating source. Equivalent qualified biological facts can display once with combined provenance.
An intermediary does not create an independent source: one origin reached twice counts once.
Different contexts stay distinct, true disagreements retain separate positions and unknown legacy
classifications remain in original guide context. A qualified guide-derived biological fact may
fill a missing Natural History display position with its original version/source; captive-care
claims remain Reviewed Captive Care. No stored claim or prior acceptance is changed by presentation.

### Ordinary reads and recovery

Overview remains compact; the dedicated Guides & Species Reference page separates locally available
Species Overview / Natural History, Reviewed Captive Care and Sources. Ordinary Animal/reference
and local-image reads make zero outbound calls, trigger no acquisition and mutate no household,
domain, projection, schedule, reminder, notification intent, Inventory, expense, taxon catalog,
mapping, generation, overlay, search, Natural History, publication, acquisition-job, reference-image
cache or keeper-media state. Existing authentication/session/security bookkeeping remains permitted,
including last-seen, CSRF, rotation and security audit under current policy. This is not a zero-SQL-
write contract or a reason to weaken authentication.

Missing optional content renders honestly and locally. Keeper attachments are mandatory recovery
content; reference-media metadata/provenance are durable. Cached species bytes may be reacquirable
only under an accepted recovery contract. Missing bytes use the keeper photo, else an eligible
bundled illustration/group fallback, while taxonomy/text still render: no hotlink, broken remote
image or page-read recovery acquisition. Natural History prose is excluded from initial global
taxonomy search and from household-private FTS.

## Qualification and consequences

`AT-NATHIST-01` covers source/version integrity, publication/withdrawal, generation independence,
equivalent/missing/conflicting guide claims, contextual classification, actual-origin deduplication,
immutable-guide preservation and rights/provenance. **Boa imperator / iNaturalist 539399**, linked
with no reviewed captive-care guide, is mandatory: useful qualified local description with taxonomy-
owned names/classification and explicit missing-guide wording, including provider outage.
`AT-PROFILE-REF-01` instruments zero outbound calls/acquisition and forbidden-state changes for
warm, missing-image and cold optional-reference states while permitting security bookkeeping.
One `AT-PRODCOMP-01` framework adds these X3 cases to shared household/identity/replay invariants.
X3 has a separate additive migration after accepted X2. See the
[controlling plan](../plans/2026-10-01-extensible-animal-and-species-platform.md).
