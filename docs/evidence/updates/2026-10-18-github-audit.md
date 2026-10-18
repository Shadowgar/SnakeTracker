# Care Keeper — historical Updates page audit (2026-10-18)

Scope: repository `Shadowgar/SnakeTracker`, default-branch history through merge `a6d54a7f2f65999e2ae7f376a3df7b0c6dd24c08`.

## Completeness and source inventory

- 294 reachable commits inspected, August 4–October 18, 2026. The complete subject/SHA/date inventory is in `commit-inventory-2026-10-18.json`.
- 23 pull requests inspected, 21 merged and 2 unmerged. The complete inventory, including historical merged dates and source links, is in `pr-inventory-2026-10-18.json`.
- GitHub's Releases API returned **zero published release entries**. Repository merge dates do **not** prove a corresponding production deployment date.
- The GitHub history contains evidence of some live owner reviews and in-place development-to-production upgrades (for example, PR #16). That is not a complete, independently verified per-version deployment ledger. The Updates UI therefore presents a clearly labelled **development history** for all historical milestones and reserves the separate **Production updates** section for entries recorded *after a verified rollout*.
- The audit inventories include internal changes and review-only pull requests; the user-facing timeline groups related changes into plain-English milestone stories instead of exposing a 294-line commit log.

## Editorial mapping of all merged pull requests

- **Platform first steps:** [#1](https://github.com/Shadowgar/SnakeTracker/pull/1), [#2](https://github.com/Shadowgar/SnakeTracker/pull/2).
- **Account and household setup:** [#3](https://github.com/Shadowgar/SnakeTracker/pull/3).
- **Trustworthy care records:** [#4](https://github.com/Shadowgar/SnakeTracker/pull/4).
- **Animal profiles and enclosures:** [#5](https://github.com/Shadowgar/SnakeTracker/pull/5).
- **Care reminders and supplies:** [#6](https://github.com/Shadowgar/SnakeTracker/pull/6).
- **Spider tracking:** [#7](https://github.com/Shadowgar/SnakeTracker/pull/7).
- **Mobile redesign and more animal groups:** [#8](https://github.com/Shadowgar/SnakeTracker/pull/8).
- **Correct care history:** [#9](https://github.com/Shadowgar/SnakeTracker/pull/9), [#15](https://github.com/Shadowgar/SnakeTracker/pull/15).
- **Inventory and spending:** [#10](https://github.com/Shadowgar/SnakeTracker/pull/10), [#11](https://github.com/Shadowgar/SnakeTracker/pull/11), [#12](https://github.com/Shadowgar/SnakeTracker/pull/12), [#13](https://github.com/Shadowgar/SnakeTracker/pull/13).
- **Species search:** [#14](https://github.com/Shadowgar/SnakeTracker/pull/14).
- **Admin support tools:** [#16](https://github.com/Shadowgar/SnakeTracker/pull/16).
- **Care guides:** [#17](https://github.com/Shadowgar/SnakeTracker/pull/17).
- **Reliability and planning:** [#18](https://github.com/Shadowgar/SnakeTracker/pull/18), [#20](https://github.com/Shadowgar/SnakeTracker/pull/20).
- **Expandable animal support:** [#22](https://github.com/Shadowgar/SnakeTracker/pull/22).
- **Expanded local species directory:** [#23](https://github.com/Shadowgar/SnakeTracker/pull/23).

All 21 merged PRs are accounted for: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 23. Unmerged #21, #19 are **excluded** from completed milestones.

## Development merge activity (not site usage)

- 2026-08: 7 merged pull requests
- 2026-09: 9 merged pull requests
- 2026-10: 5 merged pull requests

## User-facing rules

1. Headlines describe what keepers can do, not implementation details. Mention technical changes only under optional details.
2. Show feature benefits before technical background; combine related PRs into compact illustrated cards, with older months collapsed.
3. Use local, repo-owned animal-group art; do not load remote images, expose private animal data, or fabricate graphs of user activity.
4. Treat merge dates as development milestones, never confirmed deployment dates. Production release entries require independently verified deployment evidence.
5. Only approved, validated entries in the persistent operator-owned production release ledger can appear as production updates; an absent ledger means **not recorded**, not **nothing deployed**.
6. No invented historical production release dates; first production rollout of this Updates feature requires an approved backfill decision if older versions should be presented as confirmed deployments.
7. X1 and X2 are merged in GitHub but **not known to be deployed** as of this audit. The X2 full-taxonomy import remains a separate operation.

## Release-recording contract

The production release ledger uses an explicitly configured read-only-mounted directory outside the writable database volume. Development/test previews default to `production-release-history.json` beside their isolated database. It is **read-only to the app** and must be updated only by an operator *after* a verified deployment (or rollback). It is not generated automatically from Git merges. A record requires a deployed UTC offset timestamp, approved build SHA, version, verification flag, short title, concise plain-language changes, and status (`deployed` or `rolled_back`). The app never updates this file during a page view.

The deployment runbook must preserve this ledger across upgrades/rollbacks and atomically append confirmed records. Existing accounts, animal history, attachments and active database are outside this feature's mutation scope.

## Limits

This audit proves the repository history and the editorial crosswalk. It does not authenticate timestamps for previously deployed web builds, and it does not replace a live production audit or release-signoff process. New milestones after this snapshot require an explicit editorial update.

## Completion verification and individual corrections

The original inventory was preserved. Its 294 commit identities exactly match `git rev-list` at
`a6d54a7`, and all 23 PR merge states and exact timestamps were checked against GitHub again.
The 21 merged PRs still map to the same 16 stories; #19 and #21 remain excluded. Monthly counts
7 / 9 / 5 agree with actual merge timestamps, not authored commit dates.

The [verification crosswalk](2026-10-18-audit-verification.json) records 23 meaningful individual
commits and their changed paths in addition to the PR mapping. These include changes inside
merged branches as well as corrections; a commit need not have its own PR or story to matter.
They cover password recovery, phone uploads, decimal weight/length retention, enclosure history,
Today/Calendar, card interactions, stock acquisition/spending, keeper-history filtering and the
compact dedicated species-reference tab. Relevant corrections are now named within expandable
stories. Story dates anchor the associated development milestone; later corrections are
explicitly described as later work, not as independently dated production releases.

Credits and SHA-256 hashes for the reused Crested Gecko and Pink-toed Tarantula photographs
were checked against the existing local reference manifest. Their original files are unchanged.
The remaining art is the existing generic group illustration set. No household photographs, new
remote image dependency or fabricated usage chart was introduced.

No production backfill was manufactured. Repository owner-review deployment receipts are
historical evidence, but this PR does not establish the currently running production build or
create confirmed live records from merge dates. The persistent ledger accepts separately verified
release events only; a future authorized operator can publish those after deployment verification.
