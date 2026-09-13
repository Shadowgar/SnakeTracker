# M6.5-A2 Purchases, FIFO Valuation, and Cash-spend Facts

Status: **owner-accepted September 12, 2026**

Requirements `R-073` through `R-075`; acceptance procedures `AT-INVINT-04`, `AT-INVINT-05`,
and `AR-INVINT-01`. Branch `phase6.5/purchases-fifo`. This tranche was accepted before the complete
M6.5 milestone was owner-accepted September 13, 2026.

## Owner-review correction 2: guided Add inventory

The public defect was a stale-asset delivery failure. The source had gained a compact
`.choice-cards input[type="radio"]` override after the deployed page and stylesheet URL were already
using the unchanged `app.css?v=m65-a2` cache key. Cloudflare/browser caching (`max-age=14400`) could
therefore retain the earlier stylesheet, where the global full-width `input` rule rendered the
radios as giant controls. Direct-origin and public stylesheet SHA-256 were later identical at
`f7c0d55a37d7475d5381d69fb0b5d53837e94d5d6b83e9fc32e2603ef6021db5`; native public computed
style at diagnosis was a two-column grid with 359-pixel-wide, 46.78-pixel-high labels and normal
17.59-pixel radios. The correction removes dependence on that fragile visible-radio treatment and
bumps every affected asset URL to `m65-a2-owner-c2`.

The rebuilt page is one progressive task. Its initial state contains only **Existing item** and
**New item** segmented choices. Existing item reveals the Item selector; choosing an Item adds a
compact on-hand/value summary and only then reveals **Add stock** and **Add cost information**.
Add stock exposes quantity, dollar-prefixed Amount paid, and Date. Add cost information changes the
labels to quantity being assigned and amount originally paid, explains that stock quantity will not
change, and ends with **Save cost information**. New item opens the accepted A1 guided catalog flow
directly. Vendor, reference, default-USD Currency, and optional reorder threshold are under **More
details**. Semantic radios remain for native grouping and arrow-key behavior, but are visually
hidden; checked choices gain both a check mark and accent treatment, and focus remains visible.

Fresh public-runtime screenshots were captured and inspected at 390×844 and 1440×900 for all six
required states. Mobile keeps two 165.19×44.75-pixel choices in one useful row and the form within
372.39 pixels. Desktop keeps the form at exactly 672 pixels (42rem), with 311×47.75-pixel choices.
At both sizes the semantic input computes to an absolute, transparent 1×1-pixel box. There was no
horizontal overflow; every hidden branch had zero enabled controls; native arrow-key selection
worked. Twelve WCAG 2.2 AA axe scans reported zero violations. There were zero Care Keeper console,
page, HTTP, failed-request, or CSP errors. The only diagnostics were Cloudflare-injected inline
analytics loaders and `static.cloudflareinsights.com` beacon requests being correctly blocked by
Care Keeper's unchanged `script-src 'self'` policy.

Owner-review captures:

- [mobile initial](screenshots/owner-c2-mobile-390x844-initial.png)
- [mobile Existing before Item](screenshots/owner-c2-mobile-390x844-existing-before-item.png)
- [mobile Existing selected](screenshots/owner-c2-mobile-390x844-existing-selected.png)
- [mobile Add stock](screenshots/owner-c2-mobile-390x844-add-stock.png)
- [mobile Add cost](screenshots/owner-c2-mobile-390x844-add-cost.png)
- [mobile New item](screenshots/owner-c2-mobile-390x844-new-item.png)
- [desktop initial](screenshots/owner-c2-desktop-1440x900-initial.png)
- [desktop Existing before Item](screenshots/owner-c2-desktop-1440x900-existing-before-item.png)
- [desktop Existing selected](screenshots/owner-c2-desktop-1440x900-existing-selected.png)
- [desktop Add stock](screenshots/owner-c2-desktop-1440x900-add-stock.png)
- [desktop Add cost](screenshots/owner-c2-desktop-1440x900-add-cost.png)
- [desktop New item](screenshots/owner-c2-desktop-1440x900-new-item.png)

Machine-readable computed-style, progressive-disclosure, console, accessibility, and artifact
results are in [`owner-c2-browser-qualification.json`](owner-c2-browser-qualification.json).

The exact authoritative quality path (`uv sync --frozen`, then `./scripts/quality/check.sh`) passed:
formatting and Ruff across 452 files, the 42-ADR accepted architecture freeze, documentation links
across 206 files, strict mypy across 130 source files, all 563 tests, dependency audit, Compose
validation, and diff checks. Coverage was 94.66% lines and 85.01% branches. The promoted native
ARM64 image is `snaketracker:m65-a2-owner-c2`, SHA-256
`013f289d52491e26e060a969a7ad0930016a2b59bc856e57e53aa066a4c3d710`, running as `1001:1001`.
Web, worker, and Nginx are healthy; local and public readiness are ready; exactly one Care Keeper
Compose project is active.

