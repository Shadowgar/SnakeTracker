# M6.6-A primary-interaction correction

Status: implementation-qualified; owner review pending

The deployed Care Keeper interaction model now makes the object itself the primary target:

- a Today care row opens that Animal's matching record-care form;
- an Animal card opens the Animal profile;
- an Enclosure card opens the Enclosure profile;
- a Calendar agenda row opens the matching care action; and
- the Quick Log Animal row selects the Animal through its native labeled select control.

Redundant visible `View` and `Open enclosure` labels were removed. The small three-dot control now
contains secondary actions only and is a real button independent of the card link.

## Live interaction audit

The audit ran against `https://tracker.theroccos.us` with the promoted native ARM64 image. The
machine-readable result is in `browser-qualification.json`; the two inspected live renders are in
`screenshots/`.

| Check | 390×844 | 1440×900 |
|---|---:|---:|
| Today row opened care form | pass | pass |
| Animal card opened profile | pass | pass |
| Enclosure card opened profile | pass | pass |
| Calendar row opened care form | pass | pass |
| Quick Log row changed selected Animal | pass | pass |
| Overflow trigger did not navigate card | pass | pass |
| Secondary action navigated only to its own target | pass | pass |
| Menu used fixed top-layer placement | pass | pass |
| Menu was the topmost hit-tested element | pass | pass |
| Bottom/right-edge menu remained inside viewport | pass | pass |
| Escape closed and restored trigger focus | pass | pass |
| Outside click closed | pass | pass |
| Keyboard Enter opened and focused a menu action | pass | pass |

The mobile edge menu occupied `left=30, top=634, right=190, bottom=768` in the 390×844 viewport.
The desktop edge menu occupied `left=964, top=714, right=1124, bottom=848` in the 1440×900
viewport. Both were hit-tested above neighboring cards and remained entirely inside the viewport.
Native `popover="auto"` provides top-layer rendering, light-dismiss, and one-open-at-a-time
behavior; the local script handles trigger-relative positioning, edge flipping, focus, and live
resize/scroll repositioning without inline or third-party JavaScript.

Ten affected-surface axe scans (Today, Animals, Enclosures, Calendar, and Quick Log at both
viewports) reported zero WCAG A/AA violations. Application console diagnostics, page errors, and
request failures were all zero. The production CSP remains unchanged.

## Quality and live-data safety

The exact authoritative path, `uv sync --frozen` followed by `./scripts/quality/check.sh`, passed:
680 tests, 94.42 percent line coverage, 85.02 percent branch coverage, and 92.53 percent total
coverage. Formatting, Ruff, architecture freeze, documentation links, strict mypy, dependency
audit, Compose validation, and diff checks also passed.

The active paths were explicitly protected:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`
- attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`
- reference-image cache: `/home/rocco/SnakeTracker/runtime/phase2/reference-images`

Backup run `80fc2e5a-dfad-45e7-ae23-cca73dc7fd01` completed with manifest checksum
`d82d6a08ae1c42bf53801eb3080941622a36bd7e94f7b34cd636d8bf681d6e02`. Its encrypted database
artifact checksum is `27cd569f8252160420cf9fa07e334fa70b0e17a81ccb8543163aa6365fb6b33f`.
The built-in fail-safe restore rehearsal verified 33 attachments under the isolated target
`/tmp/carekeeper-m66a-interaction-restore.A4dXPf`; that disposable restored plaintext was then
destroyed. The active database was never a restore target.

All 822 ordered domain events, their high-water position and identity checksum, all household
business counts, and the 40-file attachment tree remained exact. The read-only live render caused
the reference resolver to cache one eligible CC BY-NC GBIF photograph for taxon
`9fbce531-c58d-46f6-8809-2b3e1a3be0aa`; this added one `taxon_images` cache record and one runtime
reference file without changing household or event data. It was retained as valid application
cache state rather than manually deleted from the live database.

Image `snaketracker:m66-a-interaction-c1` has digest
`sha256:87bc9787e361438d35ff023acfe0cd0bcc3c250f5099d571d23cf1eb84b37956`.
Migration remains at `0022_reference_image_provenance`; web and worker run as UID/GID `1001:1001`;
web, worker, and Nginx are healthy; local and public readiness return `ready`; and exactly one
Care Keeper Compose project is active.
