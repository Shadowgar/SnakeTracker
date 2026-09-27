# M6.6-B Animal Overview species reference correction

Status: draft PR #17, owner review pending. The Animal Overview now shows a read-only summary from the current reviewed guide for the Animal's explicitly linked Care Keeper taxon. The Species Directory, taxon search/link flow, and full Care Guide remain available.

The profile shows sourced fact values and deterministic support states. A disagreement displays **Sources differ** without choosing or merging a publisher's position. An explicitly linked taxon with no reviewed guide shows an unavailable state; an unlinked Animal gets a species-link prompt even when its legacy free-text species matches a reviewed taxon. The profile does not write care, reminder, schedule, Animal, Inventory, or source data.

## Isolated browser qualification

The disposable `/tmp/m66b-browser.efyLKz` fixture contains four fictional Animals: linked with guide, linked with source disagreement, linked without guide, and unlinked with matching legacy free-text species. It also contains the five existing reviewed public guides and global taxonomy test records. Reference photos displayed by the existing profile image path are public licensed reference images; no production household data appears in the screenshots.

The qualification script is `scripts/qualification/m66b_profile_reference_review.js`. Its private local evidence is under `/tmp/m66b-profile-reference-review`: 14 captures across desktop 1440×900 and mobile 390×844, including four desktop profile states and mobile focus crops. It checks profile-card placement, presence of actual reviewed values, disagreement handling, unavailable/unlinked states, Directory search, full-guide navigation, overflow, axe, and browser console errors. All 12 visited page-and-viewport combinations returned HTTP 200 with zero axe violations, overflow, or console errors.

## Quality gate

`uv sync --frozen` and `./scripts/quality/check.sh` passed on the Pi: 713 tests, 94.51% line coverage, 85.27% branch coverage, no known dependency vulnerabilities, and successful format, lint, type, architecture, documentation, Compose, and diff checks. The reviewed bundle SHA-256 remains `fd3e4d6e8d96173a51cfe7d7f5c20ecbfe24aae68127a3481f42a99e05097500`.

Pending verified encrypted backup, exact-image production deployment, and immediate pre/post data comparison.