No browser form was submitted against the live runtime. Before and after deployment the protected
database remained at migration `0016_inventory_acquisition`, integrity `ok`, zero foreign-key
violations, 724 events/high-water 724, and ordered event identity/checksum hash
`aad16abef4ddd1a6ea4d25565fc0e834369a8e4f577bac2a091680636963131a`. Counts remained four
households, four users, 42 Animals, 29 Enclosures, 23 Inventory Items, and 39 attachment versions.
The pre-deployment encrypted, non-overwriting backup was request
`685f7e7e-9911-4c48-a823-a21e32b26613`, run `4b249b13-fc42-418a-b571-9621c1eed88b`, with encrypted
manifest SHA-256 `b254dee5da247a3030442a93de178ed309fb10f8f80f72711bc083cfec0763a7` independently verified.
The active database and attachments were never reset, reseeded, replaced, restored over, or used
for destructive qualification.

## Owner-review correction: unified acquisition

The A2 owner-review correction replaces competing Add Item and Add Purchase entrypoints with one
keeper-facing **Add inventory** workflow. It creates and stocks a new structured Item in one atomic
operation, restocks an existing Item, or records cost for stock already on hand. A positive amount
creates one Purchase/cash-spend fact and known acquisition basis. An amount of zero creates only a
physical receipt: quantity is tracked, cost remains explicitly not tracked, and money reports get no
Purchase fact. Purchase detail and lifecycle controls remain available under **Purchase history**.

Existing-stock assignment uses the explicit **current remaining quantity** semantic accepted by the
correction request. A typed immutable `inventory.cost_assigned` fact identifies exact source-event
portions and offsets from currently remaining unknown-cost stock. It cannot exceed eligible quantity,
can be partial, and does not retroactively value stock consumed before assignment. Correction replaces
the effective assignment and its Purchase atomically. Void/reinstate removes/restores cost and cash
effects without changing physical quantity. No legacy receipt, Feeding, Expense, or Purchase event is
rewritten.

Keeper-facing templates and routes contain none of `FIFO`, `cost layer`, `uncosted layer`,
`acquisition layer`, or `depletion layer`. The internal deterministic policy and technical ADR retain
precise accounting terminology. Unknown cost remains distinct from known zero and is always displayed
as cost not tracked.

## Implemented boundary

- One Purchase aggregate represents a real receipt with one to 25 Inventory lines. Posting uses
  one atomic multi-stream append for the Purchase and every linked version-3 stock receipt.
- Every line uses the Item's same-household canonical unit and a stable line ID. Positive integer
  minor-unit subtotals plus tax and fees less discount must exactly equal the positive total paid.
- Largest-remainder allocation capitalizes shared charges exactly and uses stable line-ID tie
  breaking. No floating-point money, currency conversion, or mutable Item price is introduced.
- Purchase is the sole purchase cash-spend source and does not create an Expense event. The
  Expenses experience labels Supply purchases separately from Other expenses.
- FIFO orders effective layers/depletions by occurrence time, recorded time, global position, and
  event ID. Partial-lot cumulative allocation assigns the final remainder cent exactly. Currencies
  remain separate, and historical/manual stock without Purchase cost remains explicitly unknown.
- Purchase correction, void, and reinstatement coordinate Purchase and receipt streams atomically.
  Invalid stock removal fails without a partial Purchase, receipt, cash, or balance change.
- Balance, effective receipts, and Purchase current state remain synchronous correctness inputs.
  FIFO lots/allocations and unified cash-spend facts use asynchronous, rebuildable generations with
  checkpoint freshness and unavailable/lagging presentation.

## Migration and live-data safety

Expand-only migration `0015_purchases_fifo` adds `purchase_current`, `purchase_line_current`, and
`inventory_effective_receipts`. Owner-review correction migration `0016_inventory_acquisition` adds
the Purchase acquisition-mode discriminator and `inventory_effective_cost_assignments`. Existing
Purchase rows default to `stock_received`; no event or balance is rewritten. Generated FIFO/cash
tables remain rebuildable projection generations.

The correction was exercised from zero and from an encrypted, restored copy of the active 0015
database. The isolated upgrade target was
`/tmp/carekeeper-a2-correction-restore.l6jhMV/162943ce50554c4f8401720a120ec563/snaketracker.sqlite3`.
It reached 0016 with integrity `ok`, zero foreign-key violations, all 719 events/high-water 719, and
event identity/checksum hash
`80648271177fb19de64751de4e70739f4741074972ef97439d1e92ed1085d3ad` unchanged.

