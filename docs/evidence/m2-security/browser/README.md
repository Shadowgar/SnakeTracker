# M2 Browser and Accessibility Evidence

- Source revision: `0bcbc801c2f7fbfed0812f6ad0212eba209f307c`
- Browser: Playwright Chromium, 390 by 844 mobile viewport
- Requirement: R-035 M2 critical identity-flow slice
- Threat controls: TM-03, TM-05
- Result: Pass

A real browser completed fresh setup, reached the authenticated home page, logged out, returned to
login, logged in again, and returned to the protected home page through the Docker/Nginx endpoint.
The semantic snapshots contain one page-level heading, explicit field labels, a skip link, named
regions, and accessible buttons. The retained [mobile screenshot](mobile-home.png) shows the
authenticated state; it contains only synthetic qualification data.

The reproducible automated check is:

```sh
npx --yes pa11y http://127.0.0.1:8081/setup \
  --runner axe --standard WCAG2AA --reporter cli
```

Pa11y/axe reported `No issues found!` after solid, measurable contrast surfaces replaced decorative
translucent/gradient backgrounds. Keyboard-visible focus, a skip link, responsive layout, and
reduced-motion handling are present. Broader product-wide WCAG acceptance remains a Phase 6 gate.
