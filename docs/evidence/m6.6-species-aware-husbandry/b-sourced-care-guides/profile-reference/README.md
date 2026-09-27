# M6.6-B Animal Overview species reference correction

Status: draft PR #17, owner review pending. The Animal Overview now shows a read-only summary from the current reviewed guide for the Animal's explicitly linked Care Keeper taxon. The Species Directory, taxon search/link flow, and full Care Guide remain available.

The profile shows sourced fact values and deterministic support states. A disagreement displays **Sources differ** without choosing or merging a publisher's position. An explicitly linked taxon with no reviewed guide shows an unavailable state; an unlinked Animal gets a species-link prompt even when its legacy free-text species matches a reviewed taxon. The profile does not write care, reminder, schedule, Animal, Inventory, or source data.

## Isolated browser qualification

The disposable `/tmp/m66b-browser.efyLKz` fixture contains four fictional Animals: linked with guide, linked with source disagreement, linked without guide, and unlinked with matching legacy free-text species. It also contains the five existing reviewed public guides and global taxonomy test records. Reference photos displayed by the existing profile image path are public licensed reference images; no production household data appears in the screenshots.

The qualification script is `scripts/qualification/m66b_profile_reference_review.js`. Its private local evidence is under `/tmp/m66b-profile-reference-review`: 14 captures across desktop 1440×900 and mobile 390×844, including four desktop profile states and mobile focus crops. It checks profile-card placement, presence of actual reviewed values, disagreement handling, unavailable/unlinked states, Directory search, full-guide navigation, overflow, axe, and browser console errors. All 12 visited page-and-viewport combinations returned HTTP 200 with zero axe violations, overflow, or console errors.

## Quality gate

`uv sync --frozen` and `./scripts/quality/check.sh` passed on the Pi: 713 tests, 94.51% line coverage, 85.27% branch coverage, no known dependency vulnerabilities, and successful format, lint, type, architecture, documentation, Compose, and diff checks. The reviewed bundle SHA-256 remains `fd3e4d6e8d96173a51cfe7d7f5c20ecbfe24aae68127a3481f42a99e05097500`.

## Production owner-review deployment

Encrypted backup request `96b7e00b-02cc-4fd5-a065-d567f4d7758e` completed as run `4aa07d28-5186-454a-a47a-3502aa0d76f3`, manifest checksum `053bd9fd8580fd14832ee8f5028731cc62939899acb1704695b8937a63366e95`. An isolated restore returned `verified` with 33 referenced attachments.

Built `snaketracker:m66b-profile-c4740b3` from source commit `c4740b32c1b80f054725c0a037d47689bc283474` and verified the image's embedded revision label. The protected `.env` retained production mode and operator settings; only the image tag changed, and its mode remains `600`. Recreated web and worker without running a migration or guide import. Web, worker, and nginx are healthy; local nginx readiness returned HTTP 200. The deployed service worker advertises asset version `m66b-profile-reference-v2`.

Schema remains `0023_sourced_care_guides`. The guide tables still contain five versions, five current pointers, eight sources, and 30 claims. Exact immediate pre/post hashes match across 12 measured household/business tables, 40 attachment files, nine schema/taxonomy/guide tables, six reference-image files, and all three targeted Animal–taxon/reminder tables. The targeted tables contain three Animal–taxon links, 36 reminder rules, and 21 reminder facts; the reminder-fact comparison excludes only the worker's derived `calculated_at` timestamp. Domain-event high-water mark remains 872. SQLite integrity is `ok` with zero foreign-key violations. No Animal, care-history, reminder-rule, Inventory, user, guide-claim, or guide-source data changed; reminder due times, statuses, and explanations retained the same values.
