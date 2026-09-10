# M6.5-A1 Structured Inventory and Inventory-authoritative Feeding

Status: **technical qualification passed; owner review pending**

Requirements `R-084` and `R-085`; acceptance procedures `AT-INVINT-07` and `AT-INVINT-08`.
Branch `phase6.5/inventory-intelligence`. M6.5 is not complete or owner-accepted.

## Integrated baseline

Published M6.5 history was preserved and current main merge
`eeb58beb7f2ec42ac416c039a4ccfd72a23132b1` was integrated with normal merge commit
`ab7dc1827ec2a402bc995fd8f31a97134e635074`. Conflicts were documentation-only and retained both
the M6.5 plan/requirements and merged M6.2 `R-083`–`R-085` history. M6.2 care-record deletion and
feeding compensation remain present.

## Implemented product boundary

- New Items require one controlled Type and one Type-compatible controlled Unit from the central
  domain catalog. Whole/container quantities are exact whole multiples; mass/volume supports up to
  three decimals. Storage uses integer thousandths and never floating point.
- Food has controlled Whole prey, Insect, Prepared food, Pellets / Dry food, Produce, and Other
  categories. Whole prey requires prey, size/stage, and preparation; Insect requires feeder type
  and permits optional size; irrelevant prey fields are rejected for other categories.
- Create/Edit progressively exposes contextual controls, with server validation authoritative.
- Migrated legacy Items remain unclassified and visibly **Needs setup**. Original unit text and all
  quantities are retained. Only deterministic exact aliases can be confirmed after movement;
  ambiguous reinterpretation is rejected without conversion.
- Every normal new Feeding requires an active configured same-household Food Item and a positive
  canonical-unit amount. One transaction appends the version-2 Feeding and scaled Inventory use.
  Manual prey type/size/weight/preparation and **Do not deduct inventory** are absent.
- The Feeding snapshots Item ID/name, Food metadata, unit, amount, and outcome. Rename does not
  alter history. Accepted, refused, and regurgitated outcomes all retain consumption because the
  amount represents stock taken/offered.
- A1 correction is safely bounded to date/time, outcome, and notes while Food/amount remain fixed.
  Correction reverses/reapplies use atomically. Delete reverses once; reinstate reapplies only when
  valid. Old version-1 linked and unlinked Feedings continue to replay.

## Persistent compatibility

Expand-only migration `0014_structured_inventory_feeding` adds nullable catalog fields, parallel
scaled balances/threshold, and separate v2 consumption link/allocation tables. It never rewrites
events or guesses classifications. Runtime compatibility recognizes 0014 while 0013 requires a
forward migration. Destructive migration and restore checks use isolated targets only.

## Qualification record

### Isolated migration and replay

No destructive command targeted the active database or attachment store. The recorded isolated
qualification root was `/tmp/carekeeper-m65-a1-qualification.wK0vVS`:

- `fresh-zero-to-head.sqlite3` migrated from zero to `0014_structured_inventory_feeding` with
  SQLite integrity `ok`, zero FK violations, and an empty immutable event store;
- `pytest-upgrade/test_structured_inventory_upgr0/representative-0013-upgrade.sqlite3` completed a
  representative 0013→0014 upgrade with integrity `ok`, zero FK violations, and all nine immutable
  event IDs/checksums unchanged (`aa63ea7be60039a382e5f2f324cefc7202e16ad98ff1ca2c1f0a897997fef7a7`);
- the representative history retained old linked and unlinked Feeding replay, an effective M6.2
  void, the original legacy unit, and the exact `quantity * 1,000` scaled balance.

### Encrypted backup and live migration

The active paths were explicitly resolved as
`/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3` and
`/home/rocco/SnakeTracker/runtime/phase2/attachments`. Before deployment, the worker-owned pipeline
completed encrypted backup request `cd9b8742-b2bc-4d20-b2d7-f80f3d9ffa66`, run
`510a8afc-d35b-4988-bf90-86cb6db4464e`, with manifest SHA-256
`5e98a59fd51291a10c944cf437c03bcf15f838c2b675f2210734ff311d0924b2`. Prior backups were not
overwritten and no restore was performed.

Migration 0014 was then applied **in place** through the normal Compose migration service. The
database was not copied, replaced, reset, reseeded, or restored. The before/after preservation
boundary was:

