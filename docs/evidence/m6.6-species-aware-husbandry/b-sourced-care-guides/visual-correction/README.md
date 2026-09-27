# M6.6-B owner-review visual correction

Status: draft PR #17; owner review pending. This pass changes presentation and display rounding only. The reviewed guide bundle, source relationships, migrations, care records, and schedules are unchanged.

## Isolated browser qualification

The corrected UI was checked at 1440×900, 1720×900, and 390×844 using a disposable database under `/tmp/m66b-browser.wiiOT5`. The fixture has a fictional household and a separately licensed public Ball python reference photo by Stanislava Kamencayová (CC BY-SA 4.0, Wikimedia Commons). No production user information appears in the screenshots. The qualification script is `scripts/qualification/m66b_visual_review.js`.

Private full-page screenshots and machine-readable results are stored under `/tmp/m66b-visual-review`. The script checks image proportions, guide reading width, fact value size, disclosure target height, At a glance anchors, independent disagreement positions, plant suitability scope, overflow, axe, and browser console errors. It visits Directory, Animal profile, Animal guide, lizard disagreement, plant Directory, plant guide, and enclosure plant detail at each width.

The final isolated pass produced 21 full-page captures plus five mobile viewport crops for the guide overview, disagreement positions, and plant toxicity scope. All 21 routes returned HTTP 200, with zero axe violations, horizontal overflow, or browser console errors. The guide width stayed at or below 1140px on desktop, numeric values rendered at least 19px, and disclosure controls met a 44px target. Keyboard Enter opened source details. The wide taxon image occupied more than 35% of the hero, with at least 300px of width.

## Quality gate and backup

`uv sync --frozen` and `./scripts/quality/check.sh` passed on the Pi: 711 tests, 94.52% line coverage, 85.27% branch coverage, no known dependency vulnerabilities, and successful format, lint, type, architecture, documentation, Compose, and diff checks. The reviewed bundle SHA-256 remains `fd3e4d6e8d96173a51cfe7d7f5c20ecbfe24aae68127a3481f42a99e05097500`.

Predeployment encrypted backup request `2b91aab3-fa24-4f8b-9ee0-4bffd7bf73a9` completed as run `529f749d-2f7f-4f6a-8679-817b2b6fb72c`, manifest checksum `f94b39a162e8575b15ee6a5a3d9693253343428cd88da223459ab701163da3ea`. Isolated restore under `/tmp/m66b-visual-restore.pgmRnO` returned `verified` with 33 referenced attachments.

## Production owner-review deployment

Built image `snaketracker:m66b-visual-e9bad88` from commit `e9bad88d991a8fe0739b52a2e1062e18ae28e081` and verified its embedded revision label. The protected `.env` retained production mode and all operator settings; only the image tag changed. Its mode remains `600`. Recreated web and worker from the built image without running a migration or Care Guide import. Web, worker, and nginx are healthy; local nginx readiness returned HTTP 200. The deployed service worker advertises asset version `m66b-visual-correction-v1`.

Schema remains `0023_sourced_care_guides`. The global guide tables still contain five versions, five current pointers, eight sources, and 30 claims. Exact pre/post hashes match across all 12 measured household/business tables, all 40 attachment files, nine schema/taxonomy/guide tables, and all four reference image files. The domain-event high-water mark remains 872. SQLite integrity is `ok` with zero foreign-key violations. The existing reminder rules, care history, users, Animals, Inventory, and guide source relationships were not changed by deployment.
