# M6.2 Care Record Correction

Status: **technical qualification passed; owner review pending**

Requirement `R-083`; acceptance procedure `AT-M62-01`. Branch:
`hotfix/care-record-delete`. This bounded post-M6 correction addresses a real-use duplicate care
record without identifying the household or changing accepted event contracts. M6.5-A remains
paused.

The follow-up `AT-M62-02` covers a production feeding-form mismatch discovered before owner review:
the form rendered inventory quantity `1` even while **Do not deduct inventory** was selected. The
browser therefore submitted `(item=None, version=None, quantity=1)`, correctly triggering the
unchanged domain all-or-nothing invariant. The HTTP boundary now treats an explicitly empty item as
authoritative and normalizes all inventory fields to `None`; when an item is selected, version and
quantity remain mandatory. The quantity control is initially disabled and omitted from submission,
then the self-hosted feeding-form script enables it and defaults it to `1` only after item selection.
Correctness does not depend on JavaScript because the server discards stale unlinked values.

This current unlinked path is a pre-M6.5 compatibility bridge, not the final design. The owner has
approved future inventory-authoritative Feeding and structured Inventory catalog direction under
`R-084` and `R-085`; no M6.5 event, schema, migration, or product implementation is included here.
ADR-0042 must be amended on the M6.5 architecture branch before that work proceeds.

## Architecture and keeper behavior

**Delete record** is a compact action on supported, currently effective Animal History entries.
The server-rendered confirmation identifies the animal, care kind, date, effective details, and
notes, then explains that History and calculations will change. Cancel returns to the same record;
the confirmed mutation is authenticated and CSRF-protected. After deletion, the standard timeline
returns to the effective-history anchor with a visible status message and no longer renders the
deleted record. Advanced technical audit keeps the immutable source and appended control visible.

Deletion resolves the selected effective correction chain back to its immutable root and appends
the existing typed `event.voided` v1 contract with the original correlation lineage, actor,
causation, expected stream version, and idempotency boundary. This avoids the incorrect behavior
of voiding only a visible correction, which would reveal its predecessor. No SQL `DELETE`, second
deletion model, new event contract, or migration is introduced.

Supported Animal History types are feeding, weight, length, shed, bath/soak, molt, premolt, and
related enclosure misting records according to the animal capability profile and registered
correction policy. Household/account/security creation, animal registration/profile/status/photo,
enclosure assignment, inventory identity/lifecycle, and other specialized/system events are
intentionally excluded.

## Correctness and security coverage

Focused unit, integration, and browser tests cover:

- the reported duplicate-shed scenario, immutable row-count increase, deterministic replay,
  effective shed analytics, normal History removal, search removal, and HTML/CSV report removal;
- corrected-record root deletion and atomic reversal of stock-linked feeding consumption, with no
  duplicate reversal and no invented inventory event for an unlinked refused feeding;
- weight and length deletion with prior legitimate measurements restored as effective analytics
  values;
- bath/soak, Snake shed, Spider molt/premolt, and related misting deletion without crossing
  capability boundaries;
- event-relative reminder recalculation to the previous effective source without manually editing
  reminder tables; and
- unauthenticated/CSRF rejection, fabricated/already-deleted IDs, cross-animal and cross-household
  denial, keyboard-accessible actions, record-specific confirmation, and keeper-facing copy.

All destructive functional qualification uses pytest temporary SQLite files and isolated browser
fixtures. It never targets the active database or customer records.

## Qualification results

### Authoritative frozen quality gate

The required `uv sync --frozen` followed by `./scripts/quality/check.sh` completed against the
final hotfix implementation. The gate reported 474 tests, 0 failures, and 0 errors; 94.82%
statement coverage and 85.19% branch coverage; strict mypy, Ruff, dependency-boundary tests, coverage
validation, `pip-audit --strict`, Compose validation, and `git diff --check` all passed. The test,
coverage, and JUnit artifacts were produced. No implementation changed after this run.

### Public-origin keeper workflow

Native ARM64 Chromium qualified the deployed public origin at 390×844, 360×800, and 1440×900.
At each viewport the keeper created an explicitly tagged demo-household duplicate shed, opened the
compact action with the keyboard, saw a record-specific confirmation, canceled without mutation,
confirmed deletion, saw the success status, and verified the record disappeared from effective
History. All three viewports had no horizontal overflow. The 9 axe scans (action menu,
confirmation, and post-delete at each viewport) reported zero violations. There were zero Care
Keeper application console diagnostics and zero page errors.

The raw runner artifact is [browser-journey-raw.json](browser-journey-raw.json). Its aggregate
`status` is `failed` solely because the first runner attempted to prove audit visibility with
`innerText` while the native closed `<details>` disclosure intentionally hid its contents. Every
actual workflow, responsive, console, and axe field passed. A non-mutating follow-up expanded the
audit disclosure and confirmed all six tagged immutable source records remained visible alongside
the existing **Care record voided** controls; see
[browser-audit-verification.json](browser-audit-verification.json). Read-only SQLite verification
also confirmed a one-to-one causal `event.voided` pair for every tagged record. This is a
test-harness assertion correction, not a product exception.

Cloudflare injected Browser Insights scripts and inline analytics at the public origin. Care
Keeper's intentional `script-src 'self'` CSP blocked those resources. The 20 external diagnostics
per viewport are therefore expected platform diagnostics; axe execution produced no separate
harness diagnostics. No Care Keeper-owned resource caused a CSP violation, and the production CSP
was not weakened: no Cloudflare origin, `unsafe-inline`, or `unsafe-eval` allowance was added.

Screenshots:

- [390×844 confirmation](screenshots/mobile-390x844-confirmation.png) and
  [post-delete History](screenshots/mobile-390x844-after-delete.png)
