# M4 Accessibility Evidence

Result: **Pass with one documented axe 4.10 false-positive class**

Keyboard/screen-reader structure is asserted in the browser suite: one main landmark, skip link,
ordered headings, explicit labels, alert roles, semantic time values, descriptive photo alt text,
and current-household timezone labels. Controls retain visible focus and touch-sized targets; the
390-by-844 real-browser check corrected the only observed overlap.

Pa11y 9.0.1 with axe found no issues on login or the authenticated home page. On the authenticated
animal profile its embedded axe 4.10 reported seven textarea contrast errors. This matches Deque
[issue #4947](https://github.com/dequelabs/axe-core/issues/4947): axe could not determine textarea
backgrounds and returned false positives even for explicit valid colors. Deque's
[axe-core 4.11.1 release](https://github.com/dequelabs/axe-core/releases/tag/v4.11.1) records the
textarea fix.

Direct browser computed-style and WCAG calculations prove:

- entered text `#f4f7f2` on `#101915`: **16.58:1**;
- placeholder text `#b8c4b7` on `#101915`: **9.91:1**; and
- both exceed the 4.5:1 normal-text requirement.

The [retained axe browser capture](animal-profile-axe-browser.png) visually confirms the explicit
foreground/background styling. The contrast rule was not disabled or excluded. Re-run with:

```sh
npx --yes pa11y@9.0.1 --runner axe --standard WCAG2AA http://localhost:8081/login
```

The broader M6 critical-journey WCAG 2.2 AA gate remains future work; this evidence satisfies the
M4 core mobile, keyboard, and screen-reader workflow criterion.
