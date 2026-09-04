# M6 correctness and account-lifecycle tranche

This additive M6 tranche precedes the deferred final UX overhaul. It does not add Calendar, change
global navigation, merge PR #8, record M6 owner acceptance, or begin M7.

## Accepted implementation boundary

No new ADR is required. `AccountRegistrationService.register` is a production application boundary
that prepares the accepted `household.created` v1 and `household.owner_added` v1 facts, generates all
user/household/owner identities server-side, applies the existing normalized-email and Argon2 policy,
and commits the user, stream, events, household summary, owner membership, idempotency operation, and
security audit in one `BEGIN IMMEDIATE` transaction. It does not call one-time bootstrap or the
environment-gated ADR-0040 demo operation. Pre-auth CSRF, generic unique-identity failure, durable
throttling, and the normal session issuer remain in force.

Reminder state remains derived rather than marked complete. Event-relative schedules recur from the
latest effective qualifying event. A fixed schedule now advances to the first cadence occurrence after
qualifying care at or after the current due occurrence; care predating the occurrence and refused
feedings do not consume it. Corrections, voids, reinstatements, and one-time overrides continue through
the effective-history evaluator. Today reads this current calculation immediately, and enclosure
cleaning/water-change direct actions preserve the Today return context.

Inventory adds typed `item_updated`, `item_archived`, and `item_restored` facts plus synchronous active
status projection. Archived items are excluded from ordinary lists, stock changes, and new
inventory-linked feedings, while detail/history and consumption references remain intact. Restoration
returns the item to active selection. Permanent deletion is deliberately absent: even a newly created
item already has an immutable registration event, so no item is genuinely history-free.

## Reproduction

Focused automated coverage:

```text
pytest -q tests/integration/test_household_bootstrap.py \
  tests/browser/test_account_registration.py \
  tests/integration/test_inventory.py tests/integration/test_reminders.py \
  tests/browser/test_operational_workflows.py
```

The final qualification also runs the repository-wide coverage gate, Ruff format/lint, strict mypy,
architecture freeze and dependency boundaries, documentation links, dependency audit, event replay,
projection/search rebuilds, SQLite integrity, backup/restore, native ARM64 Compose, affected desktop
and approximately 390-by-844 mobile browser journeys, console checks, and accessibility checks.

## Qualification result

The affected native ARM64 Chromium qualification passed at desktop and 390-by-844 mobile viewports.
It covered self-service registration and isolated-household creation; Snake, Spider, Lizard, and
Scorpion reminder reconciliation; and inventory edit, stock adjustment, archive, archived-item
exclusion from future feeding selection, historical rendering, and restore. The affected axe scans
reported zero accessibility violations.

The console acceptance rule is zero Care Keeper application JavaScript/runtime errors and zero CSP
violations caused by Care Keeper-owned resources. The captured public-origin messages did not violate
that rule. They identified Cloudflare's injected Browser Insights resource at
`static.cloudflareinsights.com`, which the intentional `script-src 'self'` policy rejected, and inline
script hashes introduced solely by axe injection. The former is an expected external-platform
diagnostic and the latter is a qualification-harness artifact. No Care Keeper-owned resource or
runtime failure appeared in the captured console evidence. Production CSP was not changed: no
Cloudflare origin, `unsafe-inline`, `unsafe-eval`, or other third-party allowance was added.

Automated qualification after the last implementation change produced:

- full suite: 432 passed, with one non-failing warning;
- statement/line coverage: 95.07 percent;
- branch coverage: 85.17 percent;
- combined coverage: 93.24 percent, above the repository gate;
- Ruff formatting and lint: passed;
- strict mypy: passed across 122 source files;
- architecture freeze: passed with 41 accepted ADRs;
- dependency boundaries and documentation-link validation: passed;
- production dependency audit: no known vulnerabilities;
- typed live event replay: 51 streams and 269 events replayed successfully at the time of replay;
- live dashboard, insights, and search projection rebuilds: passed, with high-water position 634;
- focused identity verification after the final sign-in copy adjustment: 12 passed.

The fixed-cadence reminder cases passed for all four representative animal profiles. Effective-history
tests also passed for corrections, voids, and reinstatements: voided or superseded care does not advance
a reminder, and reinstatement restores the qualifying effect. Refused feedings remain nonqualifying.

## Migration and real-household integrity

Migration `0012_account_reminder_inventory` is applied in the promoted database. The final read-only
SQLite checks returned `ok` from `pragma integrity_check` and no rows from
`pragma foreign_key_check`.

The saved pre-change evidence for real household `ed44a39b-48ab-5e76-b55e-c0a553dd4030` compared
exactly after migration and browser qualification:

| Evidence | Before and after result |
| --- | --- |
| Domain-event count and SHA-256 | 21; `d30fc149221a05a097aa9035fb2f0f4d83e66a64fc28cc62b01bebe5d66472bd` |
| Pre-0012-comparable core-state SHA-256 | `196aeae39c7f1841532f8fdb136b79e16b3f9020341d6811d8f30e6c16b53e36` |
| Identity SHA-256 | `9d1a4036d1b6e657924f9845ee2ed6eaa82249438f414c56cf200d658b4409e2` |
| Attachment content SHA-256 | `1b061498c023525ae3ced752a15b97d69f2433f80486aeab4ecd8cbc70820f38` |
| Projection counts | animal 1, attachment 1, enclosure 2, expense 1, inventory 2, reminder 2 |

The post-0012 full core-state SHA-256 is
`30ab5beadce4248e3e372b8ca6c1a088adfcc9d57644344005c2ce33c7167af2`. Its intentional difference
from the pre-0012 representation is the new inventory lifecycle projection field; both real-household
inventory rows are `active`.

## Final backup, restore, and promoted runtime

The final post-change encrypted backup completed successfully:

- request: `c32d283d-f7e3-4147-ac71-51e59bdad0d9`;
- run: `96dbde6b-6268-4ce5-a00a-eb7a28d7efe4`;
- manifest SHA-256: `39426587117d97fc625f75d7c117faf1359c480a586d53f73ad978f5884196e1`;
- archive: `/var/lib/snaketracker/backups/96dbde6b62684ce5a00aeb7a28d7efe4`.

An isolated restore to
`/var/lib/snaketracker/restore-m6-correctness-final-20260825-0125` returned `verified` with 14
attachments. The source and restored databases both reported revision `0012_account_reminder_inventory`,
integrity `ok`, zero foreign-key violations, 4 users, 4 households, 300 events, and 14 attachment
versions.

The promoted Raspberry Pi image is `snaketracker:correctness-account`, image ID
`sha256:aa02aec064e9ac63b4f079e1ab50726dee0274680a181e855c7dc4d40ddc1ac9`, running the application as
UID/GID `1001:1001`. The final runtime check confirms the configured web readiness, worker process,
and nginx liveness checks are healthy and exactly one Care Keeper Compose stack is active.
