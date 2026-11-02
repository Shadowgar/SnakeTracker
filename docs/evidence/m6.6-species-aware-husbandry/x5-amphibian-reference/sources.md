# X5 source and identity review — November 2, 2026

Owner source/design acceptance and production import remain pending. This is a
bounded, operator-curated bundle, not a remote provider feed. Claims are original
concise paraphrases and structured facts. No source article, PDF or photograph is
redistributed in the bundle. Research retrieval and curation review: November 2,
2026. The midnight UTC timestamps encode date precision, not an asserted access time.

## Identity and applicability

White's tree frog is **Pelodryas caerulea (White, 1790)** in the selected current
provider. [ITIS TSN 1099553](https://itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value=1099553)
records Litoria caerulea and Ranoidea caerulea as synonyms and class Amphibia/order
Anura. [NCBI 30344](https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=30344)
independently exposes the name history; its nomenclature disclaimer remains relevant.
ITIS itself cites AMNH's taxonomic work, so these are identity evidence, not independent
husbandry corroboration. The RVC and NSW sources name Litoria caerulea.
A bounded live [iNaturalist lookup](https://api.inaturalist.org/v1/taxa/1633145)
returned active species **1633145, Pelodryas caerulea**, with Amphibia ancestor 20978
and Anura 20979. The reviewed bundle uses this exact selected name. It does not import
against a similarly named Animal, common name, genus, or a synonym-only catalog row.
Existing links keep their UUID; qualification of a renamed catalog identity uses the
existing taxonomy workflow. No alias rewrite or duplicate UUID allocation is introduced.

Cranwell's horned frog is **Ceratophrys cranwelli**, active iNaturalist species
[22844](https://api.inaturalist.org/v1/taxa/22844), also with Amphibia/Anura ancestry.
[Smithsonian National Zoo](https://www.nationalzoo.si.edu/animals/cranwells-horned-frog)
confirms the scientific identity and distinguishes the name's origin from the Argentine
horned frog. Its wild ecology is **not** used to infer captive environmental targets.
C. ornata, C. cornuta and hybrids receive no guide through this bundle. The veterinary
source explicitly covers C. cranwelli together with C. ornata; that broader source scope
is retained in the guide's applicability section. No claim is extended to all Frogs.

## Qualified originating sources

| Bundle source | Actual publisher / exact source | Qualification and limitations |
| --- | --- | --- |
| `rvc-white-2024` | [Royal Veterinary College — White's Tree Frog Care, reviewed December 2024](https://www.rvc.ac.uk/Media/Default/Beaumont%20Sainsbury%20Animal%20Hospital/EXOTICS/Animal%20Care%20Factsheets/White%27s%20Tree%20Frog%20care%20sheet%202024%20jh.pdf) | Veterinary-school Exotics Service. Publisher-hosted indexed PDF text checked, including both pages. Direct download returned 403; no claim of a downloaded PDF. December 2024 is a month-only source review date in the title, not an invented exact publication timestamp. |
| `nsw-environment` | [NSW Department of Education — Green Tree Frog – environment](https://education.nsw.gov.au/teaching-and-learning/animals-in-schools/animals-in-schools-species/australian-native-animals/green-tree-frog/green-tree-frog-environment) | Government captive-animal welfare guidance for schools. Its parent page explicitly identifies Litoria caerulea. Updated August 28, 2026. |
| `nsw-enclosure` | [NSW Department of Education — Green Tree Frog – enclosure](https://education.nsw.gov.au/teaching-and-learning/animals-in-schools/animals-in-schools-species/australian-native-animals/green-tree-frog/green-tree-frog-enclosure) | Same publisher; not a second independent origin. School enclosure context retained. Updated August 28, 2026. |
| `nsw-water` | [NSW Department of Education — Green Tree Frog – nutrition and water](https://education.nsw.gov.au/teaching-and-learning/animals-in-schools/animals-in-schools-species/australian-native-animals/green-tree-frog/green-tree-frog-nutrition-and-water) | Same publisher. Bowl maintenance is explicitly distinct from filtered aquatic systems. |
| `treeoflife-pacman` | [Tree of Life Exotic Pet Medical Center — Pacman Frog (Ceratophrys spp.) Care](https://treeoflifeexotics.vet/education-resource-center/for-clients/amphibians/pacman-frog-care) | Exotic-pet veterinary hospital. Scientific-name line explicitly includes C. cranwelli. No publication date shown; none invented. All Cranwell care claims remain Single source. |

The third-party page used to discover the current RVC URL is not a source and is not
counted. The obsolete RVC November 2023 sheet is not mixed into the current version.
AMNH direct pages were unavailable during retrieval; their unavailable contents are
not evidence. No generic horned-frog article was silently treated as species evidence.

## Source-to-claim map

Claim IDs use the source ID followed by the fact key (and juvenile/adult suffix where
applicable); each exact source URL and November 2 retrieval/review date travels in the
immutable bundle. All claims carry species, captive context and explicit stage scope.
Post-metamorphic scope is an editorial restriction of applicability, not a source claim
about when metamorphosis occurs. No Animal's life stage is inferred.

| Source section | Included fact keys | Review notes |
| --- | --- | --- |
| RVC, Temperatures and humidity | `basking_temperature`, `cool_side_temperature`, `night_temperature`, `ambient_humidity`, `heat_safety` | Keep approximate values, overnight lower-limit wording and middle-of-vivarium measurement. Thermostat, measurement and burn precautions retained. |
| RVC, Accommodation | `habitat_structure`, `substrate`, `cleaning` | Climbing/hides, replaceable substrate and hygiene only; no invented enclosure size. |
| RVC, Lighting | `uvb`, `photoperiod` | Low output, qualified benefit wording, lamp distance/replacement instructions. |
| RVC, What to feed | `food_types`, `feeding_interval-juvenile`, `feeding_interval-adult`, `nutrition` | Juvenile/adult reference intervals stay separate; prey-size/overfeeding cautions visible. No doses or household schedule generated. |
| NSW, Environment | `ambient_temperature`, `ventilation`, `photoperiod`, `uvb` | Environmental temperature is not RVC's basking-spot measurement. Daylight versus UVB duration qualifications remain visible as separate positions. |
| NSW, Enclosure | `habitat_structure`, `furniture_safety`, `enclosure_dimensions` | Climbing/hides corroborate RVC at the same context. Size applies to one frog; larger groups need more space. |
| NSW, Nutrition and water | `water_safety`, `water_change`, `feeding_interval-juvenile`, `feeding_interval-adult`, `prey_portions` | Preserve untreated-water and reverse-osmosis cautions; daily bowl replacement is not a filtered-system rule. |
| Tree of Life, Temperature & heating / Humidity | `ambient_temperature`, `warm_side_temperature`, `night_temperature`, `ambient_humidity`, `temperature_monitoring` | Source Fahrenheit values retained in qualifiers; Celsius rounded to 0.1. Damp substrate/ventilation context; side-mounted heat-pad caution. |
| Tree of Life, Housing | `habitat_structure`, `substrate_depth` | Burrowing, hides and floor space; inches converted exactly to cm. |
| Tree of Life, Lighting | `uvb`, `photoperiod` | Source's qualified UVB position and light cycle, no invented UV index. |
| Tree of Life, Diet / Supplementation | `food_types`, `feeding_interval-juvenile`, `feeding_frequency-adult`, `nutrition` | Distinct age guidance, portions/obesity and substrate-ingestion precautions. No medical treatment or supplement dose inferred. |
| Tree of Life, Water & hydration / Handling / Species overview | `water_safety`, `handling`, `source_scope` | Shallow clean water, necessary-handling precautions, explicitly broader source applicability. |

## Disagreements, unknowns and rights

UVB positions retain RVC's qualified benefit and NSW's required-lighting position separately.
The lighting-duration comparison retains RVC's approximate UVB duration and NSW's
daylight range separately; differing scope is displayed, not presented as contradictory
clinical experiments. The two environmental-temperature positions retain separate
measurement locations and are never averaged into a universal target. Adult feeding positions also differ: both are retained with their original units.
Daily juvenile feeding and common climbing/hide provision are Corroborated care positions. Three NSW pages remain one
origin. Cranwell guidance has one qualified veterinary origin, not manufactured consensus.

No reviewed tadpole/breeding guidance is supplied. Missing numeric UV exposure, doses,
and unsupported parameters remain unavailable. A linked species without a bundle retains
the exact no-reviewed-guide message; Natural History is independent. Source outages do
not remove previously reviewed local claims, and ordinary viewing never retrieves sources.

RVC and Tree of Life do not provide an unrestricted redistribution license in the inspected
material (Tree of Life explicitly reserves rights). NSW attribution does not imply rights
to republish a complete article. This PR publishes only concise original summaries, facts
and links, not their expression, illustrations, logos or downloaded documents. Do not
publish full source copies or imply publisher endorsement. Owner source/publication review
is required before production import; no release is recorded here. Any future correction
must use a new immutable version after version 1 is imported.
