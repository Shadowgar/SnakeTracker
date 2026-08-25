# M6 UX Overhaul Pass 1 — Design System and Application Shell

Status: **deployed for owner visual review; not owner-accepted**

Qualification date: 2026-08-25. Branch: `phase6/product-experience`. Public fixture:
`https://tracker.theroccos.us`. This pass follows approved concept design #2 as the primary visual
target and changes the shared design system and application shell only.

## Implemented visual system

- layered near-black canvas, sidebar, surface, raised-card, and hover surfaces;
- purple primary brand/action/focus language with restrained semantic overdue, due-today,
  upcoming, completed, and disabled states that retain text labels;
- reusable spacing, type, control-height, radius, shadow, navigation, and content-width tokens;
- compact page and section headings, cards, list rows, badges, metadata, action rows, toolbars,
  responsive grids, form groupings, empty states, and image treatments;
- one local outline-SVG icon style with no remote fonts, images, framework, or icon bundle;
- versioned stylesheet and PWA shell cache so the deployed visual revision is not masked by a
  stale edge or service-worker copy.

## Responsive shell and information architecture

Below 64rem, the shell uses the approved safe-area-aware five-item bottom navigation in exact
order: Today, Animals, Calendar, Enclosures, More. The sticky mobile header contains compact
Care Keeper identity, a labeled Add care action, search, and account access. Main content reserves
more space than the measured 71.375px navigation height. At 360×800 and 390×844 there is no
horizontal overflow or navigation/content collision.

At 64rem and above, the mobile navigation disappears and a persistent 16.5rem desktop sidebar
exposes Today, Animals, Calendar, Enclosures, Add care, Inventory, Reports, Expenses, and More.
The content area is capped at 88rem and Today's unchanged agenda records flow into compact desktop
columns rather than stretched full-width cards. A 35rem minor breakpoint improves intermediate
header and authentication composition without competing navigation systems.

More now groups normal keeper destinations under Plan and review and Supplies. Backups and durable
delivery/system operations are retained under an explicit Advanced section. Inventory is not in
the mobile primary navigation. Household identity appears only as compact account/workspace
context, not as an unexplained page eyebrow.

Search is a compact global header action into the existing authorized search page. Add care opens
a capability-aware, image-rich chooser for all 20 fixture animals and links only to each animal's
existing supported care forms. No care form or domain behavior was rebuilt. Calendar is an
intentional route/page shell that links to existing Today and reminder behavior without creating
fake calendar data; Month and Agenda remain Pass 2 work.

## Browser, accessibility, and console qualification

Native ARM64 Chromium `Chrome/151.0.7922.173` exercised the deployed fixture at 1440×900, 390×844,
and 360×800. It verified desktop/sidebar and mobile/bottom-nav exclusivity, exact mobile order,
selected states, navigation transitions, search and Quick Log triggers, 20 animal images and Quick
Log choices, content clearance, and zero horizontal overflow.

Nine representative axe WCAG A/AA scans reported zero violations: Today, Animals, and Calendar on
desktop; Today, Animals, Enclosures, More, Calendar, and Quick Log on mobile. There were zero Care
Keeper application console/runtime errors, page errors, request failures, or CSP violations
involving Care Keeper-owned resources. Cloudflare's injected inline loader and
`static.cloudflareinsights.com` beacon remained blocked by the unchanged `script-src 'self'`
policy and are recorded as external-platform diagnostics. CSP was not weakened.

The complete machine-readable result is [qualification.json](qualification.json).

Repository qualification passed Ruff formatting/lint, dependency boundaries, the architecture
freeze across 41 accepted ADRs, 190 documentation-link files, strict mypy across 124 source files,
Compose configuration, and diff checks. The full suite recorded 448 passes and one expected-copy
assertion that still named the replaced `Welcome home` greeting; after updating that affected
contract, its exact test passed, yielding 449 effective passes. Branch coverage is 93.27%, above
the 90% gate. Strict dependency audit found no known vulnerabilities.

## Owner-review screenshots

Desktop 1440×900:

- [Today](desktop-today.png)
- [Animals](desktop-animals.png)
- [Calendar shell](desktop-calendar-shell.png)

Mobile 390×844:

- [Today](mobile-today.png)
- [Animals](mobile-animals.png)
- [Enclosures](mobile-enclosures.png)
- [More](mobile-more.png)
- [Calendar shell](mobile-calendar-shell.png)
- [Search interaction](mobile-search.png)
- [Quick Log](mobile-quick-log.png)

## Runtime and deliberate deferrals

The promoted ARM64 image is
`sha256:0e0970e39fb613ad94dd1fd9bb5273c462057182a30f3357c32b3684cc593bc0` and retains application
UID/GID `1001:1001`, the existing fixture, and the single `snaketracker` Compose project.

Today content semantics, full Calendar Month/Agenda, the Animals and Enclosures content designs,
animal profiles, care forms, Inventory, Reports, authentication/onboarding, and other deeper screen
work are intentionally not redesigned in Pass 1. Those existing screens inherit the new tokens
and shell but retain known composition imperfections for Pass 2 and later owner-directed passes.
