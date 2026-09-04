# M6 Mobile-First Product Experience and Runtime Consolidation Design

Status: Approved on 2026-08-16

## Outcomes

Care Keeper becomes the visible keeper-facing product name while internal SnakeTracker package,
repository, event, migration, cookie, and compatibility identities remain unchanged. The primary
experience is designed and qualified at a 390 x 844 mobile viewport, remains accessible at desktop
sizes, and retains strict CSP/server-rendered behavior.

Exactly one promoted Docker Compose application remains available at `http://localhost:8081`.
Its existing database and attachments retain the owner's real account and records and also contain
one isolated fictional household provisioned under ADR-0040. Alternate review stacks are stopped
only after backup/restore, migration, authentication, data-count, attachment, and bidirectional
authorization evidence passes against the promoted instance.

## Information architecture

Mobile uses a persistent safe-area-aware bottom navigation with Today, Animals, Enclosures,
Inventory, and More. Search remains compact and reachable in the header. More contains Reports,
Expenses, Reminders, Backups, Operations, account, and logout. Desktop exposes the same hierarchy
through a compact top navigation rather than a different product structure.

`/home` is the Today workspace. It presents compact Overdue, Due today, and Upcoming care cards
with animal/enclosure identity, due context, and direct existing actions. Owner-defined dates are
labelled Custom due dates and remain authoritative. `/animals` is a dedicated collection with
photos, type, enclosure, and useful status. Empty households receive a clear first-animal path.

Animal profiles prioritize identity, enclosure, large capability-appropriate actions, recent care,
history/trends, schedules, and administration in that order. Forms put common fields first and
advanced optional details in accessible disclosure sections; server validation preserves values
and errors. Analytics use plain-language summaries, explicit estimate labels, actionable
insufficient-history guidance, and optional Why details with deterministic provenance.

## Navigation and action safety

Agenda actions link only to registered existing care routes applicable to the animal capability
profile. A validated return context may target Today or the originating animal profile; arbitrary
redirect URLs are rejected. Capability checks remain enforced at application and domain boundaries,
not merely hidden in templates.

## Demo data and isolation

The reserved login is `owner@m6-demo.invalid`. The fictional dataset contains 10-15 snakes and
spiders across 8-10 enclosures, distinct safe images, several hundred coherent events, shared
inventory and expenses, reminders distributed across agenda states, and both sufficient and
insufficient analytics histories. General data is created through supported application/domain
interfaces after ADR-0040 provisions the household.

Tests prove real-to-demo and demo-to-real denial for navigation, direct identifiers, attachments,
search, reports, and writes. Seeder reruns are deterministic and idempotent. No reset or failure
path may delete or modify the real household.

## Qualification boundary

Qualification covers mobile/desktop real-browser journeys, keyboard behavior, WCAG 2.2 AA scans,
strict CSP, overflow/touch targets, console errors, login/logout, direct actions, search, reports,
PWA read-only behavior, backup/restore, migration lifecycle, Compose amd64, and ARM64 OCI build.
M6 owner acceptance, PR merge, M7, remote deployment, and Raspberry Pi qualification remain out of
scope.