- [360×800 confirmation](screenshots/mobile-360x800-confirmation.png) and
  [post-delete History](screenshots/mobile-360x800-after-delete.png)
- [1440×900 confirmation](screenshots/desktop-1440x900-confirmation.png) and
  [post-delete History](screenshots/desktop-1440x900-after-delete.png)

### Feeding-form compatibility follow-up

Native ARM64 Chromium qualified the corrected deployed feeding form at the public origin at
390×844 with an existing demo animal and Inventory Item. The default **Do not deduct inventory**
selection had a disabled quantity control, the feeding saved successfully, and stock remained 25.
Selecting the Inventory Item enabled quantity with default `1`; saving reduced stock from 25 to 24.
Deleting that linked feeding through M6.2 restored stock to 25, and deleting the unlinked feeding
left it at 25. Both Feeding sources disappeared from effective History and remained visible in the
immutable audit. The six-event qualification delta is exactly: unlinked Feeding; linked Feeding;
linked stock consumption; linked Feeding void; consumption reversal; unlinked Feeding void.

The responsive page had no horizontal overflow. Three axe scans reported zero violations, with
zero Care Keeper application console diagnostics, zero page errors, and zero qualification-harness
CSP diagnostics. The 38 external diagnostics were Cloudflare Browser Insights resources blocked by
the unchanged strict CSP. Evidence is in
[feeding-form-browser-qualification.json](feeding-form-browser-qualification.json) and the
[unlinked](screenshots/feeding-unlinked-390x844.png),
[linked](screenshots/feeding-linked-390x844.png), and
[post-delete](screenshots/feeding-post-delete-390x844.png) screenshots.

### Live-data safety, backup, and integrity

The active paths were explicitly resolved before qualification:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`
- attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`

They were never wiped, reset, reseeded, replaced, restored over, truncated, used as a fresh-install
target, or manually cleaned. Functional/destructive coverage ran on pytest temporary databases.
The public-origin checks used only the existing fictional demo household and append-only tagged
qualification facts; no customer record was created, changed, or deleted.

Before deployment the supported worker-owned backup pipeline completed encrypted backup run
`e741aee5-36e7-4f10-9045-844007148475` for request
`7723ca65-5b44-4818-a645-e1d5e5a3ce5e`. Its encrypted manifest checksum is
`e953861e8e5cb255b33e0df673003866abeab358cf45278f2312220f5a06e11f`. Prior backups were not
overwritten. No restore was required or performed; any future restore qualification remains bound
to an isolated target.

Before deploying the feeding-form follow-up, the same supported pipeline completed encrypted
backup run `c2673042-d4fc-40a1-9ee5-5dd6d714b09d` for request
`cb74b8a8-c2a7-47dd-a6bb-6c078bbc3985`. Its encrypted manifest checksum is
`afb842b7aee77ef4718a3069b76e8814f49285fe877e7cf253fab5589b4acaf1`. It did not overwrite the
earlier M6.2 backup, and no restore was performed.

The read-only live comparison is:

| Check | Before | After |
| --- | --- | --- |
| SQLite integrity / FK violations | `ok` / 0 | `ok` / 0 |
| Migration | `0013_password_recovery` | `0013_password_recovery` |
| Domain event count / high-water | 637 / 637 | 649 / 649 |
| Household / user count | 4 / 4 | 4 / 4 |
| Attachment versions / files | 39 / 40 | 39 / 40 |
| Database SHA-256 | `66a1e4c6e09dd2597e2a20cc48418a5bfe990eab28b4409b724e86dfd7e1cac7` | `1816bdba4fbe4f595224d642580ae5fd1191fcd08de0ed642152f56defd475d1` |
| WAL SHA-256 | `ae73e0ebd564c4baf87a1081a5779505c5a1ade7ef388d999dc5bfc5aee185de` | `f6ffd4bbb42abfe6fc22fa4b1b9f105d79324dfbc46cd56faf1d56975996e431` |

The 12-event delta is exactly six tagged demo shed sources plus their six causal void controls from
the two evidence runs. Every source is inactive in effective History and preserved in immutable
audit history. There was no unaccounted live event activity during the comparison. The final
attachment-tree SHA-256 is
`0ce316009a1127871bbe3101849b76df5b898b1c0d3386ec815e570659110c73`.

For the feeding follow-up, the immediate pre-deploy read-only baseline was migration
`0013_password_recovery`, SQLite integrity `ok`, zero FK violations, event count/high-water 650,
four households, four users, 39 attachment versions, and 40 attachment files. The final
count/high-water is 656 solely because of the six tagged demo qualification events enumerated
above. Final integrity remains `ok` with zero FK violations; household, user, and attachment counts
are unchanged. The final database SHA-256 is
`2c8013180775e050faab6d278b0dff9ba3f6c66b595bcfd91234dfedd798ec87`, WAL SHA-256 is
`22f32c0e17dbd899970da0518a7ba636df1858761c7cc9802013240251a87eae`, and attachment-tree SHA-256
remains `0ce316009a1127871bbe3101849b76df5b898b1c0d3386ec815e570659110c73`.

### Raspberry Pi deployment

The final deployed ARM64 image is `snaketracker:m62-feeding-form-fix`, image ID
`sha256:9064aef098cecbe0a2307d11e0d74f9e129722664da9747f1c48580c5c903499`. Web and worker run as
UID/GID `1001:1001`; web, worker, and pinned Nginx are healthy; Nginx remains bound only to
`127.0.0.1:8081`; both local and public readiness endpoints return `{"status":"ready"}`; and
exactly one `snaketracker` Compose stack is active. No migration was introduced or run for M6.2.

The final commit, hosted GitHub checks, and pull-request link are recorded after push. Technical
qualification does not constitute owner acceptance and does not authorize merge.
