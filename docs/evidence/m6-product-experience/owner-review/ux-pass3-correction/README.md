# M6 UX Overhaul Pass 3 — Bounded Owner-Review Correction

Status: **deployed for owner visual review; not owner-accepted**

Qualification date: 2026-08-27. Owner-review origin: `https://tracker.theroccos.us`.
This correction is limited to the strict-mypy optional reminder label, restoration of the accepted
Pass 2.1 Today heading, and restoration of the compact Animals `+ Add` control. It does not begin
Pass 4 or change domain, event, schedule, data, migration, or CSP semantics.

## Authoritative quality gate

The GitHub workflow tool version and frozen path were reproduced with `uv 0.12.1`:

1. `uv sync --frozen`
2. `./scripts/quality/check.sh`

The Raspberry Pi required its established 120-second per-test timeout for the complete run; the
script and all gate commands remained unchanged. Results: Ruff format/lint passed, architecture and
dependency checks passed, the freeze remained 41 ADRs, documentation links passed across 194
Markdown files, strict mypy passed over 124 source files, all 458 tests passed, line coverage was
94.95%, branch coverage was 85.41%, all coverage/JUnit artifacts were generated, `pip-audit`
reported no known vulnerabilities, and Compose and diff validation passed. GitHub's own unmodified
`Quality / quality` result remains the authoritative hosted check.

The optional reminder source label is now accepted only when it is a non-empty string; otherwise
the established capability metadata supplies the real semantic fallback before keeper-facing text
normalization. No ignore, cast, or mypy relaxation was added.

## Pass 2.1 regression check

Native ARM64 Chromium `Chrome/151.0.7922.173` verified the corrected deployed public origin with no
horizontal overflow, application console findings, page errors, or same-origin response errors.
Today has the compact title, date/context, workload summary, and immediate agenda with no keeper
greeting. Animals retains the accepted density and navigation with a compact `+ Add` control under
160px rather than a full-width primary action.

- [Today — mobile 390×844](regression-mobile-today.png)
- [Today — desktop 1440×900](regression-desktop-today.png)
- [Animals — mobile 390×844](regression-mobile-animals.png)
- [Animals — desktop 1440×900](regression-desktop-animals.png)

## Pass 3 owner-review screenshots

The following are actual deployed Animal Experience captures from the corrected Raspberry Pi
environment. Juniper exercises rich history; Atlas exercises deliberately insufficient history.

Mobile 390×844:

- [Rich-history Animal Overview](owner-mobile-overview.png)
- [History](owner-mobile-history.png)
- [Trends — sufficient history](owner-mobile-trends-sufficient.png)
- [Trends — insufficient history](owner-mobile-trends-insufficient.png)
- [Care / Schedules](owner-mobile-care.png)
- [Focused schedule editor](owner-mobile-schedule-editor.png)
- [Representative care form](owner-mobile-care-form.png)

Desktop 1440×900:

- [Animal Overview](owner-desktop-overview.png)
- [History](owner-desktop-history.png)
- [Trends](owner-desktop-trends.png)
- [Care / Schedules](owner-desktop-care.png)

Machine-readable browser evidence is in [`qualification.json`](qualification.json).

## Data and runtime boundary

SQLite integrity is `ok`, foreign-key violations are zero, and migration head remains
`0013_password_recovery`. The demo fixture remains 20 animals, 16 enclosures, 505 domain events,
and 21 attachment versions. The isolated owner household remains one animal, one enclosure, five
events, and zero attachments. No owner or fixture care data was mutated.

The promoted Linux ARM64 image is
`sha256:2604bceb649b004fa2137662aeab15c61f6f80d5e370fcc294692e0743e2ad8e`. Web and worker are
healthy as UID/GID `1001:1001`; nginx is healthy; exactly one `snaketracker` Compose project remains
active. Production CSP is unchanged.
