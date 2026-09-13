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

## Owner-review correction 2: guided creation

The second owner-review correction completes Add Inventory as one guided operation. Its initial
state contains only Type and Item name: no contextual fieldset, generic Unit picker, or Starting
quantity is exposed before Type supplies enough context. Selecting a Type reveals only that Type's
controlled hierarchy. Changing the hierarchy disables and clears stale descendants in the browser,
while server normalization independently rejects invalid combinations and ignores irrelevant
metadata.

Units now come from the same domain catalog used by server validation. Discrete contexts show a
read-only **Tracked as** value and require no unit interaction; measured contexts show only their
applicable units with a recommended default. Whole prey and insects resolve to Each; Monitoring /
Thermometer, Heating & Lighting / Halogen bulb or Fixture / Tank light resolve to Each; Substrate /
Brick resolves to Brick; powders offer mass units; and liquids offer volume units. Other remains a
controlled stock-basis escape hatch rather than restoring free-text units. Keeper-facing balance
text uses sensible singular/plural forms.

Starting quantity follows the resolved Unit and precedes the optional reorder threshold. It accepts
zero, exact thousandth-scale measured quantities, and whole multiples for discrete units; negatives,
excess precision, and fractional whole units are rejected without floating point. The idempotent
registration command atomically appends Item registration plus one stock-received event when the
quantity is positive. The latter carries deterministic reference **Initial stock**, no keeper-entered
reason, vendor, purchase, or cost, so it is distinguishable and remains uncosted for A2. A zero
quantity appends registration only. Transaction rollback prevents an orphan Item, and retrying the
same operation neither duplicates the Item nor doubles stock.

### Deployed browser acceptance

Native ARM64 Chromium exercised the corrected public origin at both 390×844 and 1440×900. The
required Rat path revealed Food category only after Food, then prey controls only after Whole prey;
it resolved Small / Frozen-thawed / Rat to Each and one Add Item submission immediately displayed
**20 each on hand**, with no Receive stock step or reason prompt. A quantity-one Feeding changed
20→19 and deletion through R-083 compensated exactly once back to 20. Additional one-submit cases
produced Medium Dubia Roach at 75 each, Tank Light at 1 each, Coconut Husk Brick at 6 bricks, and
Powder Supplement at 500 g. All correction qualification Items are preserved as archived facts in
the fictional demo household; no row was manually deleted.

Final axe WCAG A/AA scans covered the initial and configured form at mobile and desktop plus the
mobile Item detail and reported zero violations. Hidden controls are disabled and removed from the
focus order. A normal-CSP console capture had zero page errors and zero Care Keeper JavaScript or
resource failures. It showed only Cloudflare's appended `static.cloudflareinsights.com` beacon and
inline challenge script being rejected by the intentional `script-src 'self'` policy. The served DOM
separately shows Care Keeper's allowed `/static/inventory-form.js?v=m65-a1-c2` immediately before
those injected nodes. Axe ran in a separate bypass-CSP qualification context, so its injection did
not obscure the application-console result. Production CSP was not changed or weakened.

Evidence: [correction 2 browser result](browser-qualification.json),
[mobile initial form](screenshots/correction2-mobile-390x844-initial.png),
[mobile guided Rat form](screenshots/correction2-mobile-390x844-rat-guided.png),
[mobile immediate balance](screenshots/correction2-mobile-390x844-rat-balance.png),
[desktop initial form](screenshots/correction2-desktop-1440x900-initial.png), and
[desktop guided Rat form](screenshots/correction2-desktop-1440x900-rat-guided.png).

### Correction 2 safety, gate, and runtime

No schema change was needed; migration head remains `0014_structured_inventory_feeding`, and all
legacy Inventory rows and their original quantities/units remain intact. Before deployment, the
active database and attachment paths were explicitly resolved to the paths above. The verified,
encrypted, non-overwriting backup request `fd4324b3-07ff-4731-9547-df23d595ecca` completed as run
`5b975a93-3afa-4b99-9b28-0800c3c25802`; its encrypted manifest SHA-256 is
`8fa4895cae34c03d935cd6bb1daaba8d1d36afd1386587dfe7a36f707aaf9d37`. Independent verification
found migration 0014, event high-water 680, and 33 referenced attachment versions. No restore was
performed.

The final read-only live check reports SQLite integrity `ok`, zero FK violations, migration 0014,
four households, four users, 42 animals, 29 enclosures, 39 attachment versions, and 40 attachment
files. The 29-event qualification delta from high-water 680 to 709 belongs entirely to the reserved
fictional household; the other three households remain at their baseline event counts of 116, 2,
and 5. All 680 pre-qualification event IDs/checksums retain canonical SHA-256
`c66dd92c01dd6101e16eb7b32764c2b8807142998bca2207bb0678478a8e2a2e`, and the attachment tree
retains SHA-256 `0ce316009a1127871bbe3101849b76df5b898b1c0d3386ec815e570659110c73`.
The demo remains 20 animals and 16 enclosures. The additional seven Inventory rows are archived
qualification facts; no customer household was mutated.

The exact frozen-environment path (`uv sync --frozen`, then `./scripts/quality/check.sh`) passed:
530 tests, line coverage 94.84%, branch coverage 85.04%, combined coverage 92.96%, Ruff, strict
mypy over 125 source files, architecture checks and the 42-ADR freeze, 205-file documentation-link
validation, dependency audit with no known vulnerabilities, Compose validation, and diff checks.
Coverage JSON/XML and JUnit artifacts were produced. The deployed `linux/arm64` image is
`snaketracker:m65-a1-c2`, image ID
`sha256:b8dffc64e5c099a85d540834c4cca81b9a377a36c5d96d85d84393ab27ce1a57`.
Web, worker, and Nginx are healthy; web/worker run UID/GID `1001:1001`; the bind remains
`127.0.0.1:8081`; local/public readiness are ready; and exactly one Care Keeper Compose project is
active. Hosted checks and the correction commit are recorded in the final owner handoff after push.
This correction remains pending owner review.

## Explicitly deferred

M6.5-A2 and later retain Purchase aggregate/receipts, FIFO lots and valuation, cash-spend
integration, physical/cycle counting, forecasting, estimated duration, advanced Inventory
Overview, and cost/expense reporting. The requested future administrator/operator login/activity
audit console is also deferred outside A1.
