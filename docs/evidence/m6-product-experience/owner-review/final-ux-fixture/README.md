# Final M6 Owner-Review UX Fixture

Status: **Pass — fixture available for owner review; M6 owner acceptance pending**

Qualification date: 2026-08-25. Branch: `phase6/product-experience`. The operation deliberately
replaced only the active owner-review data after proving that the prior qualified state was
recoverable. No UX, Calendar, CSP, Cloudflare, PR, or M7 work was performed.

## Controlled preservation and clean installation

The pre-UX source passed `PRAGMA integrity_check`, had zero foreign-key violations, and was at
`0013_password_recovery`. Its recorded shape was nine households, nine users, 19 animals, 13
enclosures, 310 domain events, and 14 attachment versions/files.

- backup request: `4ac24705-27a5-44c8-a8b2-dc284048595a`
- completed backup run: `7d0cca58-b3da-46d7-997a-51fe701bfbd1`
- manifest checksum: `d221a8b9c14ea0a32fda61cf16edaa6579f83d036e0b9eb7668871666de7b0fd`
- encrypted archive: `runtime/archives/pre-ux-qualified-20260825/encrypted-backup`
- isolated restored snapshot: `runtime/archives/pre-ux-qualified-20260825/restore-rehearsal`
- restored database SHA-256: `4e17b8555184f0c35adf39971b945d3b0394553affca5d549f66e3893e99068a`
- stopped active files: `runtime/archives/pre-ux-qualified-20260825/active-original`

The isolated restore reproduced every recorded count, all 14 attachment files, SQLite integrity,
and zero FK violations before the old active files were moved. Backups and older restore evidence
were not removed.

The replacement database was created with no household, user, event, or attachment rows. Alembic
then logged every upgrade from the empty baseline through `0013_password_recovery`; the empty head
again passed integrity and FK checks before seeding.

## Reproducible manifest and identity

- manifest version: `2`
- scenario: `carekeeper-owner-review.v2`
- anchor: `2026-08-25`, household timezone `America/New_York`
- email: `demo@carekeeper.local`
- password: `carekeeper-demo-local-only`
- final active identities: one household, one user, one owner membership
- rerun proof: event count and high-water position remained exactly `504 / 504`

The seeder uses the trusted ADR-0040 household boundary, normal authenticated application forms,
canonical events, and immutable attachment staging/finalization. It produces 640×480 local PNGs,
does not hot-link or reuse archived owner media, requires an explicit owner-review environment
switch, refuses unexpected non-demo databases, and exposes no browser reset endpoint.

## Dataset shape

| Area | Qualified state |
| --- | --- |
| Animals | 20: 5 Snake, 5 Spider, 5 Lizard, 5 Scorpion |
| Enclosures | 16, including `Quiet Quarantine Observatory` unoccupied |
| History | 504 canonical events spanning 2025-08-02 through 2026-08-25 |
| Attachments | 20 distinct local profile-photo versions/files |
| Inventory | 8 total: 7 active, 1 archived; four feeding-linked deductions |
| Expenses | 14 total, 13 effective and 1 voided, spanning 2025-09-29 through 2026-08-20 |
| Reminder rules | 23: 6 overdue, 5 due today, 12 upcoming over the next six days |

Inventory includes edit and physical-count adjustment history, an archived Waxworm item whose
identity remains in historical feeding data, a Coco fiber archive/restore cycle, varied balances,
and one naturally low-stock-looking bulb balance (one on hand against a threshold of two). No new
low-stock feature was added.

The effective-history fixtures include a Juniper feeding correction, a Vesper spider feeding
correction, an Atlas feeding void/reinstate chain, and expense correction/void history. Lizard data
contains no shed events. Scorpion data contains no length, snake-shed, or bath events.

## Analytics and deliberate sparse states

Feeding estimates are ready for Cedar, Dune, Echo, Ember, Juniper, Kiko, Marlow, Marigold, Nimbus,
Nova, Onyx, Pearl, Rune, Saffron, Sol, and Vesper. Weight/length histories are substantial where
their accepted capability profiles permit them.

