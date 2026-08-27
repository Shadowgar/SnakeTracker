# M6 UX Overhaul Pass 3 — Animal Experience

Status: **deployed for owner visual review; not owner-accepted**

Qualification date: 2026-08-27. Branch: `phase6/product-experience`. Owner-review origin:
`https://tracker.theroccos.us`. This pass changes only the animal-centered experience and the
small shared presentation pieces needed to support it. It does not begin Pass 4, change domain or
schedule semantics, reset/reseed data, modify CSP, or qualify M6 as a whole.

## Animal experience result

The animal profile is now a composed Design #2-style experience with a responsive image-forward
hero, identity/species/group, enclosure and status, prominent next care, and persistent
`Overview · History · Trends · Care` section navigation. Mobile keeps all of that context compact;
desktop uses a horizontal identity/metadata/next-care composition instead of stretching the phone
layout.

- **Overview** prioritizes keeper-useful identity, current care facts, recent activity, and compact
  capability-derived quick actions instead of exposing every stored field or every editor.
- **Quick care and forms** use the accepted capability registry for Snake, Spider, Lizard, and
  Scorpion. Common required inputs come first, optional notes/details are quieter, return-to-Care
  behavior is supported, and impossible care actions remain absent.
- **History** is a compact keeper-readable timeline. Friendly titles describe feeding outcomes,
  measurements, shed/molt/premolt, bath, and misting. Corrections remain explicit as corrected;
  existing void/reinstate state and immutable technical provenance remain available without making
  raw event-store language the primary surface.
- **Trends** shows only supported analytics, uses compact Chart.js panels with nearby textual latest
  values/ranges/status, and preserves the existing deterministic estimates. Sparse animals receive
  a polished “Learning from your care history” state rather than an empty chart or technical
  threshold message.
- **Care** presents schedules as compact independent rows, including a clear `Not scheduled` state.
  Each schedule opens a one-schedule editor. The existing one-time semantic is labelled
  `Override next due date` and explained without changing reconciliation behavior.
- **Focused management** now has distinct photo, enclosure-move, and status routes. Basic profile
  editing keeps common identity fields first and moves advanced details lower on the page.

No remote photos, fonts, SPA framework, husbandry guidance, analytics algorithms, lifecycle states,
or scheduling rules were introduced.

## Functional, isolation, and regression qualification

The affected automated journeys cover profile section navigation, capability-driven action sets,
sufficient/insufficient analytics, keeper-readable correction history, disabled/enabled schedules,
the focused schedule editor and override copy, focused photo/enclosure/status flows, quick-care
save/return behavior, CSRF, household denial, attachment isolation, and established immutable
correction/void/reinstate semantics. The complete regression set contains 457 passing tests. The
full run's five corrected/stale assertions and minimal-container `git` omission were completed with
their exact targeted reruns rather than repeating the expensive suite.

Coverage is 94.80% statements/lines and 85.01% branches, passing the 90%/85% project gates. Ruff
format/lint, dependency boundaries, the 41-ADR architecture freeze, strict mypy over 124 source
files, documentation-link validation across 193 Markdown files, Compose validation,
`pip-audit --strict` with no known
vulnerabilities, the coverage gate, and `git diff --check` pass. The final persisted-reminder-fact
compatibility correction additionally passed its focused 11-test regression plus Ruff and mypy.

## Browser, responsiveness, accessibility, and CSP

The existing native ARM64 browser environment (`Chrome/151.0.7922.173`) qualified the deployed
public origin at 1440×900, 390×844, 360×800, and the 1023/1024px shell boundary. There is no
horizontal overflow; the transition remains mobile at 1023px and desktop at 1024px. All 14 required
deployed screenshots passed axe WCAG 2.2 A/AA with zero violations. Charts have readable text
equivalents, form labels/errors remain accessible, state is not color-only, and touch targets retain
the established mobile standard. Machine-readable detail is in
[`qualification.json`](qualification.json).

The final narrow deployed console scan reports zero Care Keeper application/runtime findings, zero
page errors, zero same-origin response failures, and zero CSP violations from Care Keeper-owned
resources; see [`console.json`](console.json). Care Keeper's origin contains no Cloudflare markup.
Cloudflare's public edge adds an inline loader and a `static.cloudflareinsights.com` beacon, both of
which are intentionally rejected by the unchanged `script-src 'self'` policy. Diagnostics produced
only while axe is injected are browser qualification artifacts. No Cloudflare host,
`unsafe-inline`, `unsafe-eval`, nonce, hash, or other CSP allowance was added.

## Data and Raspberry Pi runtime

The final active database passes `PRAGMA integrity_check`, has zero foreign-key violations, and
remains at `0013_password_recovery`. Its household shapes exactly match the saved Pass 2.1 evidence:

| Household | Animals | Enclosures | Domain events | Attachments |
| --- | ---: | ---: | ---: | ---: |
| Fictional owner-review | 20 | 16 | 505 | 21 |
| Isolated owner-created | 1 | 1 | 5 | 0 |

No active database reset, reseed, hand edit, or qualification care write was performed. The real
owner account/password and its animal/history were not mutated.

The promoted Linux ARM64 application image is
`sha256:1a9c735991956933fcba2d2f3cf9d56853983d387d1a7fbbe2e72191f1ca9ad6`. Web and worker are
healthy as UID/GID `1001:1001`; nginx is healthy and bound only to `127.0.0.1:8081`; the public
login returns HTTP 200. Exactly one `snaketracker` Compose project with the three intended active
services remains deployed.

## Owner-review screenshots

Mobile 390×844:

- [Snake Overview](mobile-snake-overview.png)
- [Spider Overview](mobile-spider-overview.png)
- [Lizard Overview](mobile-lizard-overview.png)
- [Scorpion Overview](mobile-scorpion-overview.png)
- [History](mobile-history.png)
- [Trends — sufficient history](mobile-trends-sufficient.png)
- [Trends — insufficient history](mobile-trends-insufficient.png)
- [Care schedules](mobile-care-schedules.png)
- [Focused schedule editor](mobile-schedule-editor.png)
- [Representative quick-care form](mobile-quick-care.png)

Desktop 1440×900:

- [Overview](desktop-overview.png)
- [History](desktop-history.png)
- [Trends](desktop-trends.png)
- [Care](desktop-care.png)

The deterministic green-dot fixture attachments remain a known visual limitation. They were not
regenerated or mutated; the new photo treatment is designed to present real uploaded photography
well.

## Stop boundary

Automated qualification is not owner visual acceptance. Pass 4, Inventory, Reports, Expenses,
authentication/onboarding, production email integration, final M6 qualification/acceptance, PR #8
merge, and M7 remain untouched and require explicit owner direction.
