# M9 owner and visitor verification — 2026-11-08

This evidence concerns the proposed M9 implementation in the working tree based on
`a0975ef28937ecb11d0fe8da59d40eaab1886535`. It is implementation evidence, not
production qualification or public-release approval. Production public delivery is
disabled and configuration rejects enabling it in the production environment.

The browser used a fresh SQLite database and attachment directory under
`/tmp/carekeeper-m9-browser-20261108-c`, bound only to `127.0.0.1:8163`. All Animals,
accounts, captions and publication text were fictional. The uploaded 1200 × 800
image was the repository's existing generated snake illustration. No production
data, reference-provider fetch, Tailscale listener or public service was used.
The fixture process was stopped after verification; its files remain available.

## Results

- Playwright 1.58.2 with cached Chromium 145.0.7632.6 completed the real owner
  upload → two-photo ordering/caption changes → collection and Animal publication
  → anonymous profile/gallery/media → media/profile revocation journey. The
  existing primary profile-photo URL was unchanged.
- Twenty-three full-page captures covered owner album, Animal publication and
  household controls plus visitor profile, gallery, no-photo and long-name views
  at 1440, 390 and 320 pixels, and the empty album/empty collection states.
- Six additional owner captures verified the final scoped mobile gutters at 390
  and 320 pixels. This check reused the fictional post-revocation fixture and did
  not repeat mutations.
- Every checked viewport had zero horizontal overflow and zero axe violations
  for WCAG 2 A/AA and WCAG 2.1 AA. All displayed images decoded and used
  `object-fit: contain` within bounded boxes. No external browser requests or
  JavaScript errors occurred. The final fixture log contains no HTTP 500 or
  database-lock errors.
- Public output contained neither the private Animal identifier nor private
  keeper labels, attachment paths or account navigation. Public media GET/HEAD
  returned 404 after revocation. Public responses included `no-store`.
- The frontend's initial focused Python run passed 15 tests. The final combined
  new-M9 run, including the expanded archived-Album HTTP regression, passed 25
  tests (74.66 seconds), run by the integration owner. Focused Ruff, strict typing
  and JavaScript syntax checks passed.

The public profile's image element measured 561.20 × 398 pixels at 1440,
356 × 251.5 at 390, and 286 × 206 at 320. Its source remained 1200 × 800 and
`object-fit: contain` preserved the image proportions inside those bounded boxes.

Browser validation found and corrected an inaccessible no-image collection link.
Visual inspection also corrected missing mobile owner-page gutters with a rule
scoped to `.sharing-page`. The first browser attempt, concurrent with other
application tests, encountered a SQLite session-update lock; 20 overlapping
album/image reads subsequently passed, and the complete final journey passed
without overlapping test workload. No identity error was suppressed or unrelated
storage change made.

## Retained artifacts

Local evidence directory:
`/home/rocco/SnakeTracker/output/m9-public-sharing-20261108/browser/`

- `browser-results.json`: complete journey and 23 viewport records.
- `owner-mobile-results.json`: six final mobile owner checks.
- `SHA256SUMS`: checksums for both reports and all 29 screenshots.
- `public-animal-1440.png`, `public-collection-320.png`,
  `owner-album-final-390.png`, `owner-sharing-final-320.png`: representative
  captures that were visually inspected.

The final mobile screenshots have `-final-` in their names. Earlier owner mobile
captures remain as evidence of the full journey before the gutter correction.

## Reproduction

From the repository checkout, start the harness with a **fresh** directory; it
refuses an existing populated directory and never resets one:

```sh
PYTHONPATH=src:. /home/rocco/SnakeTracker/.venv/bin/python \
  scripts/qualification/m9_public_sharing_fixture.py \
  --data-dir /tmp/carekeeper-m9-browser-fresh --port 8163
```

After its manifest exists and the listener is ready, use the installed browser
and axe locations for the machine. The paths used for this run were:

```sh
CARE_FIXTURE=/tmp/carekeeper-m9-browser-fresh \
CARE_PLAYWRIGHT=/home/rocco/.npm/_npx/705bc6b22212b352/node_modules/playwright \
CARE_AXE=/home/rocco/.npm/_npx/6eed5a3c3d9b5d77/node_modules/axe-core/axe.min.js \
CARE_OUTPUT=/tmp/carekeeper-m9-browser-evidence \
node scripts/qualification/m9_public_sharing_browser.js
```

For a scoped rerender of the six mobile owner pages on the already populated
fictional fixture, add `CARE_OWNER_LAYOUT_ONLY=1`. This writes a separate report
and leaves the complete journey report intact. Stop only the fixture process
started for this check. Browser automation does not constitute physical-device,
production load, proxy, ARM64 image or release qualification.
