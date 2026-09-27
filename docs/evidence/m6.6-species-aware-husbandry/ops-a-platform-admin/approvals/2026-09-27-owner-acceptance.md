# M6.6-OPS-A Owner Acceptance

Status: **M6.6-OPS-A accepted**

Accepted: **September 27, 2026**

Accepted source revision: `f8c429562c2b38ca29ba8ecf6a48b81426a51059`

Review vehicle: [PR #16 — Read-only operator administration and support console](https://github.com/Shadowgar/SnakeTracker/pull/16)

Record compiled: **2026-09-27 06:34 UTC** by Codex from the owner's explicit acceptance after live
production visual review. The owner said to continue and accepted the read-only Admin console,
production environment correction, deployment-controlled platform operator authorization, and
System Health/build-SHA improvements. This record covers the M6.6-OPS-A tranche; no separate
requirement or acceptance-test identifier was assigned to OPS-A. It does not accept the full M6.6
milestone or any OPS-B write capability.

## Accepted scope

The console provides Accounts, Households, Animal/Enclosure/Inventory support, Event Inspector,
Incident Explorer, System Health, and Admin Audit. Cross-household access requires an existing
authenticated account on the deployment-controlled platform operator allowlist. The owner accepted
the final readable dates, session status and browser labels, copyable IDs, Inventory quantities,
linked internal activity, named audit identities, and human-first event detail.

Support Notes, session revocation, account disable/reactivation, Admin password-reset actions, job
retry, projection rebuild, business-data correction tools, image refresh actions, and impersonation
remain deferred to OPS-B. Owner acceptance implies no authorization to implement or use them.

## Qualification and evidence

The accepted image `snaketracker:ops-a-owner-review-c2-f8c4295` embeds the exact accepted source
SHA. Web and worker ran that same image in `production` mode, and web, worker, and nginx were
healthy. Production-mode requirements were checked with an isolated data tree before deployment:
HTTPS origin, secure cookies, valid runtime and backup secrets, absolute local storage paths,
disabled local-file password-reset delivery, startup compatibility, signup/login, keeper routes,
Admin authorization, and worker startup. No production migration was required.

The frozen commands `uv sync --frozen` and `./scripts/quality/check.sh` passed on the production Pi:
**698 tests**, **94.45% line coverage**, **85.08% branch coverage**, and **no known dependency
vulnerabilities**. The accepted head's GitHub Actions [Quality run](https://github.com/Shadowgar/SnakeTracker/actions/runs/36299569534)
and [Container run](https://github.com/Shadowgar/SnakeTracker/actions/runs/36299569538) both
completed successfully. Generated local `coverage.json`, `coverage.xml`, and `junit.xml` and the
GitHub workflow artifacts contain the detailed test output; they are not production data.

A new encrypted backup completed and passed an isolated restore rehearsal. Read-only production
checks reported SQLite integrity `ok`, **zero** foreign-key violations, and **872** immutable
business events with high-water **872** at qualification. Pre/post hashes matched for users,
memberships, households, Animals, Enclosures, Plants, Inventory balances, Purchases, Expenses,
immutable events, consumption links, attachment metadata, and attachment files. No business data
was erased or edited, no user or care record changed, no Inventory balance changed, no event was
deleted, no attachment was replaced, and no test fixture entered production. The isolated review
copy was removed after qualification.

The owner completed the live production visual review. Private screenshots, account details,
emails, and incident evidence are deliberately excluded from this repository record.

## Boundary of this approval

This approval authorizes integration of PR #16. It does not require rebuilding the already-running
accepted image to display a merge commit: its embedded source SHA remains truthful. OPS-B and
M6.6-B remain deferred pending separate owner instruction.
