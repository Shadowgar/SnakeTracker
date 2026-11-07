# Plant Detail layout correction

Verified November 7, 2026 against baseline
`71eb88c01390d3672c470c1a50a80e707233c181`. The loopback fixture renders the actual
Plant Detail/base templates with fictional populated state and the exact retained
CC0 reference image. It uses no database, authentication credentials or provider.

## Cause and correction

The shared image rule sized the column to 112 px but left the HTML `height="800"`
in effect. The browser confirmed a **112 × 800 px** image, 870 px desktop header,
title at y=417 px and watering at y=1397 px. The file itself is 1001 × 987 px.

A Plant Detail stylesheet now sets automatic height, natural aspect ratio, bounded
height and contained image rendering, and top-aligns the title/species/status.
Compact details precede watering; optional reference guidance follows it. A direct
Watering & history anchor remains near the title. Attribution, fallback, Edit,
Remove, schedule, watering form and history URLs are preserved.

The stylesheet uses the existing `page_styles` hook with its own new URL, avoiding
the existing cache-first app.css entry in installed PWAs. Shared app.css, base
template, Animal and Directory layouts are unchanged. No plant records or history
are changed. Extreme unbroken names wrap in full; their text can legitimately make
a mobile header taller, while the photo stays bounded and the anchor still works.

| Viewport | Photo before → after | Header before → after | Watering top before → after |
| --- | --- | --- | --- |
| 1440 px | 112 × 800 → 176 × 173.56 | 870.06 → 218.11 | 1397.05 → 454.30 |
| 390 px | 112 × 800 → 112 × 110.45 | 866.06 → 225.33 | 1411.44 → 503.91 |
| 320 px | 112 × 800 → 112 × 110.45 | 866.06 → 253.84 | 1435.44 → 556.42 |

Screenshots: [desktop before](before/reference-1440.png) / [after](after/reference-1440.png),
[390 px before](before/reference-390.png) / [after](after/reference-390.png),
[320 px before](before/reference-320.png) / [after](after/reference-320.png),
[long name](after/long-name-320.png), [missing image](after/missing-image-320.png).

## Verification and reproduction

The [baseline browser run](before/browser-results.json) failed 25 geometry assertions.
The [final browser run](after/browser-results.json) passed all nine cases: three
widths × reference/long-name/missing-image. It checks dimensions and natural ratio,
title alignment, detail/watering access, actual anchor scrolling, attribution,
existing controls/history, horizontal overflow and axe WCAG A/AA violations.
There were zero axe violations, external requests, page errors or overflow.
Seven focused [Bioactive HTTP rendering tests](focused-rendering.txt) passed.
No local full application suite, build, scan or deployment was run for this fix.
Required hosted PR gates qualify the committed candidate separately.

```sh
python scripts/qualification/plant_detail_fixture.py --port 8193
# In a second terminal; use existing Playwright/axe-core installations:
CARE_PLAYWRIGHT=/absolute/path/to/node_modules/playwright \
CARE_AXE=/absolute/path/to/node_modules/axe-core/axe.min.js \
CARE_OUTPUT=output/plant-detail-layout \
node scripts/qualification/plant_detail_browser_review.js
PYTHONPATH=src:. pytest -q tests/integration/test_bioactive_web.py
```

`tested-file-hashes.json` identifies the tested source bytes; the evidence predates
the enclosing commit, hence `working-tree` in the browser receipt. The fixture
checks the retained image checksum before serving it. Automated Chromium/axe
checks do not claim physical-device or manual screen-reader acceptance.

## Reference asset finding

The cached Swiss Cheese Plant image is a Czech annotated educational plate with
white captions, yellow border and magenta annotation lines. It is unsuitable for
a clean reference-photo presentation. This correction preserves it and its
**Kostka Martin / Wikimedia Commons / CC0** attribution; CSS does not erase embedded
annotations. No replacement was fetched or published. Any replacement must use
the existing qualified reference-image acquisition process, never ordinary page
view downloads. Exact licensed fixture bytes and provenance are retained under
[`tests/fixtures/reference-images`](../../../tests/fixtures/reference-images/swiss-cheese-plant.json),
SHA-256 `5d73cdcbf18f47f96252a308d8678f0ed03631678a15e0f34972352c187ab9a5`.
