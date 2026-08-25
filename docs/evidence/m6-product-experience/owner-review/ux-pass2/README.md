# M6 UX Overhaul Pass 2 — Core Daily Experience

Status: **deployed for owner visual review; not owner-accepted**

Qualification date: 2026-08-25. Branch: `phase6/product-experience`. Public owner-review origin:
`https://tracker.theroccos.us`. This pass follows approved concept design #2 and changes only
Today, Calendar, Quick Log, Animals, Enclosures, and small supporting shell presentation.

## Implemented daily-care experience

- Today is now a responsive care dashboard with authoritative Overdue, Due today, and Upcoming
  counts; compact image-backed cards; friendly relative timing; source-care context; concise
  capability-aware actions; and schedule provenance behind **Why this date?** disclosure.
- Calendar now provides real Agenda and Month views over the existing reminder facts and effective
  care history. Month navigation, selected-day detail, scheduled/completed markers, recent
  completed care, and direct care actions are presentation projections only; no calendar domain,
  duplicate schedule, or synthetic record was created.
- Quick Log groups all animals by the four accepted capability profiles and exposes only the
  existing care forms supported by each profile.
- Animals is image-forward, filterable by All/Snakes/Spiders/Lizards/Scorpions, and combines
  species, morph, current enclosure, status, and the most urgent applicable reminder.
- Enclosures now show occupants and their photos, unoccupied state, current enclosure status, and
  the most urgent maintenance reminder.

The reminder fact service and effective event histories remain authoritative. A small read-only
`EnclosureService.effective_history` method mirrors the existing animal read contract so Calendar
can present completed enclosure maintenance without persistence or event-contract changes.

## Native browser, layout, accessibility, and console

Native ARM64 Chromium `Chrome/151.0.7922.173` passed the deployed public origin at 1440×900,
390×844, and 360×800. It also verified the exact shell transition: the mobile shell remains active
at 1023px and the desktop sidebar takes over at 1024px (64rem). Every checked viewport had zero
horizontal overflow and mobile content cleared the measured bottom navigation.

Ten axe WCAG 2.2 A/AA scans reported zero violations: desktop Today, Calendar, Animals, and
Enclosures; mobile Today, Calendar Agenda, Calendar Month, Animals, Quick Log, and Enclosures.
There were zero Care Keeper application console/runtime errors, page errors, same-origin request
failures, or CSP violations involving Care Keeper-owned resources.

Cloudflare appends an inline analytics loader and
`https://static.cloudflareinsights.com/beacon.min.js` at the public edge. Care Keeper's unchanged
`script-src 'self'` policy blocks both, so Chromium records expected external-platform CSP
diagnostics. Axe ran through a temporary browser-only CSP bypass; it required no production
allowance. No `unsafe-inline`, `unsafe-eval`, Cloudflare host, or other third-party CSP source was
added. The complete machine result is [qualification.json](qualification.json).

## Repository and runtime qualification

- Ruff formatting/lint, dependency boundaries, 41-ADR architecture freeze, 191 documentation-link
  files, strict mypy over 124 source files, Compose config, and diff checks pass.
- Qualification has 455 effective passes: 444 passed in the full coverage run, the five affected
  presentation/environment contracts passed on exact rerun, and six focused projection tests pass.
- Coverage gates pass at 95.05% lines and 85.39% branches; strict dependency audit found no known
  vulnerabilities.
- Final active SQLite integrity is `ok`, foreign-key violations are zero, and Alembic remains at
  `0013_password_recovery`.
- The promoted native ARM64 image is
  `sha256:0accfcb9d96c1cc832954c4074f55b5e08af9894eede3209155b976c87760a66`.
  Web and worker are healthy as application user `snaketracker` with UID/GID `1001:1001`; nginx is
  healthy; and exactly one `snaketracker` Compose project remains active.

During qualification, the owner used normal self-service registration concurrently. The resulting
`Paul Rocco` / `Home` household was created at 2026-08-25 16:05 EDT and contains one animal and one
enclosure. It was preserved. The isolated fictional household still contains its 20 animals and
16 enclosures; its authenticated live agenda contained 23 rules grouped as 3 overdue, 5 due today,
and 15 upcoming at capture time. No reset, reseed, fixture mutation, or cross-household write was
performed by Pass 2.

## Owner-review screenshots

Desktop 1440×900:

- [Today](desktop-today.png)
- [Calendar Month](desktop-calendar.png)
- [Animals](desktop-animals.png)
- [Enclosures](desktop-enclosures.png)

Mobile 390×844:

- [Today — top](mobile-today-top.png)
- [Today — scrolled care cards](mobile-today-scrolled.png)
- [Calendar Agenda](mobile-calendar-agenda.png)
- [Calendar Month](mobile-calendar-month.png)
- [Animals](mobile-animals.png)
- [Quick Log](mobile-quick-log.png)
- [Enclosures](mobile-enclosures.png)

## Deliberate deferrals

Animal profiles, care-entry forms, schedules/reminder management, Trends, Inventory, Reports,
Expenses, authentication/onboarding, and deeper administrative views are not redesigned here.
Pass 3 has not begun. Calendar domain work, the final UX overhaul, M6 acceptance, PR #8 merge, and
M7 remain pending explicit owner direction.
