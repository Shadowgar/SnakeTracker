# M6.6-B sourced Care Guides qualification

Status: owner review pending. All browser data below is fictional and isolated from production.

## Reviewed reference data

- `reference/care-guides/reviewed-v1.json`: five public taxa, eight source records, and 30 individually attributed claims. The source quality and scope rules are in `docs/operations/care-guide-sources.md`.
- Snake: *Python regius*; lizard: *Pogona vitticeps*; spider: *Avicularia avicularia*; scorpion: *Pandinus imperator*; plant: *Monstera deliciosa*.
- The lizard basking ranges from RVC and RSPCA remain separate and display **Sources differ**. Their matching UVB positions display **Corroborated**. Single-publisher claims display **Single source**.
- The Monstera cat/dog toxicity claim has an explicit cat/dog scope. Reptile and exotic-enclosure suitability remains unestablished.

## Isolated production restore and migration rehearsal

- Restored encrypted backup run `57b3a675-d7f1-4168-9297-2e6923349677` under `/tmp/m66b-restore.NHIchAyq` using `backup_restore`. The restore verified 33 attachments.
- Rehearsed additive `0022_reference_image_provenance` → `0023_sourced_care_guides` against that restored copy. SQLite integrity was `ok` with zero foreign-key violations.
- Before/after snapshots of household tables and attachments were identical after the migration and after the import. The existing event high-water mark remained 872; attachment count remained 33.
- Cached exact public Pogona and Pandinus taxa in the isolated global taxonomy cache, then imported the five-guide bundle. First import: five new versions and 30 claims. Second import: zero new versions, five identical versions. Household snapshots remained identical.
- An attempted `0023` → `0022` downgrade on the isolated imported copy stopped with `Care-guide downgrade blocked: reviewed guide versions exist.` Recovery uses the verified encrypted backup or a reviewed forward migration.

## Browser and accessibility

The [browser qualification results](browser-qualification.json) record 14 captures: seven flows each at 1440×900 and 390×844. Flows include Directory, Animal profile, animal guide, lizard disagreement, plant Directory, plant guide, and enclosure plant detail. Every capture had zero axe violations, no horizontal overflow, and no browser console errors. [Screenshots](screenshots/) contain fictional data only.

## Local read performance

The browser qualification recorded navigation durations including Playwright's `networkidle` wait. The animal guide took 665 ms desktop and 565 ms mobile; the animal profile entry took 628 ms desktop and 603 ms mobile; the enclosure plant detail took 581 ms desktop and 566 ms mobile. These are isolated Raspberry Pi browser measurements, not server-only latency. Guide reads use local SQLite and make no external source request.

## Frozen quality gate

`uv sync --frozen` and `./scripts/quality/check.sh` passed on the Pi: 709 tests passed, 94.51% line coverage, 85.24% branch coverage, no known dependency vulnerabilities, and successful architecture, documentation, type, Compose, and diff checks. The fixed thresholds were unchanged.

## Boundaries

The guide import writes only the new global Care Guide tables. Guide pages and links perform reads only. No household care records, reminders, schedules, Inventory balances, user accounts, or attachments are derived or changed by guide data.
