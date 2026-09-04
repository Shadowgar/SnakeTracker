# Final M6 qualification

Status: **Technical qualification passed; explicit final owner acceptance pending**

Baseline was `54009c4e3ec49527547959289d10bb72f57605ec` on
`phase6/product-experience`, matching `origin/phase6/product-experience`, with only the preserved
untracked `SnakeTracker.code-workspace`. No runtime database, attachment, backup, or secret was
tracked or staged.

## Live-data safety

The active database is `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`; active
attachments are `/home/rocco/SnakeTracker/runtime/phase2/attachments`. They were never reset,
reseeded, replaced, restored over, or used for destructive tests. Migration, account, image,
authorization, fixture, and schema lifecycle tests used pytest temporary databases. Restore and
projection rehearsal used `/tmp/carekeeper-final-m6-restore-final.*`, mounted as `/qualification`,
outside `/var/lib/snaketracker`. The operator restore command now fails closed when a non-test
target overlaps its configured runtime root or protected database/attachment/backup paths.

The final encrypted backup request was `8b77acf6-8da3-4fbc-bbd2-95bdfcf2cfe9`; run
`d4aae519-eaad-4f97-b780-7504527ea7fe` completed at migration `0013_password_recovery` and event
position 587. Its encrypted manifest SHA-256 is
`7da8c29a24bb8b0078f9ee67bd6172da292e991e0b49638277c3e5d2cb9223e6`; verification found 29
attachment artifacts and 31 event contracts. The isolated restore contained 4 households, 4
users, 587 events, 35 attachment-version records, 29 files, zero sessions, and zero password-reset
credentials. SQLite integrity was `ok`, FK violations were zero, and dashboard, insights, and
search rebuilt through position 587 without changing the immutable-event hash
`e7f24f930707764bc97066bcdd48d52b0d096587261706cda56abeecdc7457da`.

## Functional, migration, replay, and security result

The full 468-test suite passed. It covers the typed registry and v1/v2 coexistence; deterministic
correction, void, reinstate, reminder, inventory, expense, attachment, search, and analytics
replay; Snake, Spider, Lizard, and Scorpion capabilities; registration and isolated household
creation; login, persistence, logout, password-reset expiry/supersession/single-use/session
revocation/operator recovery; direct-ID household denial; Calendar; reports and CSV safety;
search; and state-derived onboarding. The 10-test migration lifecycle passed from disposable
databases, including zero-to-head, downgrade/re-upgrade, preservation/backfill, and lossy-downgrade
guards. The active database stayed at `0013_password_recovery`.

R-082 coverage passed JPEG, PNG, WebP, EXIF orientation/GPS stripping, the 6,172,221-byte
3072×4080 case, processed 1600-pixel long edge, content/MIME/corruption rejection, 20 MiB
application limit, 8192-pixel edge and 25 MP decoded limits, and cross-household denial. Nginx
retains its 21 MiB ceiling. The already owner-accepted public-origin normal-phone upload evidence
is retained in [M6.1 evidence](../m6.1-usability-corrections/README.md); it was not repeated because
that would append a live event. HEIC/HEIF remains explicitly unsupported.

The exact local gate `uv sync --frozen` followed by `./scripts/quality/check.sh` passed: Ruff,
strict mypy (124 source files), architecture boundaries and the 41-ADR freeze, 198 documentation
files, 468 tests, 94.85% line coverage, 85.21% branch coverage, dependency audit with no known
vulnerabilities, Compose validation, and diff checks.

The final pushed SHA's hosted Quality, Container, and security results are retained on PR #8 and
reported with the completion handoff; the PR remains unmerged.

## Browser, accessibility, CSP, and ARM64

Native ARM64 Chromium 145 exercised the public origin at 390×844, 360×800, 1440×900, 1023×800,
and 1024×800. Forty-one page/viewport combinations covered Sign in, Today, Animals, Overview,
History, Trends, Care/Schedules, Calendar Month and Agenda, Enclosures, Inventory, Expenses,
Reports, Search, More, Sign out, Registration, Forgot password, and the photo form. All returned
success with no horizontal overflow, hidden main landmark, same-origin failure, page error, or Care
Keeper application console error. Nineteen representative axe WCAG 2.2 A/AA scans reported zero
violations.

Cloudflare injects inline analytics/challenge loaders and a `static.cloudflareinsights.com` beacon
into the public edge response. Care Keeper's unchanged `script-src 'self'` correctly blocks them;
they are external-platform CSP diagnostics, not application-owned failures. Axe ran in a separate
instrumented context whose script injection is a test-harness artifact. No Cloudflare host,
`unsafe-inline`, `unsafe-eval`, nonce, hash, or other CSP relaxation was added.

Image `sha256:d67824003978484e13bba779dd9be193cf9a0d8d8df12f27a26ea17d99d00439` is native
`linux/arm64`. Web, worker, and nginx are healthy, web/worker run as UID/GID `1001:1001`, local and
public health/sign-in return HTTP 200, and the only Care Keeper Compose project listens on
`127.0.0.1:8081`.

## Owner-data comparison and boundary

The Home and Pass Four Empty household business hashes exactly match their pre-qualification
values: `7a23350dd2d86b2ae253edd86349de47f2898a17d5e7c1b837822a6e68091149` and
`853393b3b5140b8117f4e414f3a9cba781e7170f24adea9a2d5acde371a1c581`. Their event, animal,
enclosure, attachment, reset-credential, and session counts are unchanged. The Reptiles household
changed concurrently through owner-originated photo, weight, and feeding events at global positions
580–594 and associated attachment/session activity; qualification issued none of those events. The
verified final backup is the consistent position-587 snapshot; seven legitimate owner events arrived
afterward. The final live check at position 594 still reported SQLite integrity `ok`, zero FK
violations, and migration `0013_password_recovery`. Qualification writes to the active database were
limited to supported backup coordination and demo login/logout sessions. No real-owner credential
was used or changed.

R-065–R-069 and R-082 are owner-reviewed. M6.5 inventory intelligence, M7 formal deployment and
recovery qualification, M8 release qualification, M9 public profiles/albums/sharing, production
email delivery, HEIC/HEIF, and fictional fixture green-dot imagery remain deferred. This evidence
does not mark M6 owner-accepted and does not authorize PR #8 merge.
