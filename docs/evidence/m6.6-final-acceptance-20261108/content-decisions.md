# M6.6 reference-content decisions — November 8, 2026

**Owner decisions pending. No content was imported, published or deferred by this
documentation task.** The deployed reference features and their retained development
qualification do not establish production content publication or milestone acceptance.
This note reuses existing source reviews; only local bundle bytes and records were
checked again.

## Two Frog Care Guides

Recommend approving the existing [bounded publication proposal](../roadmap-continuation-20261107/frog-guide-publication.md)
after the owner's source/design review, conditional on the importer's exact live-taxon
checks. Alternatively, leave both unpublished. Either choice requires an explicit
owner record; deployment or M6.6 acceptance alone is not publication authorization.

The exact [reviewed bundle](../../../reference/care-guides/reviewed-amphibians-v1.json)
was rehashed locally on November 8:
`441e3d03e41072a4a307ae90b136adf3828fc18a2353f64b038cef6308839e66` (SHA-256).

| Exact species; version | Retained identity qualification | Sources / claims |
| --- | --- | --- |
| *Pelodryas caerulea*; 1 | iNaturalist 1633145; reviewed sources also use *Litoria caerulea* | 4 / 26 |
| *Ceratophrys cranwelli*; 1 | iNaturalist 22844 | 1 / 16 |

This adds **two guides, five source pages from three originating publishers and 42
claims**. For a first import, expected global-reference changes are two immutable
`care_guide_versions`, five `care_guide_sources`, 42 `care_guide_claims` and two
`care_guide_current` pointers. An identical retained version is idempotent; altered
version-1 bytes are rejected. No other species or guide version is authorized by
this proposal.

The [qualified importer](../../../src/snaketracker/infrastructure/taxonomy/care_guides.py)
must resolve each exact name to exactly one existing amphibian taxon UUID: accepted,
selected, species rank, Amphibia classification/ancestry, at least one provider
reference and every provider reference qualified. Missing or ambiguous identity stops
the atomic import. No providerless amphibian bypass, approximate/common-name or
synonym-only substitution, new UUID, taxonomy import or Animal relinking is included.
Production eligibility has **not** been rechecked in this task.

Preserve the complete [November 2 source and rights review](../m6.6-species-aware-husbandry/x5-amphibian-reference/sources.md):

- RVC's December 2024 sheet and three NSW Education pages support White's tree frog;
  the NSW pages are one origin with school/captive context. Keep differing temperature
  measurement locations, lighting scopes, life stages and adult feeding positions
  separate. The RVC direct-download 403 and date-precision limits remain recorded.
- Tree of Life explicitly includes *C. cranwelli* in a broader Pacman-frog source;
  every Cranwell position remains **Single source**. Do not extend it to *C. ornata*,
  *C. cornuta*, hybrids or all Frogs. Taxonomy and wild ecology are not husbandry
  corroboration. Scope is post-metamorphic captive care; unsupported values, doses,
  tadpole and breeding guidance remain unavailable.
- Publish only the bundle's original concise paraphrases, structured facts and links.
  No full article/PDF, photograph, illustration or logo is included. RVC and Tree of
  Life supplied no unrestricted redistribution grant in the reviewed material; Tree
  of Life reserves rights, and NSW attribution does not license whole articles.
  Owner approval supplies neither legal clearance nor publisher endorsement.

The operation changes no Animal, household, event, attachment, species link, schedule
or reminder. It includes no Natural History publication or remote fetch on page views.
Eligible Animals can display local guides and Smart Care can offer supported feeding
suggestions; schedules change only through a keeper's separate explicit confirmation.
Reuse [X5 qualification](../m6.6-species-aware-husbandry/x5-amphibian-reference/README.md);
only a successful separately authorized import and verification can establish that
the guides are live.

## X2 full taxonomy archive

The local catalog, stable UUIDs, provider overlay and local search are implemented.
The [X2 receipt](../x2-local-taxonomy/README.md) qualifies **10,001 synthetic rows** on
the Pi; it expressly does not qualify a real full archive or production capacity.
Deployment and the November 8 recovery evidence do not replace that missing work.

The frozen [M6.6 checklist](../../roadmap/milestones.md#pre-m66-c-extension--x1-through-x5)
explicitly requires actual-archive intended use, provenance/rights and production-sized
Pi search, database/generation/index/WAL, backup scratch/memory/duration, restore/replay
and normal-duty measurements. The controlling [platform plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md)
and [ADR-0046](../../adr/0046-local-taxonomy-snapshot-and-provider-overlay.md) preserve
those gates. This requirement is **genuinely incomplete**, not already deferred.

Recommend an explicit owner scope disposition if the bounded deployed catalog is
sufficient for this release: defer full-archive acquisition, qualification and import
to a separately authorized work item, with its rights and operational gates intact.
That would require the normal approved roadmap/governance change; this note cannot
waive the frozen requirement or call M6.6 complete. Otherwise retain the item as an
acceptance blocker and separately authorize qualification. Neither choice authorizes
a download, import or migration now.

## X3 Natural History

Permanent-UUID source associations, immutable versions, publication/withdrawal and
local-only reading are implemented and supported by [X3 qualification](../m6.6-species-aware-husbandry/x3-natural-history/README.md).
The required *Boa imperator* / iNaturalist 539399 example was demonstrated without a
reviewed Care Guide. Its Wikipedia revision 1380867968 adaptation retains authors,
CC BY-SA 4.0 and modification notices, but is **development content**, not a
production-qualified publication. Production excludes `rights_scope=development`.

Recommend keeping that fixture unpublished and explicitly recording any deferral of
production prose to a separate content decision. [The operator policy](../../operations/natural-history.md)
requires source-specific production rights evidence and exact revision/hash selection;
changing a scope label or approving M6.6 cannot substitute for that review. No direct
IUCN or third-party text becomes qualified merely through an accessible URL. The
[ADR-0047 boundary](../../adr/0047-natural-history-reference-boundary.md) remains intact.

Treat functionality qualification and unpublished content as separate findings. Owner
disposition must address applicable production-publication acceptance gates in the
controlling plan; an unaccepted mandatory gate remains open until satisfied or validly
amended. Already documented deferrals of prose full-text search, speculative
profiles/providers and mass enrichment remain deferred; they do not authorize a new
deferral of the full-archive or publication gates.

| Decision requiring the owner | Current status |
| --- | --- |
| Publish the exact two-guide bundle under the conditions above, or keep it unpublished | Pending; no publication authorization |
| Complete full-archive qualification, or explicitly approve a bounded scope deferral through roadmap governance | Pending; frozen requirement remains incomplete |
| Keep Natural History prose unpublished with an explicit acceptance disposition, or authorize separate production-content qualification | Pending; development fixture remains ineligible for production |

No decision in this record constitutes formal M6.6 acceptance.