| Check | Before deployment | After migration | After demo browser qualification |
| --- | --- | --- | --- |
| Revision | `0013_password_recovery` | `0014_structured_inventory_feeding` | `0014_structured_inventory_feeding` |
| Integrity / FK violations | `ok` / 0 | `ok` / 0 | `ok` / 0 |
| Household / user count | 4 / 4 | 4 / 4 | 4 / 4 |
| Event count / high-water | 660 / 660 | 660 / 660 | 675 / 675 |
| Attachment-version count | 39 | 39 | 39 |
| Inventory Item count | 8 | 8 | 10 (two archived qualification Items retained) |

All 660 pre-deployment event IDs/checksums retained hash
`8d319af13c6ebd84505dba2c65761bb032eec9c78ac55d76cbd6c7227f4555f2` after migration and after
browser qualification. The attachment tree retained SHA-256
`0ce316009a1127871bbe3101849b76df5b898b1c0d3386ec815e570659110c73`. All eight migrated Items
were preserved with exact scaled backfills and honest unclassified state. The browser's 15-event
delta is entirely in the reserved demo household: two v2 Item registrations, one receipt, two v2
Feedings and consumptions, two void/reversal pairs, one snapshot-preserving rename, one legacy Item
setup, and two archive facts. The demo fixture remains 20 animals and 16 enclosures. No customer
household event was appended by qualification.

### Browser, accessibility, and console

Native ARM64 Chromium exercised the deployed public origin at 390×844 and 1440×900. It created
**Small Frozen Mouse** as Food / Whole prey / Mouse / Small / Frozen-thawed / Each, received three,
recorded a Feeding, observed stock 3→2, deleted it through R-083, and observed 2→3. A second Feeding
retained the original immutable food description after the Item was renamed, then deletion restored
stock once. **Heat lamp** as Equipment never appeared in the Food selector. The pre-existing
**Basking bulbs 75W** Item visibly required setup and was classified Equipment / Each without its
stock changing from one. Created qualification Items were archived; no row was deleted.

The normal Feeding form had no no-deduction option and no manual prey type, prey size, prey weight,
or preparation inputs. Amount defaulted to one with the Item's unit. Both desktop pages had no
horizontal overflow. Five axe WCAG A/AA scans reported zero violations, with zero page errors and
zero Care Keeper-owned console diagnostics. The 66 external diagnostics were Cloudflare-injected
inline analytics and `static.cloudflareinsights.com` beacon scripts being rejected by the intended
`script-src 'self'` policy. Qualification instrumentation produced zero additional CSP diagnostics.
The production CSP was not changed or weakened.

Evidence: [browser result](browser-qualification.json),
[mobile create Food](screenshots/mobile-390x844-create-food.png),
[mobile Feeding](screenshots/mobile-390x844-feeding.png),
[mobile immutable snapshot](screenshots/mobile-390x844-history-snapshot.png),
[desktop create Food](screenshots/desktop-1440x900-create-food.png), and
[desktop Feeding](screenshots/desktop-1440x900-feeding.png).

### Authoritative gate and runtime

The exact `uv sync --frozen` followed by `./scripts/quality/check.sh` completed successfully: 510
tests passed; statement/line coverage was 94.88%, branch coverage 85.08%, and combined coverage
93.00%. Ruff, strict mypy across 125 source files, dependency boundaries, the freeze across 42
accepted ADRs, 205-file documentation links, strict dependency audit with no known vulnerabilities,
Compose validation, and diff checks passed. Coverage JSON/XML and JUnit artifacts were produced.

The deployed `linux/arm64` image is `snaketracker:m65-a1`, image ID
`sha256:b6a501d54144f3a563cf4c7dc037b55a65552872f36e5a9ffe7aea550520ac52`. Web, worker, and pinned
Nginx are healthy; web/worker run UID/GID `1001:1001`; Nginx remains bound to `127.0.0.1:8081`;
local and public readiness are ready; and exactly one `snaketracker` Compose project is active.
Hosted checks and the final commit are reported in the owner handoff after push. This evidence does
not mark M6.5 accepted.

## Explicitly deferred

M6.5-A2 and later retain Purchase aggregate/receipts, FIFO lots and valuation, cash-spend
integration, physical/cycle counting, forecasting, estimated duration, advanced Inventory
Overview, and cost/expense reporting. The requested future administrator/operator login/activity
audit console is also deferred outside A1.
