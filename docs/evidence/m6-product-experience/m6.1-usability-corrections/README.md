# M6.1 Final Usability and Correctness Corrections

Status: **implementation-qualified on the owner-review Raspberry Pi; owner review pending**

Qualification date: 2026-09-04. Branch: `phase6/product-experience`. Owner-review origin:
`https://tracker.theroccos.us`. This bounded package covers only `R-065`–`R-069` and `R-082`.
It does not record final M6 qualification or owner acceptance, merge PR #8, or begin M6.5, M7,
M8, or M9.

## R-065 — discoverable, revoking Sign out

The mobile More page now contains a clearly labelled **Sign out** control in its account card. The
desktop sidebar account area exposes the same compact action without adding it to primary care
navigation. Both controls submit the existing CSRF-protected `POST /logout`; the identity service
revokes the server-side session before cookies are deleted. Browser coverage proves the protected
home route is denied afterward, and deployed persistent-profile Chromium qualification proves the
logged-out state survives a browser close/relaunch.

Implementation: `presentation/templates/more.html`, `presentation/templates/base.html`,
`presentation/static/pwa.js`, and the existing logout handler in `presentation/web.py`. Tests:
`tests/browser/test_identity_flow.py` and `tests/browser/test_product_experience.py`.

## R-066 — mobile background/resume session persistence

The root cause was the cookie boundary, not server-side expiration, CSRF, service-worker cache, or
canonical-origin handling. The authenticated session and CSRF cookies had no `Expires` or
`Max-Age`, so they were browser-process session cookies even though the identity repository kept a
valid 30-minute-idle/12-hour-absolute server session. Mobile process eviction could therefore lose
the cookie while the server session remained valid. The Compose runtime also hard-coded the
development `Secure=false` value instead of honoring its configured HTTPS value.

All authentication issuance and rotation paths now set both cookies with the server session's
finite absolute expiry. They remain `HttpOnly`, `SameSite=Strict`, path `/`, and `Secure` on the
deployed HTTPS origin. The backend idle and absolute expirations are unchanged; normal request
validation still refreshes only the bounded idle window. Missing-CSRF recovery rotates the session
rather than replacing it with a pre-authentication state. No authentication state is placed in
local storage and the service worker does not own or clear session cookies.

Native ARM64 Chromium passed a CDP frozen/active lifecycle transition, reload, browser
close/relaunch with a persistent profile, explicit logout, protected-route denial, and a second
close/relaunch that remained logged out. Existing regressions continue to prove expired/invalid
sessions fail closed, CSRF is enforced, and a successful password reset revokes all sessions.
This is the strongest available automated lifecycle reproduction; it is not a claim of direct iOS
Safari automation. Implementation: `presentation/web.py` and `compose.yaml`. Tests:
`tests/browser/test_identity_flow.py`, `tests/browser/test_account_registration.py`, and the
password-recovery suites.

## R-067 and R-068 — actionable, understandable Calendar

The selected-day list now makes the whole care row a keyboard-focusable, touch-sized link.
Scheduled animal care opens the existing animal Care/schedule context (with existing action or
subject fallback); completed animal care opens the existing History timeline. Completed enclosure
care opens the existing enclosure context. Labels remain keeper-facing, never expose internal IDs,
and direct cross-household destinations continue to fail closed.

The marker legend is before the month toolbar and grid on phone and desktop. It explicitly maps
`✓ Completed`, `! Overdue`, `D Due`, and `↑ Upcoming`; color is supplementary rather than the only
signal. Counts remain compact in date cells. Every date link exposes its full date, pluralized care
counts/state names, and selected state to assistive technology. Tests cover scheduled/completed
destinations, full-row sizing, keyboard focusability, marker text/order, accessible labels, and
cross-household direct-ID denial in `tests/browser/test_product_experience.py`,
`tests/unit/presentation/test_agenda_actions.py`, and
`tests/unit/presentation/test_core_daily_views.py`.

## R-069 — global attribution

Desktop shows `© <current year> Paul Rocco`, email, and GitHub links in the sidebar footer. Mobile
places the attribution at the reachable bottom of More with padding above the fixed bottom
navigation and safe area, so it does not consume daily-care space. Unauthenticated pages receive a
quiet auth-shell footer. The links are `mailto:rocco.paul@gmail.com` and
`https://github.com/Shadowgar/SnakeTracker`. The year is supplied by the application template
environment. Implementation and responsive tests are in `templates/base.html`,
`templates/more.html`, `static/app.css`, and `tests/browser/test_product_experience.py`.

## R-082 — bounded, privacy-safe profile-photo processing

The former path rejected uploads above 5 MiB or 4096 pixels on either edge, accepted only JPEG/PNG,
and retained/served the uploaded bytes unchanged. Nginx independently capped the request at 1 MiB.
That combination rejected an ordinary 5.7 MB, 3072×4080 phone photo and could retain its EXIF/GPS
metadata.

The corrected path uses these finite boundaries:

- Incoming multipart/image size: 20 MiB at the application, with a 21 MiB Nginx request ceiling.
- Source raster: at most 8192 pixels on either edge and 25,000,000 decoded pixels. Pillow
  decompression-bomb warnings/errors, malformed data, decoding errors, and memory errors fail
  closed before attachment finalization.
- Supported decoded formats: JPEG/JPG, PNG, and WebP. Detected content must exactly match the
  declared media type; SVG, arbitrary files, and remote URLs are unsupported. HEIC/HEIF is not in
  the deployed ARM64 Pillow stack and receives a specific conversion-format message instead of a
  false size error.
