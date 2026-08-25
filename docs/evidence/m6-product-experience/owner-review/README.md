# M6 Owner-Review Environment

Status: **available for owner inspection; M6 owner acceptance pending**

The promoted Raspberry Pi runtime is now a clean, disposable owner-review installation containing
exactly one fictional account and household. The previously qualified multi-household database and
attachments remain recoverable from a verified encrypted backup and an isolated pre-UX archive;
they are no longer active.

## Current fictional fixture

- URL: `https://tracker.theroccos.us`
- Email: `demo@carekeeper.local`
- Password: `carekeeper-demo-local-only`
- Scenario: `carekeeper-owner-review.v2`
- Anchor date: `2026-08-25` in `America/New_York`
- Contents: five Snakes, five Spiders, five Lizards, and five Scorpions; 16 enclosures; 20 distinct
  local fictional photos; 504 canonical domain events; eight inventory items; 14 expenses; and 23
  deliberate reminder rules.

The application still exposes normal self-service registration. The one-account statement
describes only the seeded starting state. The CLI seeder requires
`SNAKETRACKER_OWNER_REVIEW=enabled`, refuses a database containing any non-demo household, uses
supported application/domain/attachment boundaries, and returns the existing verified manifest
without appending events on an identical rerun.

See the [final fixture qualification](final-ux-fixture/README.md) for preservation IDs, exact
dataset shape, analytics states, browser/accessibility results, and the new backup/restore drill.
See [UX Pass 1](ux-pass1/README.md) for the owner-review design system, responsive shell,
navigation, Calendar shell, Quick Log, and public-fixture screenshots.
The earlier shared real-plus-demo runtime is retained as [historical qualification
evidence](consolidated-demo/README.md), not as the current active state.

This environment does not approve M6, implement the full Calendar experience, merge PR #8, or
begin M7.