Before correction deployment, the worker-owned pipeline completed non-overwriting encrypted backup
request `48ec0532-3391-41c7-bc78-c16b32d18c90`, run
`162943ce-5055-4c4f-8401-720a120ec563`, with encrypted manifest SHA-256
`6c7253477d9c33e67e047acc965177f55648e66f5e0c3f860c53f001a335404e`. Restore was verified only
under `/tmp/carekeeper-a2-correction-restore.l6jhMV`, outside the active runtime. It restored revision
0015, 719 events/high-water 719, the exact event hash above, integrity `ok`, zero FK violations, and
33 referenced attachments. The active database was never a restore target.

The active paths were explicitly resolved as:

- database: `/home/rocco/SnakeTracker/runtime/phase2/snaketracker.sqlite3`
- attachments: `/home/rocco/SnakeTracker/runtime/phase2/attachments`

No destructive command targeted either path. The isolated migration root was
`/tmp/carekeeper-a2-migration.ba1MsJ`. A zero-to-head database and an online copied live snapshot
both migrated to 0015 with integrity `ok`, zero foreign-key violations, and eight active product
projection definitions. The copied snapshot retained all 717 events at high-water 717 and the
pre-migration event identity/checksum hash
`907bf04333c2fdde614f392b8f2bb282428b4bf754e5d3acf4f4e7e3cf81c7e7`.

Before copied-snapshot qualification and deployment, the worker-owned pipeline created encrypted,
non-overwriting backup request `3e6ed004-652c-43a2-9cfe-2eaf7e110899`, run
`5ff003fa-1265-422b-8fc4-0fcfcdb35ac4`, with encrypted manifest SHA-256
`8805e339986e215dc0ec7325f4d5913b6b82c0a3027f0e03f93f6ab0015812a7`. Independent verification
reported migration 0014, high-water 717, and 33 referenced attachments.

Restore was rehearsed only into isolated target
`/tmp/carekeeper-a2-restore-host.9Rvdg6/5ff003fa1265422b8fc40fcfcdb35ac4`. It reported integrity
`ok`, zero foreign-key violations, migration 0014, 717 events at high-water 717, the exact event
hash above, and 33 restored attachments. The isolated restored target was then removed; the active
database was never restored over.

## Automated qualification

Focused A2 integration/browser and projection-worker tests cover atomic posting, total validation,
idempotent retry, 25-line bounds, household isolation, correction/add/remove lines, refused void
rollback, reinstate, changing prices, partial quantities, final-cent reconciliation, backdating,
unknown cost, currency separation, cash uniqueness, projection lag, generation rebuild, and
rollback, unified acquisition validation, legacy-cost assignment bounds, and feeding-deletion cost
compensation. The exact authoritative command was:

```text
uv sync --frozen
./scripts/quality/check.sh
```

It passed formatting and Ruff across 452 files, the 42-ADR accepted architecture freeze,
documentation links across 206 files, strict mypy across 130 source files, all 561 tests,
dependency audit, Compose validation, and diff checks. Coverage passed at 94.66% lines and 85.01%
branches; `coverage.json`, `coverage.xml`, and `junit.xml` were generated.

## Native ARM64 browser and accessibility qualification

The owner-review correction ran in existing native ARM64 Chromium 1208 against the isolated fresh
target `/tmp/carekeeper-a2-correction-browser.JkS6PH`; the active database and attachments were not
mounted. At both 1440×900 and 390×844, the browser completed new paid Item (20 / $40), existing paid
restock (10 / $25), zero-amount untracked restock (5), current-stock cost assignment (20 / $36),
Inventory-authoritative Feeding, and R-083 feeding deletion. The final representative Items returned
to 35 on hand after deletion, with $65 known remaining value and five units cost-not-tracked. The
legacy Items remained 20 on hand while gaining $36 known value. Each viewport produced exactly the
expected two receipt Purchases and one quantity-neutral cost Purchase; zero-amount receipts produced
none.

Fourteen WCAG 2.2 AA axe checks reported zero violations. Both viewports had no horizontal overflow,
Care Keeper console errors, page errors, HTTP errors, or failed requests. The Feeding consumed one
unit and $2.00, then its typed deletion compensation restored stock and the cost allocation exactly
once. Normal UI exposed no FIFO jargon.

Correction owner-review captures:

