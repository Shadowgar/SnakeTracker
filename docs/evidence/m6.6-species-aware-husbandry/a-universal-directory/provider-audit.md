# Current taxonomy/provider audit

Reviewed: 2026-09-14

Only provider-supplied taxonomy query text and group may cross the boundary. Care Keeper IDs,
accounts, households, Animal names, care/health history, enclosures, inventory, finances, notes,
and attachments do not.

| Provider | Current access/auth/quota | Rights, attribution, images, pricing | M6.6-A decision |
|---|---|---|---|
| [GBIF Species API](https://techdocs.gbif.org/en/openapi/v1/species) | Public read API; identifiable user agent requested; service applies load-dependent limits and `429` | Aggregated occurrence/media licences are record-specific; attribution/licence must travel with media | Eligible open backbone/enrichment adapter; not selected for live common-name autocomplete because tested relevance was weaker |
| [Catalogue of Life / ChecklistBank](https://www.catalogueoflife.org/tools/api) | Public ChecklistBank API; custom downloads can require a free GBIF account | COL site/content states CC BY 4.0 unless noted; contributing datasets can use CC0/CC BY and retain source conditions | Eligible accepted-name/synonym backbone and future enrichment; no bulk mirror needed for A |
| [iNaturalist](https://www.inaturalist.org/pages/api%2Brecommended%2Bpractices) | Public taxon reads; recommended about 1 request/second and 10,000/day; hard ceiling 100/minute and requested use at or below 60/minute; custom user agent | Observation/photo licences are per record and may be absent or restrictive; taxon text must retain provenance | Selected live discovery adapter. Cache normalized text/mappings; accept image metadata only for explicit CC0/CC BY/CC BY-SA, otherwise placeholder |
| [Reptile Database](https://www.reptile-database.org/data/index.html) | Web search and published checklist downloads; full dumps generally available to academic collaborators by request | Citation is requested; no sufficiently clear general production cache/redistribution grant was identified | No A adapter, scraping, or mirror. Candidate specialist link/enrichment only after permission/licence review |
| [World Spider Catalog](https://www.wsc.nmbe.ch/dataresources) | REST API requires membership/API key | Download advertised under CC BY-NC-SA 4.0; non-commercial/share-alike terms are unsuitable as an assumed general production cache licence | Disabled in A; do not bulk mirror. Revisit narrow lookup/link-out only with affirmative compatibility |
| [Trefle](https://docs.trefle.io/docs/guides/getting-started/) | API token required; documentation states 120 requests/minute while product material states a lower 60/minute tier | Free service/sponsorship tiers; beta/availability caveats; no sufficiently clear redistribution licence found | Disabled; not needed for plant registration/search |
| [Perenual](https://www.perenual.com/docs/api) | API key; free tier limited to 100 requests/day and limited data | Paid tiers advertise commercial use (reviewed prices: $59.99/month for 10,000/day, $139.99/month for 100,000/day) | Disabled paid enrichment; no subscription required |
| [Kindwise plant.id](https://www.kindwise.com/faq) | API key/credit service; 100 trial credits; identification/details consume credits | Paid identification pricing varies by volume; designed primarily for image identification rather than canonical taxonomy | Disabled; not a universal directory backbone |
| [Kew POWO](https://powo.science.kew.org/about) | Public reference website backed by WCVP; no supported general public API identified | Citation/source terms and image rights vary; identifiers/data can change | No scraping or direct adapter. Use authoritative link-out or mappings from licensed backbone data in a future enrichment review |

## Conclusion

iNaturalist currently gives the best bounded four-animal-group and plant autocomplete behavior,
including useful common-name and scientific-name matches. It is discovery, not Care Keeper
identity. Care Keeper stores its own UUID plus the iNaturalist mapping/provenance. Catalogue of
Life/ChecklistBank and GBIF remain compatible candidates for accepted-taxonomy reconciliation.
Manual entry and cached records are the mandatory fallback; paid or specialist APIs are never a
registration dependency.

No provider image is copied merely because its URL is returned. Unknown/unlicensed and
non-commercial-only media use a Care Keeper placeholder. No provider terms caused a CSP change.

## Owner-review Boa verification

On September 14, 2026, Care Keeper's live cache and the iNaturalist detail response for taxon
`32093` (`Boa constrictor`) were compared. The provider supplied default photo `588689904` from an
approved iNaturalist image hostname, but marked it `cc-by-nc`. The non-commercial restriction is
outside M6.6-A's approved `CC0`/`CC BY`/`CC BY-SA` set, so normalization intentionally removed all
eligible image fields and Care Keeper correctly offered the placeholder. This was not a missing
photo, hostname rejection, malformed record, or download/cache failure. Licensing and origin rules
were not loosened to make the Boa display an image.
