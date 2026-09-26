# M6.6-A final visual closure

Status: implementation-qualified; owner review pending. Captured from the deployed Raspberry Pi
site at `https://tracker.theroccos.us` on 2026-09-26. ADR-0043 remains Proposed.

## Blind visual re-audit

The ratings below were assigned from the final deployed screenshots, using the same ten surfaces
and owner board as the previous blind audit. The mobile viewport was exactly 390×844 and the
desktop viewport exactly 1440×900.

| Surface | Previous | Final | Screenshot |
|---|---|---|---|
| Mobile Today | MINOR GAP | MINOR GAP | [view](screenshots/mobile-390x844-today.png) |
| Mobile Animals | MINOR GAP | MINOR GAP | [view](screenshots/mobile-390x844-animals.png) |
| Mobile Animal Profile | MATCH | MATCH | [view](screenshots/mobile-390x844-animal-profile.png) |
| Mobile Calendar | MODERATE GAP | MINOR GAP | [view](screenshots/mobile-390x844-calendar.png) |
| Mobile Quick Log | MINOR GAP | MINOR GAP | [view](screenshots/mobile-390x844-quick-log.png) |
| Mobile Enclosures | MINOR GAP | MINOR GAP | [view](screenshots/mobile-390x844-enclosures.png) |
| Desktop Today | MODERATE GAP | MINOR GAP | [view](screenshots/desktop-1440x900-today.png) |
| Desktop Animals | MINOR GAP | MINOR GAP | [view](screenshots/desktop-1440x900-animals.png) |
| Desktop Animal Profile | MATCH | MATCH | [view](screenshots/desktop-1440x900-animal-profile.png) |
| Desktop Enclosures | MINOR GAP | MINOR GAP | [view](screenshots/desktop-1440x900-enclosures.png) |

**Does the current deployed Care Keeper site visually match the owner-approved design board? YES.**
Both former moderate gaps are now minor, and neither matched Profile regressed.

Calendar names and actions occupy separate lines in approximately 55px rows. The due state is
right aligned, bold, and colored by status. Desktop Today ends with four compact cards drawn from
the existing animal, enclosure, care-attention, and next-scheduled-care data. The desktop Animals
filter and Add button have a 13.7px gap. The desktop sidebar wordmark fits at 1440px and 1280px.

Remaining minor differences reflect live care data and supported actions: the mobile Today shell
retains its separate brand bar and larger title; Quick Log shows the five actions currently
supported by Care Keeper; live overdue labels are longer than the board's example due labels;
and the desktop Today due-today column is empty because no demo care is due today. No values or
actions were fabricated to fill those areas.

## Interaction and accessibility verification

At both viewports, Today and Calendar care rows opened the matching care form, Animal cards
opened profiles, Enclosure cards opened enclosure profiles, and Quick Log's Animal selection
changed the focused actions. The `⋮` action did not navigate its parent card; its secondary
link navigated only to its own destination. The first and bottom-edge menus used fixed top-layer
placement, were the topmost hit-tested element, stayed inside the viewport, opened from the
keyboard, closed on Escape and outside click, and restored trigger focus on Escape.

All ten surfaces returned HTTP 200, had no horizontal overflow or broken images, and produced
zero WCAG 2 A/AA, 2.1 A/AA, or 2.2 A/AA axe violations. There were zero application JavaScript
page errors. Browser navigation through network idle took 816–1,568 ms across the ten captures.

The production CSP still includes `script-src 'self'`. The local origin's `/home` response
contained four self-hosted external scripts and no inline scripts. The public Cloudflare response
added an email-decoder script and a 921-byte inline script; the public console also reported a
blocked `static.cloudflareinsights.com` analytics beacon. These are external platform CSP
diagnostics, separate from application JavaScript errors. Axe ran only in a browser test context
with CSP bypass for its injected instrumentation; production CSP was not changed.

## Live data and deployment

Active paths were explicitly identified before qualification:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`
- attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`
- reference-image cache: `/home/rocco/SnakeTracker/runtime/phase2/reference-images`
- encrypted backups: `/home/rocco/SnakeTracker/runtime/phase2/backups`

The live database was used only for authenticated read-only browser journeys and the application's
normal session activity. The 864 ordered domain events, event identity hash, all household
business counts, 40-file attachment tree, and four-file reference-image cache were identical
before and after. SQLite integrity was `ok`, foreign-key violations were zero, and migration
remained `0022_reference_image_provenance`. Details are in [live-data-integrity.json](live-data-integrity.json).

A later read-only check observed positions 865–870: three `animal.feeding_recorded` events each
paired with `inventory.stock_consumed`, recorded 05:53–05:54 UTC during a concurrent stock-feeding
investigation. These occurred after the identical visual-qualification before/after snapshot, not
from this pass's read-only browser journeys. The later database still passed SQLite integrity and
foreign-key checks; the six subsequent events are preserved, not cleaned up or attributed to the
visual qualification.

Prequalification encrypted backup run `65a9d334-9c93-48fd-a489-e06353595860` completed and
passed the built-in archive verifier. Its manifest SHA-256 was
`7c77473657e80a5c8610157643b2dba043d0c7a9489c650bd5b1e51da7fdcd1e`; the encrypted
database artifact SHA-256 was
`e087c37ebe734a87b644649e734e4f70feffadbf9d1bfd7f5a7ffd594e2d50ac`. The verified
archive contained 33 referenced attachments, migration `0022_reference_image_provenance`, and
event position 864. The prior isolated restore rehearsal remains documented in the
[interaction correction evidence](../interaction-correction/README.md); no restore targeted the
live runtime during this closure pass.

The promoted image is `snaketracker:m66-a-visual-closure-c1`, digest
`sha256:613c15514267f589d4b163f69c6ec050eb0a3c89fbdb81ac0ba45a938950a92d`.
Web, worker, and Nginx are healthy; local and public readiness report `ready`; web and worker
run as UID/GID `1001:1001`; and exactly one Care Keeper Compose project is active.

## Authoritative quality gate

The exact `uv sync --frozen` followed by `./scripts/quality/check.sh` passed against the isolated
final source checkout. Formatting, Ruff, architecture and architecture-freeze checks,
documentation links, strict mypy, all 680 tests, coverage artifact generation and coverage gates,
dependency audit, Compose validation, and diff checks completed successfully. Total coverage was
92.53%, with 94.42% line and 85.02% branch coverage. The audit found no known vulnerabilities.
The browser performance assertion passed within this full run; its earlier load-sensitive failure
was reproduced only while another qualification suite and image build were competing for the ARM
host. No threshold was changed.
