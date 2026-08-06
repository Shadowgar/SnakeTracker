# M2 Browser and Accessibility Evidence

- Retained browser-run source revision: `0bcbc801c2f7fbfed0812f6ad0212eba209f307c`
- Review-correction revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Browser: Playwright Chromium, 390 by 844 mobile viewport
- Reviewer: Codex automated verification; owner visually accepted the flow August 6, 2026
- Requirement: R-035 M2 critical identity-flow slice
- Threat controls: TM-03, TM-05
- Result: Pass

A real browser completed fresh setup, reached the authenticated home page, logged out, returned to
login, logged in again, and returned to the protected home page through the Docker/Nginx endpoint.
The semantic snapshots contain one page-level heading, explicit field labels, a skip link, named
regions, and accessible buttons. The retained [mobile screenshot](mobile-home.png) shows the
authenticated state; it contains only synthetic qualification data.

The retained August 5 browser run used the original local qualification endpoint on port 8081.
The current owner-facing WSL2 profile uses port 18081 because Windows/Hyper-V later reserved 8081;
the application and test configuration are otherwise equivalent. The reproducible current
accessibility check is:

```sh
npx --yes pa11y@9.0.1 http://127.0.0.1:18081/setup \
  --runner axe --standard WCAG2AA --reporter cli
```

Pa11y/axe reported `No issues found!` after solid, measurable contrast surfaces replaced decorative
translucent/gradient backgrounds. Keyboard-visible focus, a skip link, responsive layout, and
reduced-motion handling are present. Broader product-wide WCAG acceptance remains a Phase 6 gate.
