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

## Production owner-review deployment

- Committed source `6cbecf76f2f04be2a6e110acaef599a5a24bc597`; built image `snaketracker:m66b-owner-review-6cbecf7` with that exact embedded revision. The protected `.env` retained all settings, including production mode and platform operator configuration; only the image tag changed. Its mode remains `600`.
- Before promotion, encrypted backup request `d4e3fe55-510b-4b5c-9641-9247ef322865` completed as run `073db6e1-26e9-4ae8-a0a1-05cf5a28ad6a`, manifest checksum `83467367d1d1babdf8ffaa0192a6fc283415a6e28594919811687dc67e17c693`. Isolated restore under `/tmp/m66b-predeploy-restore.0TK5EG` verified 33 referenced attachments, integrity `ok`, zero foreign-key violations, and exact hashes for all measured household tables compared with live production. The production Attachment tree contains 40 files and remained byte-identical across deployment.
- The existing public taxonomy cache lacked *Pogona vitticeps* and *Pandinus imperator*. The M6.6-A provider/cache path resolved one exact public match for each and added only global taxonomy reference records before guide import. No household identifiers were sent to the provider. Business and Attachment hashes remained identical after this separate cache step.
- Stopped web and worker for the forward `0022→0023` migration. The immediate post-migration household/Attachment snapshot matched the predeploy baseline exactly. Imported five reviewed guide versions, eight source records, and 30 claims using the new image. A second production import reported zero new and five identical versions.
- Web and worker use the same new image in `production`; both and nginx are healthy. The local nginx readiness endpoint returned HTTP 200. Schema revision is `0023_sourced_care_guides`; current guide groups are snake, lizard, spider, scorpion, and plant.

## Production data integrity

Before/after hashes match for users, memberships, household summaries, Animals, Enclosures, Enclosure Plants, Inventory balances, Purchases, Expenses, immutable domain events, attachment metadata, and all 40 Attachment files. The event high-water mark remains 872. SQLite integrity remains `ok` with zero foreign-key violations. Full table comparison to the verified predeploy restore also found `reminder_rule_current` byte-identical. All 21 `reminder_facts` retain their identity, due time, status, and explanation; only the derived `calculated_at` timestamp changed when the worker recalculated them. The encrypted backup intentionally excludes ephemeral sessions and password-reset credentials, so those tables cannot be compared to its restored copy.

No household fact was created from Care Guide data. No schedule or reminder rule was created or changed; no Animal care history, Inventory balance, or user account changed. The new guide importer modified only the four new global Care Guide tables. The separate public-taxonomy cache step changed only global taxonomy reference records.

## Boundaries

The guide import writes only the new global Care Guide tables. Guide pages and links perform reads only. No household care records, reminders, schedules, Inventory balances, user accounts, or attachments are derived or changed by guide data.
