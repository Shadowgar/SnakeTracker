# Updates page — completion evidence

Existing PR #24 and branch `feature/visual-updates-history` were continued from
`bc0025b78f744f39df5745217aac40e68b3ff42c`. The initial work and inventories were preserved.
The original checkout's architecture-freeze edits were not used or changed.

## Finished design

The owner-approved board in [owner design](../../ux/owner-design/README.md) remains the target:
dark surfaces, restrained purple, image-led cards, mobile bottom navigation and desktop sidebar.
The header is more compact, photos carry local-manifest attribution, and each story expands to
explain what improved and whether a keeper needs to act. Older months remain native keyboard-
accessible disclosures. The chart counts actual merged PRs, with an explicit development label.

- [Desktop, 1440 × 900](screenshots/desktop-1440x900.png)
- [Desktop full page](screenshots/desktop-full.png)
- [Mobile, 390 × 844](screenshots/mobile-390x844.png)
- [Expanded mobile history](screenshots/mobile-history.png)
- [Synthetic rollback display](screenshots/synthetic-rollback-preview.png) — explicitly a test,
  not a production deployment or a claim about the running website.

## History verification

The [original audit](2026-10-18-github-audit.md) was completed using the
[additional verification crosswalk](2026-10-18-audit-verification.json): all 294 commit identities,
all 23 prior PR states/merge timestamps through #23, all 21 merged PRs in the same 16 stories,
and 23 meaningful individual corrections mapped to those stories. #19 and #21 are excluded.
No old production dates were invented; X1 and X2 remain development milestones.

## Qualification

The [baseline](baseline-focused.log) passed four existing tests before editing. New chronological
release/story tests [failed first](release-and-copy-red.log); the new append-command tests
[failed before implementation](operator-command-red.log). The
[final focused run](focused-final.log) passed all 17 cases. These cover time-zone ordering,
future/conflicting records, rollback retention, restart persistence, attribution, private routing,
CSP, dry-run behavior, invalid existing history and concurrent operator appends.

[Actual Chromium checks](browser-checks-2026-10-18.json) covered desktop/mobile screenshots,
320/768px overflow, keyboard Enter/Space, visible focus, More navigation, 44px disclosures,
reduced motion and representative contrast. All images loaded, with no console/network/CSP
errors. The strict existing CSP remains intact. Synthetic deployment/rollback records are
preserved in [this explicitly fictional fixture](synthetic-browser-release-history.json), used
only under `/tmp`; no production history was published.

The unchanged local quality gate is running once after corrections. Final hosted Quality,
Container and security results will be recorded in the PR description and delivery report;
this document does not claim an unfinished check passed. No thresholds or assertions were
weakened. The TestClient deprecation warning is retained in test receipts.

## Release persistence and boundaries

[Operator instructions](../../operations/updates-and-releases.md) describe persistent storage and
the explicit offline command. It validates without writing by default and atomically appends
only with `--apply`, after separate deployment verification. App views never write or repair
release records. Rollbacks append a new restoration event; old events are retained. No new
service, dependency, framework or database migration was added.

PR #24 remains the only review destination. No merge, deployment, production import, container
restart, live-data/attachment/backup change, X3 implementation or kernel-security work occurred.
Stop for owner design approval before merge.

## Final review correction: production read-only ledger

Hosted review identified that placing an operator-only ledger beside the writable database
cannot enforce its file-system boundary. Production now defaults to no ledger and accepts an
explicit `SNAKETRACKER_PRODUCTION_RELEASE_HISTORY_PATH` only on an absolute read-only-mounted
directory; ordinary startup checks the parent and any existing file mount flags. Development/test fallback remains local.
The runbook shows a normal read-only **directory** bind outside writable data volumes so atomic
host-side publication remains visible. No production mount, configuration or container was changed.

The [regressions](readonly-path-red.log) fail on the preceding configuration source. The
[41-test focused run](readonly-path-green.log) covers the new opt-in, mount rejection, environment
loading and existing release/configuration behavior. No local full gate was restarted. The old
run remains in progress after automatic approval review declined interruption; fresh hosted CI
will qualify the corrected commit. Earlier-head passes are not substituted.
