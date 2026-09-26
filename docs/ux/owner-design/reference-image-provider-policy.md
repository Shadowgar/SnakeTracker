# Reference-image provider and licence qualification

Qualification date: September 14, 2026. This policy implements the owner-approved noncommercial
image addendum while ADR-0043 remains Proposed.

## Provider cascade

1. Use an eligible default photograph returned with the selected iNaturalist taxon.
2. Query Wikimedia Commons by accepted scientific name and accept a result only when its title or
   description confirms that name.
3. Resolve the accepted name through GBIF and scan a bounded set of StillImage occurrence media.
4. If no candidate passes licence screening and the existing downloader/decoder boundary, consult
   the local species-illustration manifest, then use the local group illustration. The manifest is
   the extension point for future reviewed species-specific assets; it is intentionally empty while
   the common-species photo cascade provides coverage. No remote URL is placed in keeper HTML.

Provider calls identify Care Keeper, use fixed HTTPS API hosts, short timeouts, bounded payloads,
schema checks, and no household or animal facts. Failed lookups are negatively cached for one hour
when providers are unavailable and 30 days when no eligible match exists. Licensed bytes are
normalized to WebP (maximum 1600×1600), checksummed, and served through Care Keeper's authenticated
same-origin route.

## Licence policy

The current deployment is noncommercial. Eligible licences are CC0, CC BY, CC BY-SA, CC BY-NC,
and CC BY-NC-SA. Unknown terms, All Rights Reserved, CC BY-ND, and CC BY-NC-ND are rejected. Every
cached record retains provider, provider record ID, source page, creator, licence code/URL, and
retrieval date so NC assets can be found and re-evaluated before any future monetization or
commercial distribution.

Tiny attribution appears immediately below major species-reference presentations. Dense Today,
Calendar, Animals, Enclosures, Quick Log, and Search thumbnails link to the animal profile, where
full attribution is present. Personal keeper photos never show provider credits.

## Official provider review

- [iNaturalist developer guidance](https://www.inaturalist.org/pages/developers) and
  [API recommended practices](https://www.inaturalist.org/pages/api+recommended+practices) establish
  the public API/rate boundary; licence eligibility is checked per photo.
- [MediaWiki Imageinfo API](https://www.mediawiki.org/wiki/API:Imageinfo),
  [Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/licenses),
  and [Wikimedia API policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines)
  establish per-file metadata/attribution and considerate API use.
- [GBIF occurrence API](https://techdocs.gbif.org/en/openapi/v1/occurrence),
  [image cache API](https://techdocs.gbif.org/en/openapi/images), and
  [citation guidance](https://www.gbif.org/article/37tpGiBDc40oSAmKIWWC24/citation-guidelines)
  establish per-media rights/provenance and the bounded fixed-host image cache.
- Encyclopedia of Life was evaluated through its
  [data services](https://api.eol.org/docs/what-is-eol/data-services) and
  [API terms](https://eol.org/docs/what-is-eol/terms-of-use-for-eol-application-programming-interfaces).
  It is not activated because it adds registration/terms overhead without improving the
  representative coverage achieved by iNaturalist, Commons, and GBIF.

## Representative live-provider check

The bounded Commons provider returned an eligible, identified photograph for every target:

| Common name | Accepted name | Result licence |
| --- | --- | --- |
| Ball Python | *Python regius* | CC BY-SA |
| Boa Constrictor | *Boa constrictor* | CC BY-SA |
| Corn Snake | *Pantherophis guttatus* | CC BY-SA |
| Kingsnake | *Lampropeltis getula* | CC BY-SA |
| Leopard Gecko | *Eublepharis macularius* | CC0 |
| Crested Gecko | *Correlophus ciliatus* | CC BY |
| Bearded Dragon | *Pogona vitticeps* | CC0 |
| Bold Jumping Spider | *Phidippus audax* | CC0 |
| representative tarantula | *Grammostola rosea* | CC BY-SA |
| Emperor Scorpion | *Pandinus imperator* | CC0 |

The owner-identified current iNaturalist default for *Boa constrictor* taxon `32093` was also
rechecked: photo `588689904`, creator Nicolas Burnel, CC BY-NC, and an approved fixed iNaturalist
image host. It is eligible in the current deployment and takes precedence when that taxon is
selected. This is not hard-coded: current provider metadata still has to pass every transport,
decoding, size, and licence check.
