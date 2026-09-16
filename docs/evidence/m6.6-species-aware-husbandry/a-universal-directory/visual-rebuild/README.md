# M6.6-A Phase 2 visual reconstruction

Status: implementation-qualified; owner review pending

The independent live visual audit was the baseline for this bounded reconstruction. The final
browser render, rather than template structure or test success alone, determined the ratings below.

| Surface | Baseline | Final |
|---|---|---|
| Mobile Today, 390×844 | MAJOR GAP | MINOR GAP |
| Mobile Animals, 390×844 | MAJOR GAP | MATCH |
| Mobile Animal Profile, 390×844 | NOT CLOSE | MINOR GAP |
| Mobile Calendar, 390×844 | MAJOR GAP | MINOR GAP |
| Mobile Quick Log, 390×844 | MAJOR GAP | MATCH |
| Mobile Enclosures, 390×844 | MAJOR GAP | MATCH |
| Desktop Today, 1440×900 | MAJOR GAP | MINOR GAP |
| Desktop Animals, 1440×900 | MAJOR GAP | MATCH |
| Desktop Animal Profile, 1440×900 | NOT CLOSE | MATCH |
| Desktop Enclosures, 1440×900 | MAJOR GAP | MATCH |

No required surface remains `NOT CLOSE` or `MAJOR GAP`.

## Remaining differences

- Today reflects the real fixture's current agenda volume and distribution, so its populated
  columns and available insights do not exactly match the fictional board data.
- Calendar retains all 36 real scheduled-care rows rather than reducing the result set to the
  board's sparse example. Its mobile document height fell from approximately 3,696 to 2,403 pixels
  through denser rows, controls, and grouping without hiding records.
- The profile uses the resolved reference photograph and identity of the actual qualified Animal,
  rather than copying the board's fictional animal.

These are truthful-data/content differences, not unresolved layout-system failures.

## Browser evidence

The isolated target was `/tmp/carekeeper-phase2-visual.bPDtFk`, served at
`http://127.0.0.1:8097`. Its database and attachment store were copied into that temporary target;
the active database `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3` and active
attachment directory `/home/rocco/SnakeTracker/runtime/phase2/attachments` were never qualification
targets. The browser journey was read-only.

The `screenshots/` directory contains the exact ten required renders. The machine-readable
`browser-qualification.json` records every route and viewport. Across all ten captures:

- axe reported zero WCAG A/AA violations;
- no horizontal overflow occurred;
- all 143 rendered images decoded, with zero broken images;
- application console diagnostics, page errors, and request failures were all zero; and
- every response retained the production CSP, including `script-src 'self'` and `img-src 'self'`.

The same audit was rerun against the promoted public HTTPS deployment and passed in 29 seconds.
The final screenshots and JSON therefore represent the real deployed Raspberry Pi image, not the
temporary qualification container.

## Reconstructed system

The shell no longer adds a redundant global header to screen-specific views. Desktop uses the
compact sidebar; mobile uses compact screen headers and bottom navigation. A shared, keyboard-safe
overflow menu replaces visually dominant secondary buttons and supports outside-click dismissal,
Escape, and focus restoration without inline script.

Today uses dense animal-led rows; Animals uses photo-dominant two- and four-column cards; the
profile uses one integrated mobile hero and a shallow panoramic desktop hero; Calendar uses a
compact week strip and grouped agenda rows; Quick Log uses icon-led action tiles and a dense recent
feed; and Enclosures uses image-led cards populated only by stored occupant, type, plant, and
maintenance facts.

The shared visual resolver now enforces keeper photo, cached Directory reference, reviewed local
species reference, species illustration, then group fallback. The known generated demo-seed art is
not misclassified as a keeper upload. Twenty integrity-checked local WebP references cover the
fixture's exact species plus the owner-requested Boa Constrictor image. Manifest entries retain
creator, provider, licence, source URL, and SHA-256 metadata; CC BY-NC use remains explicitly tied
to Care Keeper's current noncommercial status.

ADR-0043 remains Proposed. This reconstruction changes presentation and image resolution only; it
does not change domain events, household isolation, CSP, or the active database schema.

## Engineering and deployment qualification

The authoritative `uv sync --frozen` and `./scripts/quality/check.sh` path passed after the final
application change: all 680 tests passed; enforced line coverage was 94.41 percent, branch coverage
85.02 percent, and total coverage 92.52 percent. Formatting, Ruff, architecture freeze,
documentation links, strict mypy, dependency audit, Compose validation, and diff checks passed.

Public-origin performance remained within every existing budget: representative pages reached
network idle in 0.82–1.78 seconds, layout shift was zero, every visible image completed, total image
transfer stayed below 5 MiB, and the largest image stayed below 1 MiB. The performance harness's
only console diagnostics were Cloudflare's injected Browser Insights beacon and inline loaders
being rejected by the intentional `script-src 'self'` policy. They are external-platform
diagnostics, not Care Keeper JavaScript failures. No CSP allowance was added.

The non-overwriting encrypted backup and isolated restore details are recorded in
`live-data-integrity.json`. Active before/after business counts, all 822 ordered domain events,
SQLite integrity/FK status, and the 40-file attachment tree remained exact. The live database was
never a fixture or restore target.

Native ARM64 image `snaketracker:m66-a-phase2-visual` has digest
`sha256:bb4ba5a1162ca1008cc15c4f3bce251b61d206ac4da8de08aa38a18161196ac8`.
The migration one-shot exited zero at existing head `0022_reference_image_provenance`; web and
worker run as UID/GID `1001:1001`; web, worker, and Nginx are healthy; local and public readiness
return `ready`; and exactly one Care Keeper Compose project with three active services remains.