- snake shed estimates: Juniper, Marlow, Nova
- spider molt estimates: Ember, Marigold, Pearl, Vesper
- scorpion molt estimates: Nimbus, Onyx, Rune
- deliberately insufficient: Atlas (Snake), Pip (Spider), Bramble (Lizard), Cobalt (Scorpion)

All estimates derive from seeded effective history through the approved deterministic M6
calculations. No projection or prediction result was inserted directly.

## Replay, search, reports, registration, and recovery

- typed event replay loaded all 82 streams and all 504 events with contiguous stream heads;
- dashboard, insights, and search rebuilt atomically to high-water position 504;
- animal name, group, species, enclosure, and keeper-note searches returned their intended
  fixtures, including Marlow, Scorpion/Nimbus, Pantherophis, Amber Meadow, and moonlit;
- Collection, effective Care, and Expenses HTML and CSV reports returned substantial results;
- focused seeder/provisioning/isolation tests: 14 passed;
- isolated production registration, password-recovery, and household-isolation smoke: 5 passed;
- the active database remained at one user/household, with zero active reset credentials and zero
  active sessions after qualification cleanup.

## Native browser, CSP, and accessibility

Native ARM64 Chromium `Chrome/151.0.7922.173` passed 10 authenticated page scans at 1440×1000 and
390×844. Today, Collection, Inventory, Reports, and Search had no horizontal overflow, no page
errors, no Care Keeper-owned request failures, and no Care Keeper application console/runtime
findings. All 10 axe WCAG 2.2 A/AA scans reported zero violations.

The origin HTML contains only `/static/vendor/chart.js/chart.umd.min.js`, `/static/charts.js`, and
`/static/pwa.js`. Cloudflare's public response appends an inline `/cdn-cgi/challenge-platform`
loader and may inject `static.cloudflareinsights.com/beacon.min.js`; Care Keeper's intentional
`script-src 'self'` policy blocks both. Those messages are external-platform diagnostics.
Diagnostics caused solely while an axe script is injected are qualification-harness artifacts.
There were zero CSP violations involving Care Keeper-owned resources. CSP was not changed and no
third-party, `unsafe-inline`, or `unsafe-eval` allowance was added.

## New rich-demo backup and runtime

- backup request: `2ad40ca2-aae8-4742-9636-e11d8f9ed8e8`
- completed backup run: `6b50f7fc-efd4-4040-a0f7-01dd5a37e660`
- manifest checksum: `0b676fbefe0a605361c45fe1e99986fbf4719a4a6bcdfefa281cf9b8427712aa`
- isolated restored database SHA-256:
  `f7c8f627dec2fa2b019b3455b139ab72e5f99d36934d354e37b1e070409abf78`

The restore reproduced one household/user, 20 animals, 16 enclosures, 504 events, all 20 attachment
records/files, revision 0013, integrity `ok`, and zero FK violations. Restored active sessions and
password-reset credentials were zero.

The single `snaketracker` Compose project is healthy on Raspberry Pi ARM64 and binds only
`127.0.0.1:8081`. Web and worker use image
`sha256:2b1b8f17e5bdde73f483a6c55559a127a938d2083ddf03061f8514bfce78cccc` and run with application
UID/GID `1001:1001`; the runtime bind is also owned by `1001:1001`. The public route
`https://tracker.theroccos.us/login` returns HTTP 200.

## Repository quality

Ruff formatting/lint, dependency boundaries, architecture freeze (41 ADRs), 189 documentation
links, strict mypy over 124 source files, Compose config, and diff checks pass. The complete suite
has 449 passing tests: the containerized coverage run recorded 448 passes plus one environment-only
failure because that minimal image omitted the `git` executable; the exact failed contract then
passed in an ephemeral quality container with `git` present. Branch coverage is 93.30%, above the
90% gate. `pip-audit --strict` found no known vulnerabilities.

This evidence qualifies the fixture and environment only. M6 owner acceptance remains pending.
