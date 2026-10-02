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

The [amended browser receipt](reference-navigation-browser-20261002.json) records **118/118 cases** and **68 private captures**: 34 navigation/presentation cases plus all 84 regressions. Both 1440×900 and 390×844 passed zero axe violations, page overflow, unexpected console/page errors, and external requests. The 26 injected regression failures remain expected. All eight Record forms passed computed-style, native-anchor and keyboard checks at both sizes. Mobile keyboard focus and direct reference entry reveal the full active tab by scrolling only the section strip horizontally.

Frozen sync and the **entire quality script finished successfully**: **900 passed**, zero failures/errors/skips, lines **94.55%**, branches **85.37%**, and no known dependency vulnerabilities. Formatting/Ruff, architecture/freeze, documentation links, mypy, Compose and diff checks passed. Thresholds and the 30-second test timeout remain unchanged. Initial incomplete runs are superseded by this complete gate; a measured mobile focus defect was fixed before the final pass. See [full quality evidence](reference-navigation-quality-20261002.json).

### Exact live candidate

Source: `dd1785fe5508127f8c292b28cc8363b3e70e735d`. Image: `snaketracker:m66b-reference-navigation-dd1785f`. Image ID: `sha256:7a3fb836a12783e1bb8be2dc1c9d0f0e914ad8ab11367dc1ab78969f656fc4ef`.

Its exact GitHub Quality, Container and secret checks were SUCCESS before deployment. CodeRabbit reported SUCCESS with draft review skipped; an independent local source review found no material issue. The normal Dockerfile built UID/GID 1001:1001; all 35 runtime distributions match the lock, image/application revision matches source, and schema head remains 0023.

Maintenance lasted **15.288 seconds**. The guard required a clean exact source, complete successful local gate, green exact-head CI, read-only candidate qualification, unchanged live configuration and a fresh predeployment snapshot. It stopped worker then web and recreated only that pair from the same exact image, using no-deps/no-build/no-pull/force-recreate. No migration or Boa guide import ran. Web/worker/nginx are healthy, restart counts 0, liveness/readiness 200 and public readiness 200; captured new-container logs have no errors/exceptions.

Actual settings/operator allowlist, mounts/read-write flags, security settings and .env bytes/mode 0600 are unchanged. Nginx/tunnel identity/image/start times and historical migration State remain unchanged. Runtime storage topology is unchanged.

### Integrity and local-only reads

Immediate cutoff **1035→1035**; all 90 normalized and 61 logical table dimensions match. Schema 0023,148 raw SQL objects,114 normalized objects, projection catalog/generations and all 9 active checkpoints at 1035 are preserved. Backup worker construction is available with 0 pending requests. Inventory, reminders, schedules, records/history, taxon links, all 6 guide versions and their immutable source/claim/current tables remain unchanged.

All 46 attachment versions and 77 media files retain their metadata/hashes, mismatches 0. Boa version 1 equals the unchanged reviewed bundle: 28 facts, 34 positions, 7 sources; 22 Single source, 2 Corroborated, 4 Sources differ. Overview contains 0 full fact articles; the reference page contains all 28.

Before and after deployment, the exact image rendered **61 Overview +61 Reference pages across 4 households** with **0 outbound attempts and0 SQL-write attempts**. Cases include 39 available cached images (24 selected), 20 keeper photos, 4 missing optional enrichment cases (1 selected fallback), and local asset handlers 39×200/4×404. The real linked Boa imperator mapping 539399 shows Central American Boa identity/classification and explicitly lacks a reviewed captive-care guide.

**22 private production-data captures** use actual read-only GET-handler HTML, returned media and exact image static assets replayed locally under unchanged CSP. Bitey compact Overview, reference top/full/collapsed/all-facts, disagreement/sources, real Boa imperator identity/no-guide, Length actions and mobile tab focus passed 0 axe/overflow/errors/outbound/non-GET requests. The 68 fictional HTTP captures additionally include empty Feeding and normal Length/Weight/all-eight-form actions. Screenshots, production HTML and media remain outside the repository. The diagnostic supplies an existing principal only locally, issues no sessions, and does not claim a genuine production owner login or full production HTTP middleware qualification.

### Recovery and review boundary

Recovery point 12fa3806-128d-4fde-83b1-b72d728919a9 was freshly restored and verified before deployment, within the 6-hour RPO: 46 DB versions = 46 manifest entries = 46 restored files, 0 hash/metadata mismatches, schema 0023 / cutoff 1031, valid integrity/foreign keys and 0 restored sessions/reset credentials. Historical point 8777f5b4-545e-4384-81e6-e50c99553bb8 remains unchanged and reverified. The previous 21a image passed actual read-only startup compatibility before and after replacement; no rollback was performed. The known 16 MiB routine backup verification temporary-space limit remains unchanged; this presentation task does not resolve it.

See [sanitized deployment evidence](reference-navigation-deployment-20261002.json). The final evidence commit changes documentation only and preserves the deployed source/test/qualification/reference trees.

## Live owner review

1. Animals→Bitey→Overview: compact identity/three reviewed highlights and reference action, separate from Your Records.
2. Select **Guides & Species Reference** after Care: inspect saved identity, complete reviewed guide and separate sources/provenance; Care remains personal workflows.
3. Open Temperature & humidity and Sources differ; each publisher retains its own position. Open Sources for all 7 bibliography entries, dates and Version1.
4. Open the linked Central American Boa / Boa imperator reference page: saved taxonomy is visible; only the reviewed captive-care guide is described as absent.
5. Inspect empty Feeding Add food/Set up/Cancel and normal Length/Weight Submit/Cancel controls. At 390×844, reach the full tab by swipe or keyboard and check disclosures/focus without page overflow.

**Stop for owner review. PR #17 remains open, draft and unmerged. M6.6-B and ADR-0044/0048 are unaccepted. No X1, X2/X3 implementation, Amphibians or M6.6-C follows.**

## Historical qualification: superseded inline presentation

The earlier inline-reference candidate `21a0fca7c04bea090008d7fab180ef9db2e876f7` remains documented in the [historical browser receipt](browser-qualification-20261002.json), [historical quality receipt](quality-20261002.json), and [historical deployment receipt](deployment-20261002.json). Its 892-test gate, 26 browser captures and 10 real-Bitey captures qualify that earlier direction, not this amendment.

The encrypted recovery point `12fa3806-128d-4fde-83b1-b72d728919a9` contains all 46 finalized attachment versions at event cutoff 1031. The earlier qualified point `8777f5b4-545e-4384-81e6-e50c99553bb8` is preserved. Prior normal-worker verification encountered a 16 MiB temporary-space disk I/O failure; a bounded private scratch retry qualified the recovery point. That operational limit remains unchanged by this presentation correction.

Stop for owner review after the amended candidate is qualified and deployed. Do not merge PR #17 or mark M6.6-B accepted.
