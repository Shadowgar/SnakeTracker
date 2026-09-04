# M6 UX Overhaul Pass 2.1 — Mobile Density and Design Fidelity

Status: **deployed for owner visual review; not owner-accepted**

Qualification date: 2026-08-26. Branch: `phase6/product-experience`. Owner-review origin:
`https://tracker.theroccos.us`. This is a focused presentation correction over Pass 2. It does not
add product capabilities, change reminder or care semantics, alter event storage, reset fixture
data, weaken CSP, or begin Pass 3.

## Before and after observations

- The mobile application header decreased from approximately 64px to a measured 56.19px. The
  logo is 28px, Add care is a compact plus control, and search/account retain 44px touch targets.
- Mobile Today removes the greeting eyebrow and repeated explanatory copy, compresses the summary,
  and presents care as approximately 90px image-backed rows. At 390×844, five complete tasks are
  visible above the bottom navigation in the qualified fixture; the prior Pass 2 capture required
  scrolling to inspect care cards. Visible **Why this date?** disclosures were removed from Today;
  authoritative due and prior-care context remain in each row.
- Mobile Animals moves from a single-column list to a two-column photo-first collection. Desktop
  Animals moves from three to four cards per row at 1440×900. The horizontal type-filter rail has
  an explicit fade/chevron affordance and its final chip is fully reachable.
- Calendar Agenda retains its existing architecture but adds stable 44px animal thumbnails and
  tighter rows/date groups. Calendar Month retains its table and selected-day panel while adding
  symbol-and-color markers for overdue (`!`), due (`D`), upcoming (`↑`), and completed (`✓`) states,
  including accessible per-state counts.
- Mobile Enclosures changes from large sparse cards to compact occupant-led rows; seven complete
  enclosures are visible at 390×844. Desktop Enclosures presents four compact cards per row and
  removes the repeated low-value Active label. Quiet negative state copy is now **No care due**.
- Mobile More changes five-rem destination tiles into compact navigation rows; six destinations
  are fully visible at 390×844.

The prior visual baseline remains in [`../ux-pass2`](../ux-pass2). Real attachment images are
cropped consistently, and missing-image fallbacks now use intentional group-specific gradient
treatments. Most fictional fixture attachments are themselves deterministic green-dot demo cards;
replacing those stored versions would require fixture regeneration and new photo-selection domain
events, so that source-asset improvement is deliberately deferred under this pass's data-safety
rule.

## Browser, responsiveness, accessibility, and console

Native ARM64 Chromium `Chrome/151.0.7922.173` passed the deployed public origin at 1440×900,
390×844, 360×800, 1023×800, and 1024×800. The exact 64rem shell transition remains correct:
mobile at 1023px and desktop at 1024px. All checked views had zero horizontal overflow, and mobile
content clears the measured 71.38px bottom navigation.

The ten required final screenshots each passed axe WCAG 2.2 A/AA with zero violations. Following a
CSS-only enclosure/filter refinement and asset cache-key update, the four affected Animals and
Enclosures views were rerun and again produced zero axe violations, zero application console or
page errors, zero same-origin request failures, and fully reachable filters. See
[`qualification.json`](qualification.json) and [`affected-rerun.json`](affected-rerun.json). A
final Today-only selector correction was then verified at desktop/mobile with five visible mobile
tasks, prior-care context present, zero visible schedule-provenance disclosures, and zero axe or
application runtime findings; see [`today-rerun.json`](today-rerun.json).

Care Keeper's origin response contains zero inline scripts and zero Cloudflare references. The
public edge response adds an inline `__CF`/`cdn-cgi` loader, and Chromium also reports the injected
`static.cloudflareinsights.com` beacon. Care Keeper's unchanged `script-src 'self'` blocks these
external additions. Axe uses browser-only CSP bypass while injected, so any diagnostic from that
period is qualification instrumentation rather than production application code. There were zero
CSP violations involving Care Keeper-owned resources. No Cloudflare host, `unsafe-inline`,
`unsafe-eval`, nonce, hash, or other allowance was added.

## Focused repository and runtime qualification

- Fourteen unique focused tests cover the daily projections, calendar, navigation/PWA shell,
  capability-aware agenda actions, and representative overdue/due/upcoming reconciliation. One
  bind-mounted SQLite migration test initially exceeded the default 30-second test timeout and
  passed unchanged with the established 120-second timeout. A later test-double compatibility
  failure in fallback metadata was corrected and its eight affected unit tests passed.
- Ruff formatting and lint pass. Dependency boundaries pass. The architecture freeze remains 41
  accepted ADRs. Strict mypy passes across 124 source files. `git diff --check` passes.
- The full-suite coverage gates were not repeated for this CSS/template-focused pass, as requested.
  The immediately preceding Pass 2 baseline remains 95.05% lines and 85.39% branches; new
  read-model behavior has focused unit and deployed-browser qualification.
- Final SQLite integrity is `ok`, foreign-key violations are zero, and Alembic remains at
  `0013_password_recovery`.
- The fictional household remains 20 animals, 16 enclosures, 505 domain events, and 21 attachment
  versions. The isolated owner household remains 1 animal, 1 enclosure, 5 domain events, and zero
  attachment versions. No reset, reseed, or cross-household write occurred.
- The promoted native ARM64 image is
  `sha256:daca057c6c062294d636db2343316bf8644f6c54342a67298f90900277e4d42d`.
  Web and worker are healthy as UID/GID `1001:1001`, nginx is healthy, and exactly one
  `snaketracker` Compose project with three active services remains deployed.

## Owner-review screenshots

Mobile 390×844:

- [Today](mobile-today.png)
- [Animals](mobile-animals.png)
- [Calendar Agenda](mobile-calendar-agenda.png)
- [Calendar Month](mobile-calendar-month.png)
- [Enclosures](mobile-enclosures.png)
- [More](mobile-more.png)

Desktop 1440×900:

- [Today](desktop-today.png)
- [Animals](desktop-animals.png)
- [Calendar Month](desktop-calendar-month.png)
- [Enclosures](desktop-enclosures.png)

## Stop boundary

Animal profiles, detailed care forms, schedule editors, Trends, History, Inventory, Reports,
Expenses, authentication/onboarding, Pass 3, final M6 qualification, PR #8 merge, M6 acceptance,
and M7 remain untouched and pending explicit owner direction.
