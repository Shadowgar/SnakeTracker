# M6.6-B sourced Care Guides qualification

Status: **M6.6-B Accepted / Complete**, owner acceptance October 5, 2026. PR #17 integration is
finalized separately after the unchanged quality gate and current-head checks. The qualification
sections below retain their original revisions, counts and review context; final correction
receipts supersede the original presentation and 709-test gate.

## Owner acceptance

- Decision: ADR-0044, ADR-0048, ADR-0028
- Acceptance date: 2026-10-05
- Authority: Care Keeper owner explicit final acceptance, merge and source-synchronization instruction; subsequent explicit instruction to ignore GitGuardian failures and continue.
- Review status: Accepted for the implemented M6.6-B product and the bounded governance updates listed below.

The owner reviewed and accepts the live reference-density candidate at source
`04364cc4cad6c600dc167f32f4a9099b84667e98`, image
`snaketracker:m66b-reference-density-04364cc`. The starting PR head was
`f2700404e691104a977f16673b0fb745f23801ec`; subsequent finalization changes are documentation only.

Accepted scope: sourced/versioned global Care Guides with immutable source provenance, contextual
claims and separate disagreement positions; explicit/manual species workflows; compact Animal
Overview with limited reference highlights; the dedicated **Guides & Species Reference** tab after
Care; dense reference-sheet presentation, compact Species Overview, **Taxonomy details** disclosure,
At-a-Glance tiles and care disclosures; complete expanded guide detail and **Sources / Provenance**;
consistent Record-form actions; exact fractional length v2 and all mixed-version consumers; local-only
normal Animal/reference/image reads; production compatibility, recovery and live-data preservation.

**Species Overview / Natural History** currently contains locally saved taxonomic identity,
classification and names. Richer Natural History remains future X3. **Reviewed Captive Care** contains
the complete reviewed guide when available. The no-guide wording remains **No reviewed captive-care
guide is available yet.** No reference claim becomes a household fact, schedule or reminder.

Evidence: [correctness and exact-length consumer matrix](../b-corrections/README.md),
[backup completeness](../b-corrections/backup-completeness/README.md),
[owner-review deployment](../b-corrections/owner-review-deployment/README.md), and
[final reference-density qualification](../b-corrections/compact-species-reference/README.md).
The final candidate gate passed 900 tests, 94.55% line and 85.37% branch coverage. It qualified
21 browser cases, 46 fictional captures, 61 production profiles, 46 finalized attachment versions
and 77 media files. These are the linked October 2 receipts, not a claim about a new finalization run.

### Security-check exception

Incidents 37809855, 37809856 and 37809857 were independently verified as cryptographic file-integrity
SHA-256 digests, not credentials. The owner reports marking them ignored / false positive.
GitHub still recorded **GitGuardian Security Checks: FAILURE** at the starting head. The owner's
subsequent explicit instruction authorizes continuing despite that check. This records a check
exception, not a claim of scanner success. New findings remain a stop condition. Other required
checks and the full local quality gate remain mandatory; GitHub branch protections are not bypassed.
No credential rotation, history rewrite, detector weakening or global suppression is authorized.

### Preserved limits and next boundary

The routine backup worker verification path still has its documented 16 MiB temporary-space
limitation. Qualified private recovery points remain valid and include every finalized keeper
attachment version; this acceptance does not fix routine scratch infrastructure.

M6.6-A implementation/PR #14 and ADR-0043's established Accepted status remain recorded, but no
standalone historical A owner-acceptance artifact was preserved. This record accepts B only.
ADRs 0045, 0046 and 0047 remain Proposed; X1/X2/X3, Amphibians and M6.6-C are not begun or accepted.
**Boa imperator / iNaturalist 539399** remains a future X3 Natural History acceptance case.
Next task: **Pre-X1 Architecture Reconciliation**, then X1 → X2 → X3 → X4 → X5 → M6.6-C.

The content-bound approval entries below cover ADR promotion and the minimal status/presentation
consistency updates; they do not authorize Pre-X1 reconciliation or a new architecture design.
- Approved file: `docs/adr/0044-versioned-sourced-care-guides.md` SHA-256: `2972e6db22fbf7463b010de2dfc8df0a8902847601111fdbad463dcd2756fb15`
- Approved file: `docs/adr/0048-precise-animal-length-measurements.md` SHA-256: `ab85d2ac27656b828f27557708ef6a7c22a5eb5d6f6eb4c310ae5d3716863db2`
- Approved file: `docs/roadmap/milestones.md` SHA-256: `8ec9db613d8aa57202de44d2b93e874e67cfd26381e7959ee5f16018fcf6fab3`
- Approved file: `docs/requirements/traceability-matrix.md` SHA-256: `520a42e2f63ec39a5278b38ea229e6e365a3991fc94476b4ce0e6f83bb3a5cd2`
- Approved file: `docs/plans/2026-10-01-extensible-animal-and-species-platform.md` SHA-256: `107dfa73d8c3c69b2d373dafa4c1f3b8c230d8e86c85822b0385a35eaf031d45`

- Approved file: `docs/adr/README.md` SHA-256: `04e2363833ef4de451add37e76ea51347919374883798a0a3f0d13c4a9e4994d`

- Approved file: `docs/README.md` SHA-256: `1b40182cc57b5ab0b8d702a9422248189f468b9cc99cfc93363e584c14a68eb4`

## Final acceptance qualification — October 5

`uv sync --frozen` and the entire unchanged `./scripts/quality/check.sh` passed after the
acceptance/governance edits: **900 tests passed**, zero failures/errors/skips, **94.55% line**
and **85.39% branch coverage**. Formatting, Ruff, architecture, content-bound freeze/ADR
index/status validation, docs links, mypy, coverage, dependency audit, Compose and diff checks
passed. [Finalization receipt](final-acceptance-quality-20261005.json) distinguishes this run from
the historical deployment and browser receipts. Runtime trees remain identical to accepted source
`04364cc4cad6c600dc167f32f4a9099b84667e98`; no deployment, migration or import is required.

The read-only production baseline for source synchronization was schema 0023, event high-water
1037, 46 finalized attachment versions with zero mismatches, 77 media files, six guide versions,
15 sources and 64 claims. All services/readiness checks passed. Post-merge preservation is checked
against that baseline; these counts are not substituted for the original October 2 receipt.

## Historical initial qualification

The remaining sections record the original September qualification. Browser data is fictional and
isolated from production; production sections retain their original deployment context.

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