- [desktop Add inventory](screenshots/correction-desktop-1440x900-add-inventory.png)
- [desktop tracked Item](screenshots/correction-desktop-1440x900-tracked-detail.png)
- [desktop mixed known/unknown cost](screenshots/correction-desktop-1440x900-mixed-cost-detail.png)
- [desktop existing-stock cost form](screenshots/correction-desktop-1440x900-legacy-cost-form.png)
- [desktop Purchase history](screenshots/correction-desktop-1440x900-purchase-history.png)
- [mobile Add inventory](screenshots/correction-mobile-390x844-add-inventory.png)
- [mobile tracked Item](screenshots/correction-mobile-390x844-tracked-detail.png)
- [mobile mixed known/unknown cost](screenshots/correction-mobile-390x844-mixed-cost-detail.png)
- [mobile existing-stock cost form](screenshots/correction-mobile-390x844-legacy-cost-form.png)
- [mobile Purchase history](screenshots/correction-mobile-390x844-purchase-history.png)

Machine-readable correction results are in
[`browser-qualification.json`](browser-qualification.json).

The correction is promoted as `snaketracker:m65-a2-correction`, ARM64 image
`sha256:ccafa69e4c473d61b578537fce2814451517247e55aa53c9c9094e28dc1b3ae8`,
built for and running as UID/GID `1001:1001` on the Raspberry Pi.

The write journey ran only against the isolated online snapshot target
`/tmp/carekeeper-a2-browser.kqgOum`, never the active database. Native Chromium exercised a
two-line Purchase, exact total reconciliation, one-row-per-click line editing, atomic stock
receipt, one cash-spend fact, two FIFO lots, correction, void, reinstatement, Inventory FIFO value,
and single rendering in Expenses. The final isolated state had Purchase stream version 4, two
active linked receipts, integrity `ok`, and zero foreign-key violations. The isolated runtime and
target were removed after evidence capture.

Seven isolated and four public-origin axe checks reported zero WCAG 2.2 AA violations. Both
1440×900 desktop and 390×844 mobile views had no document-level horizontal overflow. After the
complete attachment snapshot was present, isolated console capture reported zero application
errors, page errors, HTTP errors, or failed requests.

Owner-review captures:

- [desktop Purchase form](screenshots/desktop-1440x900-purchase-form.png)
- [desktop Purchase detail](screenshots/desktop-1440x900-purchase-detail.png)
- [desktop Inventory FIFO value](screenshots/desktop-1440x900-inventory-fifo.png)
- [desktop Expenses](screenshots/desktop-1440x900-expenses.png)
- [mobile Purchase form](screenshots/mobile-390x844-purchase-form.png)
- [mobile Purchase detail](screenshots/mobile-390x844-purchase-detail.png)
- [mobile Inventory FIFO value](screenshots/mobile-390x844-inventory-fifo.png)
- [live desktop Purchase form](screenshots/live-desktop-1440x900-purchase-form.png)
- [live mobile Purchase form](screenshots/live-mobile-390x844-purchase-form.png)

Machine-readable results and artifact paths are in
[`browser-qualification.json`](browser-qualification.json).

## Console and CSP decision

Public-origin console capture had zero Care Keeper JavaScript/runtime errors and zero CSP
violations caused by Care Keeper-owned resources. Cloudflare changed the public HTML by adding a
same-origin `/cdn-cgi/.../email-decode.min.js` loader plus one inline challenge loader that is not
present in the direct origin HTML. That injected code attempted to load
`static.cloudflareinsights.com/beacon.min.js` and execute paired inline scripts. Care Keeper's
intentional `script-src 'self'` policy blocked both, producing seven external-beacon and seven
paired inline-loader diagnostics during repeated navigations. Axe produced no CSP diagnostic in
this run. The origin and public response retained the same strict policy; no Cloudflare host,
`unsafe-inline`, `unsafe-eval`, nonce, hash, or other allowance was added.

## Promoted runtime and live integrity

Migration `0016_inventory_acquisition` is applied on the active database. Immediately before and
after deployment, SQLite integrity was `ok`, foreign-key violations were zero, and the database
retained 719 events at high-water 719. The ordered identity/checksum hash remained exactly
`80648271177fb19de64751de4e70739f4741074972ef97439d1e92ed1085d3ad`. Counts remained four
households, four users, 42 Animals, 29 Enclosures, 22 Inventory Items, and 39 attachment-version
rows. The same 40 attachment files retained content hash
`148367657887ab26b8a8d0bf8cb3fdd5eb33389241c8ce66ef430e01dfd6e3dc`. Migration created zero
cost assignments, as expected, and the version-2 Inventory costing projection rebuilt through
event 719 without error.

The live post-deployment checks were read-only for domain data. Web, worker, and Nginx remained
healthy on the one active Care Keeper Compose stack, with web and worker running the corrected
image as UID/GID `1001:1001`.

## Explicitly deferred

Physical/cycle counts, usage forecasting, remaining-duration/excess signals, and the advanced
Inventory Overview are M6.5-B work. Expanded reports/CSV and spending estimates remain M6.5-C.
This evidence records the owner's A2 acceptance but does not accept B, M6.5, or a later milestone.
