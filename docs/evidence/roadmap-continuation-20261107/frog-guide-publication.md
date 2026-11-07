# Frog Care Guides — bounded owner publication decision

Status: prepared November 7, 2026; **publication not authorized or performed**. The
combined deployment included guide support, not the two guide records. This note
reuses the [X5 source review](../m6.6-species-aware-husbandry/x5-amphibian-reference/sources.md)
and qualified importer; no source retrieval or production inspection was repeated.

## Exact proposal

Authorize one atomic publication of
[`reference/care-guides/reviewed-amphibians-v1.json`](../../../reference/care-guides/reviewed-amphibians-v1.json)
at SHA-256 **`441e3d03e41072a4a307ae90b136adf3828fc18a2353f64b038cef6308839e66`**.
The bytes were rehashed for this decision note. The bundle contains two version-1
guides, five source pages from three publishers, and 42 claims:

| Exact accepted species | Recorded identity qualification | Bundle content |
| --- | --- | --- |
| *Pelodryas caerulea* — White's tree frog | iNaturalist species 1633145; sources also use the reviewed synonym *Litoria caerulea* | 4 sources, 26 claims |
| *Ceratophrys cranwelli* — Cranwell's horned frog | iNaturalist species 22844 | 1 source, 16 claims |

Before any authorized write, each must resolve to **exactly one existing Care Keeper
taxon UUID** with the exact scientific name and amphibian group, `accepted` status,
`selected` state, species rank, Amphibia classification/ancestry, and at least one
provider reference with **every** provider reference qualified. These are the
[importer's existing conditions](../../../src/snaketracker/infrastructure/taxonomy/care_guides.py).
Current production taxon eligibility has not been rechecked by this documentation
task. Missing, ambiguous or unqualified identity stops the whole import. No
common-name, synonym-only, genus, hybrid or approximate substitution; no taxonomy
import, silent relinking or new taxon UUID is included in this decision.

## Applicability and rights being accepted

- Royal Veterinary College's December 2024 White's Tree Frog sheet and three NSW
  Department of Education pages apply to the reviewed White's tree frog identity.
  NSW's school/captive context remains visible; its three pages count as one
  publisher. Separate temperature measurement locations, UVB/lighting positions,
  life stages and differing adult feeding guidance are retained, not averaged.
- Tree of Life Exotic Pet Medical Center explicitly includes *C. cranwelli* in a
  broader Pacman-frog source. All Cranwell care positions remain **Single source**;
  the guide does not extend to *C. ornata*, *C. cornuta*, hybrids or all Frogs.
- These are post-metamorphic captive-care references, not tadpole/breeding guidance.
  Unsupported values, doses and other unknowns remain unavailable; warnings and
  source-specific context stay attached. Taxonomic and wild-ecology references are
  not independent husbandry corroboration.
- Publication is limited to the bundle's original concise paraphrases, structured
  facts and source links. RVC and Tree of Life did not supply unrestricted
  redistribution permission in the reviewed material; Tree of Life reserves rights.
  NSW attribution does not authorize republication of an entire article. No source
  article, PDF, photograph, illustration or logo is included, and no publisher
  endorsement is implied. The original source review records the RVC direct-download
  403 and date-precision limits; this note does not invent a fresh source check or
  legal clearance.

## Expected database effect and stopping conditions

For the first import of both previously unpublished versions:

| Global reference table | Expected change |
| --- | --- |
| `care_guide_versions` | 2 immutable version rows |
| `care_guide_sources` | 5 source rows |
| `care_guide_claims` | 42 claim rows |
| `care_guide_current` | 2 current-version pointers |

The existing operator entry point validates the bundle without `--apply`; an
authorized write additionally requires an explicit absolute existing database path.
It validates exact taxa and immutable version hashes within one transaction.
Identical retained versions are idempotent; changed version-1 content is rejected
and requires a new reviewed version. Existing guide content is preserved.

There is **no** Animal, household, care-event, attachment, species-link, schedule or
reminder mutation; no Natural History publication, migration or remote fetch is part
of this operation. Eligible linked Animals can display the new local guides and
Smart Care can offer applicable reviewed feeding suggestions. Existing schedules
remain authoritative until a keeper separately reviews and explicitly confirms a
change. The earlier [X5 qualification](../m6.6-species-aware-husbandry/x5-amphibian-reference/README.md)
already covers idempotence, atomic rejection and unchanged non-guide tables; it is
reused rather than rerun here.

**Smallest owner decision:** approve these exact two version-1 guides, source/rights
limits and reference-only changes for one controlled import, conditional on the
existing exact-taxon checks; or leave them unpublished. Approval of code, deployment
or M6.6 acceptance alone is not this publication authorization. Only an actually
successful import and verification may be reported as content being live.
