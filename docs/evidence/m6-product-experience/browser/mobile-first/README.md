# M6 Mobile-First Care Keeper Journey

Result: **Pass** on August 16, 2026 against the consolidated Docker runtime at
`http://localhost:8081`.

Chromium was exercised with the fictional household at the primary 390 by 844 viewport and at
1440 by 900. The inspected journey covered login, Today, direct care action and safe return
context, the 12-animal mixed collection, Snake and Spider profiles, capability-specific actions,
recent effective care, analytics estimates, desktop navigation, and authenticated attachment
delivery.

- Document width equalled viewport width on every inspected mobile page; no horizontal overflow.
- The mobile navigation remained fixed with Today, Animals, Enclosures, Inventory, and More.
- Desktop used the same information architecture with static header navigation.
- Direct Today entry opened the correct animal form, kept `return_to=today`, and made Cancel return
  to `/home`.
- Feeding showed common fields first and a native accessible “More feeding details” disclosure.
- Snake actions included length, shed, and bath; Spider actions included molt, premolt, and misting,
  with the inapplicable opposite-type actions absent.
- Recent care excluded registration, photo, inventory, and schedule setup noise while retaining the
  complete timeline elsewhere.
- Analytics labeled results as estimates, kept reminder schedules authoritative, and exposed
  deterministic provenance under “Why?”.
- Chromium reported zero console errors and zero warnings.

Retained fictional-data screenshots: [mobile Today](mobile-today.png),
[mobile Animals](mobile-animals.png), [mobile animal profile](mobile-animal-profile.png),
[mobile analytics](mobile-analytics.png), and [desktop Today](desktop-today.png).

Pa11y 9.0.1 with the Axe runner and WCAG2AA rules reported zero issues on the authenticated Today,
Animals, animal profile, analytics, and More pages at 390 by 844. See the
[accessibility record](../../accessibility/critical-journeys/mobile-first.md).