- Processing: EXIF orientation is transposed first; aspect ratio is preserved with no destructive
  crop; the long edge is reduced to at most 1600 pixels; JPEG uses quality 88 optimized progressive
  encoding, PNG uses optimized level-7 compression, and WebP uses quality 86/method 4.
- Privacy/retention: the image is decoded into pixels and re-encoded without EXIF, GPS, camera,
  device, or source timestamp metadata. Only that canonical processed derivative enters staging,
  immutable attachment finalization, backup, and authenticated delivery. Raw phone bytes are not
  retained.

One 1600-pixel canonical derivative is reused by the current responsive profile/thumbnail UI. A
separate thumbnail family would require a broader attachment-derivative contract and is left as a
future optimization rather than creating a new media subsystem in M6.1. The existing opaque
attachment IDs, household ownership checks, animal ownership checks, authenticated delivery,
idempotency, and safe storage boundaries remain unchanged. WebP extensions were added to storage,
delivery, and backup mappings; there is no migration or event-contract change.

The native ARM64 public-origin journey accepted a synthetic privacy-safe 6,172,221-byte,
3072×4080 phone-scale JPEG carrying portrait orientation and synthetic device/GPS EXIF. It returned
to the animal profile in 4.270 seconds and served an 830,711-byte, 1600×1205 orientation-normalized
JPEG with zero EXIF entries. An isolated run under the production 384 MiB/one-CPU/non-root/read-only
container limits processed the same source in 0.715 seconds with 207,988 KiB maximum resident
memory. The reverse proxy retains a finite request timeout and the application remains a single
worker inside its 384 MiB container limit. Web/worker/nginx remained healthy. Unit, integration,
browser, and isolation coverage includes small JPEG, phone-scale JPEG, EXIF/GPS stripping, PNG,
WebP, malformed input, MIME mismatch, HEIF feedback, byte/dimension/pixel ceilings, immutable
finalization, authorized serving, cross-household denial, and profile refresh rendering.

## Deployed browser and accessibility qualification

The existing native ARM64 Chromium environment exercised 390×844, 360×800, 1440×900, and the
1023/1024-pixel shell transition. All measured viewports had no horizontal overflow. Axe WCAG
2 A/AA scans reported zero violations on mobile More, mobile Calendar, mobile processed profile,
and desktop Calendar. There were zero page errors, Care Keeper application JavaScript/runtime
errors, same-origin resource failures, or Care Keeper-owned CSP violations.

The public Cloudflare edge injects an inline challenge/analytics loader and a
`static.cloudflareinsights.com` beacon that are absent from the origin HTML. Both origin and public
responses retain the same strict `script-src 'self'` policy, so the browser correctly blocks those
Cloudflare additions. Script injection used by axe can likewise create test-harness-only CSP
diagnostics. These are classified separately in
[`browser-qualification.json`](browser-qualification.json); `applicationOwnedDiagnostics` and
`pageErrors` are empty. No Cloudflare allowlist, `unsafe-inline`, `unsafe-eval`, nonce, hash, or CSP
relaxation was introduced.

## Runtime, regression, and data safety

The final local qualification uses the exact frozen path `uv sync --frozen` followed by
`./scripts/quality/check.sh`. The complete gate passes formatting, architecture freeze, docs links,
strict mypy, the full pytest suite and coverage artifacts, dependency audit, Compose validation,
and diff checks. Focused M6.1 coverage passed 28 tests before the complete suite.

Migration head remains `0013_password_recovery`; no `0014` exists. Final SQLite
`integrity_check` is `ok` and `foreign_key_check` returns no rows. Deterministic pre/post hashes for
all non-demo business tables are identical: Home has 9 rows,
`7a23350dd2d86b2ae253edd86349de47f2898a17d5e7c1b837822a6e68091149`; Pass Four Empty
Collection has 4 rows,
`853393b3b5140b8117f4e414f3a9cba781e7170f24adea9a2d5acde371a1c581`; and Reptiles has
89 rows, `816bfd7d9711966cbeec2d025b408397f0e130a7a4aae635d9e58052eec00c96`.
Only the fictional demo animal received qualification photos. It remains 20 animals and 16
enclosures. No reset/reseed occurred.

The promoted image is native ARM64, runs as `snaketracker` UID/GID `1001:1001`, and remains behind
the single local `127.0.0.1:8081` Compose listener. Web, worker, and nginx are healthy. This is an
M6.1 owner-review deployment and does not qualify M7 deployment/recovery.

## Owner-review screenshots

Mobile 390×844:

- [Easy Sign out](screenshots/mobile-sign-out.png)
- [Calendar top legend](screenshots/mobile-calendar-legend.png)
- [Calendar selected-day links](screenshots/mobile-calendar-selected-items.png)
- [Reachable attribution](screenshots/mobile-attribution.png)
- [Profile upload form](screenshots/mobile-profile-before-upload.png)
- [Processed profile photo](screenshots/mobile-profile-after-upload.png)

Desktop 1440×900:

- [Sidebar account and Sign out](screenshots/desktop-account-sign-out.png)
- [Calendar top legend](screenshots/desktop-calendar-legend.png)
- [Calendar selected-day links](screenshots/desktop-calendar-selected-items.png)
- [Sidebar attribution](screenshots/desktop-attribution.png)
- [Processed profile photo](screenshots/desktop-profile-after-upload.png)

The source qualification image contains only generated noise and synthetic metadata. No owner
photo or private GPS value is committed. Owner review, including a representative real phone photo,
remains required before final M6 qualification may begin.
