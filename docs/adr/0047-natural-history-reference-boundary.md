# ADR-0047: Natural History authority and immutable Care Guide coexistence

Status: Proposed
Decision date: 2026-10-01

## Context

[ADR-0043](0043-universal-species-directory.md) owns taxonomy identity;
[ADR-0044](0044-versioned-sourced-care-guides.md) proposes reviewed captive Care Guides. Existing
immutable guide versions also contain biological/reference claims. New Natural History must
coexist with those claims without rewriting versions or presenting duplicate competing authorities.

## Decision

Add an optional global Species Overview / Natural History layer keyed to the permanent Care Keeper
taxon UUID. It owns sourced biological description, classification, common names, wild range,
habitat, activity, natural diet, adult size, life history and conservation. Each fact retains actual
publisher/source URL, retrieval/version context, applicable rights/attribution, and disagreement
state. A Wikipedia-origin summary obtained through iNaturalist is attributed/licensed to its actual
origin; API availability does not grant text reuse rights. Ranges retain dataset/model version and
licence. Absent facts remain unknown.

Captive temperature, humidity, UVB, substrate, feeding intervals, enclosure and schedule guidance
remain the responsibility of ADR-0044 and the
[reviewed guide source policy](../operations/care-guide-sources.md). Wild facts cannot generate
husbandry rules. Neither layer writes household Animals, history or reminders without an explicit
keeper action under existing contracts. Household Your Records remain independently authoritative.

### Presentation precedence

Taxonomy identity/classification uses the catalog and active reference selection under
[ADR-0046](0046-local-taxonomy-snapshot-and-provider-overlay.md). For biological facts, display an
available reviewed/sourced Natural History fact once in Species Overview. Suppress an equivalent
legacy guide biological claim from the compact profile summary, while preserving the immutable
version and its full detail/source view. If Natural History lacks that fact, a sourced legacy guide
claim may appear once as a clearly labelled guide-derived biological reference with version/source.
No bulk copying of guide claims into a second authoritative store or destructive migration is allowed.

Different values, contexts or dates are not deduplicated as if equivalent: expose disagreement with
both sources and no silently synthesized winner. Captive-care claims remain in Reviewed Captive Care
even when they concern size/diet in a captive context. New imports classify claims by responsibility
and publish new guide versions where appropriate; old versions remain immutable. Presentation
deduplication changes no stored claim, evidence or owner acceptance.

Animal profiles show Your Records separately from locally available Species Overview, Reviewed
Captive Care and Sources. Rendering performs zero external provider/network calls, including image
retrieval; an explicit bounded enrichment workflow runs outside the ordinary read path.

## Qualification and consequences

`AT-NATHIST-01` covers equivalent, missing and conflicting legacy biological claims, captive-context
claims, immutable guide preservation, source/licence attribution and no household writes.
`AT-PROFILE-REF-01` checks labels and zero outbound calls for warm, missing-image and cold optional
reference states. See the [controlling plan](../plans/2026-10-01-extensible-animal-and-species-platform.md).
