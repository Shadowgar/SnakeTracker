# M6.6-B Animal reference navigation owner correction

The October 2 owner amendment supersedes the earlier full-reference-on-Overview presentation decision. PR #17 remains open, draft, and unmerged. M6.6-B and ADR-0044/0048 acceptance remain pending. No X1, X2/X3 implementation, Amphibians, or M6.6-C work is authorized by this correction.

## Current presentation

The fifth Animal tab, **Guides & Species Reference**, follows Care at `/animals/{animal_id}/reference`, sharing the Animal hero and section navigation. Care continues to contain the keeper's personal schedules and workflows. The standalone Directory and taxon/guide pages remain secondary browsing tools.

Overview keeps a separate compact Species Reference card: linked species identity, up to three existing reviewed glance facts, guide availability, and a clear link to the Animal reference tab. The complete guide is rendered only on the reference page. Unlinked Animals retain their manual species record and existing explicit linking workflow.

The dedicated page separates **Species Overview / Natural History**, **Reviewed Captive Care**, and **Sources / Provenance**. It shows only already-saved identity/classification/names and existing reviewed guide facts. No new descriptions, Wikipedia summaries, conservation/range facts, or enrichment are fabricated or implemented. Existing sourced care and life-history claims retain their reviewed guide provenance; future biological-reference precedence remains governed by ADR-0047.

Full guide facts, original source disagreements, contextual positions, qualifiers/cautions, dates, bibliography, and version remain accessible through native disclosures. Desktop uses a glance grid and two-column section layout; mobile uses stacked disclosures and a readable horizontal tab strip. The strip may scroll; the page must not overflow.

A linked species without a guide says **“No reviewed captive-care guide is available yet.”** Species identity and Natural History availability remain separate from captive husbandry. The existing [platform plan](../../../../plans/2026-10-01-extensible-animal-and-species-platform.md#required-x3-qualification-central-american-boa) now requires Central American Boa / *Boa imperator* / iNaturalist `539399` as a future X3 acceptance case, using the established X2 local foundation and approved cached reference data.

## Record action controls

The shared Record form covers Feeding, Weight, Length, Shed, Bath, Molt, Premolt and Misting. Main submissions remain primary buttons; setup/navigation and Cancel use the existing secondary button visual system on semantic anchors. Empty Feeding presents primary Add food to inventory, secondary Set up inventory, and secondary Cancel. Applicable Feeding/Weight/Length/Shed/Molt correction forms follow the same hierarchy; deletion confirmations already complied. No new correction contracts were introduced.

No guide claims, support calculations, Animal records/taxon links, reminders, schedules, Inventory/history, exact length behavior, schema, provider architecture, or production settings are changed. Asset URL/cache versions advance together. No guide re-import or migration is required.

## Qualification and deployment evidence

The [amended browser receipt](reference-navigation-browser-20261002.json) records 34 navigation/presentation cases with 36 captures plus 84 retained regression cases with 32 captures. Both viewports passed with zero axe violations, page overflow, unexpected console errors, or outbound requests; the 26 injected regression failures remain expected. All eight Record forms passed computed-style, native-link and keyboard checks at both sizes. Mobile keyboard focus now reveals the complete reference tab label by adjusting only the tab strip horizontal scroll. Full quality, exact-image and deployment receipts follow their completed gates. Private/local captures are retained outside the repository. Production renderer diagnostics use actual read-only handler data with a locally injected existing principal; they do not claim a genuine owner login or full production HTTP middleware qualification.

## Historical qualification: superseded inline presentation

The earlier inline-reference candidate `21a0fca7c04bea090008d7fab180ef9db2e876f7` remains documented in the [historical browser receipt](browser-qualification-20261002.json), [historical quality receipt](quality-20261002.json), and [historical deployment receipt](deployment-20261002.json). Its 892-test gate, 26 browser captures and 10 real-Bitey captures qualify that earlier direction, not this amendment.

The encrypted recovery point `12fa3806-128d-4fde-83b1-b72d728919a9` contains all 46 finalized attachment versions at event cutoff 1031. The earlier qualified point `8777f5b4-545e-4384-81e6-e50c99553bb8` is preserved. Prior normal-worker verification encountered a 16 MiB temporary-space disk I/O failure; a bounded private scratch retry qualified the recovery point. That operational limit remains unchanged by this presentation correction.

Stop for owner review after the amended candidate is qualified and deployed. Do not merge PR #17 or mark M6.6-B accepted.
