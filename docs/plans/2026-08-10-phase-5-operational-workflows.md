# Phase 5 Operational Workflows Implementation Plan

> **For Codex:** Execute this plan task-by-task with test-driven development after explicit owner
> approval. Do not implement Phase 6 search, reports, dashboards, charts, or PWA scope.

**Goal:** Deliver M5 inventory, expense, reminder, and durable-delivery workflows with provable
concurrency, compensation, deduplication, lease, crash-recovery, reconciliation, and dead-letter
behavior.

**Architecture:** Inventory items, expenses, and reminder rules remain event-sourced aggregates.
Inventory/current-rule/expense-current projections are synchronous where command correctness
depends on them. Reminder facts, notification intent, outbox handoff, durable jobs, delivery
attempts, and provider operations are separate operational stages with independent stable keys.
The M3 atomic append and outbox seam is extended without rewriting M3 events or M4 animal history.

**Tech stack:** Python 3.13, FastAPI/Jinja, synchronous SQLAlchemy/SQLite, Alembic, pytest,
Playwright, Docker Compose, and the existing `uv` lockfile and quality gate.

---

## Scope and governing decisions

The authoritative exit criteria are the five unchecked M5 release blockers in
[the milestone roadmap](../roadmap/milestones.md#phase-5--m5--operational-workflows-reliable).
Implementation is governed primarily by ADR-0002, ADR-0004, ADR-0005, ADR-0006, ADR-0007,
ADR-0011, ADR-0012, ADR-0013, ADR-0014, ADR-0015, ADR-0023, ADR-0025, ADR-0030, ADR-0031,
ADR-0032, ADR-0034, ADR-0035, and ADR-0038.

The relevant traceability requirements are R-002, R-004 through R-006, R-011 through R-014,
R-016, R-024, R-031 through R-035, R-039, R-041, and R-044. M5 will add evidence links for its
roadmap-specific inventory and expense acceptance procedures without changing their accepted
aggregate or event-catalog decisions.

M5 extends these existing seams:

- M3 `AtomicAppendRequest`, deterministic multi-stream expected-version checks, atomic command
  idempotency, registered event contracts, correction/compensation controls, and `outbox_items`;
- M4 animal feeding commands and immutable care history, without changing or rewriting any stored
  M4 feeding events;
- M4 current-authorization checks, keeper-facing progressive forms, security audit, Compose worker,
  and local backup behavior.

Explicitly excluded are FTS/global search, reports, charts, dashboard statistics, PWA/offline work,
remote/public deployment, Raspberry Pi qualification, real third-party provider selection, animal
health, breeding, plugins, and all other M6+ work.

## Domain and operational rules

### Inventory

- The aggregate and stream remain Inventory Item / `inventory-item:{item_uuid}`.
- Register the existing catalog contracts beginning at schema version 1: item registration, stock
  receipt, reservation, consumption, consumption reversal, authorized adjustment, expiry, and
  reorder-policy change.
- `inventory_balance` is a synchronous projection. Commands cannot make available, reserved, or
  on-hand quantities invalid. Authorized reconciliation uses `inventory.stock_adjusted` with an
  explicit reason; historical stock events are never mutated or generically voided.
- A feeding that consumes stock atomically appends the unchanged M4 feeding contract and the M5
  inventory consumption contract with expected versions for both streams, one correlation lineage,
  one idempotency result, and both synchronous projections.
- Correcting or voiding a stock-linked feeding must atomically reverse the prior consumption and,
  when applicable, append the replacement consumption. Unsupported generic controls are withheld
  rather than allowing animal and inventory state to diverge.
- Concurrent commands use separate database connections in qualification tests. One valid winner
  commits; stale expected versions fail with a typed conflict; equivalent retries return the stored
  result; no path permits a negative or double-consumed balance.

### Expenses

- The aggregate and stream remain Expense / `expense:{expense_uuid}`.
- Register `expense.recorded`, `expense.corrected`, and `expense.voided` version 1 contracts.
  Corrections replace effective financial facts through new events; voids preserve the original
  record and reason. Expense events are not rewritten, and no relational expense table becomes a
  second source of truth.
- Financial reads and commands require current household ownership plus explicit `expense.view` or
  `expense.manage` capability. Owner and Administrator receive management capability; Caretaker and
  Viewer do not receive financial access. Capability evaluation remains projection-backed on every
  request.
- The initial correction policy permits Owner/Administrator corrections and voids at any record age,
  requires a non-empty reason, records security audit context, and does not support reinstatement.
  This avoids silently hiding older financial mistakes while keeping the policy explicit and tested.

### Reminders and delivery

- Reminder Rule / `reminder-rule:{rule_uuid}` owns schedule, subject, activation, recipient/channel
  selection, and uses the existing rule-created, rule-changed, and rule-disabled contracts.
- `reminder_rule_current` is synchronous. Rebuildable `reminder_facts` derive factual due occurrences
  from current rules and authoritative care projections; a fact is not a notification request.
- Rules support fixed intervals and event-relative schedules, per-animal owner configuration,
  enable/disable state, and an explicit due-date or interval override. M5 encodes no species advice.
- Event-relative rules use latest effective qualifying history: accepted feeding, weight, length,
  bath/soak, enclosure cleaning, or water change. Refused and regurgitated feedings do not reset an
  accepted-feeding schedule. Corrections replace the source, voids fall back to the previous
  effective source, and reinstatements restore the source when it is again effective.
- Each due/overdue fact retains rule/version, schedule kind, configured interval/override, source
  kind and effective occurrence time, calculated due time, and a technical source reference. Normal
  keeper views render that provenance as an explanation without exposing raw event identifiers.
- A notification intent is operational and unique by rule occurrence, recipient, and channel.
  Its outbox handoff is unique by intent and payload contract. The durable job is unique by handler
  type and logical operation. Each delivery attempt is unique by job, attempt number, and lease
  token. Provider idempotency uses a stable key derived from the intent/channel, not the attempt.
- Converting a pending M3 outbox item into a job and marking the handoff complete occurs in one
  SQLite transaction. A duplicate handoff or worker restart returns the same logical job.
- Reminder facts, intent, outbox, jobs, and attempts remain conventional relational/projection state,
  not domain events. Their state changes are observable but never added to business streams.

### Durable job and uncertain-effect rules

- Jobs persist payload contract/version, household, priority, availability, status, attempts and
  maximum attempts, lease owner/token/acquired/heartbeat/expiry times, logical and idempotency keys,
  correlation/causation, timestamps, safe error, external operation reference, and result schema.
- Claim is atomic. Only the current opaque lease token may heartbeat, succeed, retry, reconcile, or
  dead-letter a job. Expired leases are reclaimable after the previous token is fenced out.
- The default is five attempts with bounded exponential backoff and injected jitter. Permanent
  failures and exhausted retries become visible dead letters. Manual retry of an uncertain external
  result requires reconciliation first and produces a security-audit record.
- External execution is explicitly at least once. The first M5 adapter is a deterministic local
  qualification provider with provider-style idempotency and lookup by stable operation key; it
  performs no real email/SMS delivery. Fault injection will crash after provider acceptance but
  before local completion. Recovery reuses the same provider key, reconciles the durable external
  operation ID, records one logical effect, and completes the original job.
- Adapter registration must declare provider idempotency, external-ID/read-before-write
  reconciliation, or an explicitly approved bounded duplicate tolerance. An adapter declaring none
  fails startup/registration safely.

## Test-driven task sequence

### Task 1: Lock M5 contracts, scope, and migration lifecycle

**Files:** create `migrations/versions/0009_operational_workflows.py`, contract/replay fixtures under
`tests/fixtures/events/`, and update compatibility, migration, architecture-scope, and traceability
tests.

Write failing tests first for the exact new tables, constraints, indexes, event registrations,
unknown-contract behavior, Phase 2/3/4 fixture replay, and upgrade/downgrade/re-upgrade. Implement
one forward expand migration after `0008_local_backups`; never edit accepted revisions.

### Task 2: Inventory contracts and synchronous balance

**Files:** create `src/snaketracker/domains/inventory/contracts.py`,
`src/snaketracker/application/inventory.py`, and
`src/snaketracker/infrastructure/inventory/projections.py`; add unit and integration tests under
`tests/unit/domains/` and `tests/integration/`.

Drive item registration, receipt, reservation, consumption, reversal, expiry, adjustment, replay,
unit validation, same-household subjects, and balance invariants from failing tests.

### Task 3: Inventory concurrency and idempotency

**Files:** extend inventory integration tests and the existing event-store concurrency fixtures.

Prove stale-version conflicts, deterministic two-stream ordering, equivalent retry results,
idempotency-hash conflicts, rollback on invariant failure, and correct balances under simultaneous
receipt/consume/adjust operations using independent connections.

### Task 4: Stock-linked feeding and compensation

**Files:** modify `src/snaketracker/application/animals.py`, the feeding form/view-model paths in
`src/snaketracker/presentation/`, and focused animal/inventory browser and integration tests.

Add the optional stock selection without changing M4 event payloads. Test atomic feeding plus stock
consumption, correction replacement, void reversal, failed compensation rollback, and absence of an
unsafe generic control when the linked compensation cannot be formed.

### Task 5: Expense contracts, authorization, and effective history

**Files:** create `src/snaketracker/domains/expenses/contracts.py`,
`src/snaketracker/application/expenses.py`,
`src/snaketracker/infrastructure/expenses/projections.py`, focused templates, and unit/integration/
security/browser tests.

Test recording, correction, voiding, effective totals, immutable history, reason policy, cross-
household denial, current-capability checks, CSRF, idempotency, expected versions, and safe audit
details before implementing the keeper-facing expense list and focused forms.

### Task 6: Reminder-rule contracts and effective-history factual occurrences

**Files:** create `src/snaketracker/domains/reminders/contracts.py`,
`src/snaketracker/application/reminders.py`,
`src/snaketracker/infrastructure/reminders/projections.py`, and clock-controlled tests.

Test fixed-interval rules; event-relative rules; per-animal intervals; enable/disable and owner
overrides; last effective accepted-feeding semantics; refusal and regurgitation behavior; corrected,
voided, and reinstated effective care history; weight, length, bath, enclosure-cleaning, and
water-change facts; due/overdue provenance; household-timezone and DST behavior; five-minute
future-skew policy; subject tenancy; deterministic occurrence keys; rule changes; rebuild; and
repeated scheduler scans before adding rule management and factual due-state reads.

### Task 7: Notification intent and atomic outbox-to-job handoff

**Files:** create application-owned contracts under `src/snaketracker/platform/notifications/` and
`src/snaketracker/platform/jobs/`, SQLite adapters under `src/snaketracker/infrastructure/`, and
integration tests for every dedupe boundary.

Test duplicate fact scans, intent creation, outbox handoff, atomic job creation, restart recovery,
malformed payload quarantine, and cross-household isolation. Preserve the existing M3 outbox rows
and uniqueness semantics while expanding their lifecycle.

### Task 8: Durable job claim, lease, heartbeat, and fencing

**Files:** create `src/snaketracker/infrastructure/jobs/repository.py`,
`src/snaketracker/worker/jobs.py`, and deterministic repository/worker tests.

Test simultaneous claims, opaque-token fencing, heartbeat extension, expiry takeover, stale-worker
completion rejection, graceful shutdown, and worker restart before integrating the job poller with
the existing backup worker loop.

### Task 9: Retry, reconciliation, and dead-letter operations

**Files:** extend job application/repository modules, authenticated operations views, structured
metrics/logging, and security-audit tests.

Test injected transient/permanent errors, exact attempt accounting, capped backoff, exhaustion,
dead-letter visibility, authorized reconciliation, forbidden blind retry of uncertain work, and
safe redaction of payload/error data.

### Task 10: Uncertain external-side-effect crash qualification

**Files:** create the provider port and local qualification adapter under
`src/snaketracker/infrastructure/notifications/`; add fault-injection contract tests.

Prove the crash window after accepted provider work and before local completion: restart, reclaim,
stable provider key reuse, lookup/reconciliation, durable external operation ID, one logical effect,
one terminal job result, and complete attempt history. Also prove that an unsafe adapter cannot be
registered.

### Task 11: Keeper workflows and accessibility

**Files:** add inventory, expense, reminder, and operations templates/routes/view models; extend
`src/snaketracker/presentation/static/app.css`; add Playwright and accessibility tests.

Test desktop/mobile navigation, values and units, correction/compensation explanations, conflict
pages, keyboard/focus/error summaries, dead-letter/reconciliation status, protected routes, CSRF,
and no leakage across households. Ordinary reminder schedules are configured from each animal
profile and automatically maintain one logical underlying rule. The Reminders page is a care agenda
grouped as overdue, due today, and upcoming; it explains calculations such as “10 days after last
accepted feeding” without ordinary rule-management controls. Event IDs remain behind technical
disclosure. Do not add M6 dashboards, charts, search, predictions, recommendations, or PWA
behavior.

### Task 12: M5 qualification and evidence

Run the full quality gate, migration lifecycle, Phase 2/3/4 compatibility fixtures, concurrency and
crash matrices, backup regression, amd64 Compose lifecycle, ARM64 image build, browser workflows,
accessibility checks, dependency audit, architecture freeze, documentation links, GitHub Quality,
Container/Trivy, GitGuardian, and substantive review. Record M5 as implementation-qualified with
owner acceptance pending; do not mark it accepted or merge until owner review.

Qualification must prove event-relative scheduling remains correct across correction, void,
reinstatement, authoritative replay/rebuild, repeated scans, worker restart, and duplicate
execution. The accepted M3/M4 fixtures remain byte-for-byte unchanged.

## Requirements-to-tests and evidence mapping

| M5 criterion | Requirements / ADRs | Acceptance tests | Proposed evidence |
|---|---|---|---|
| Inventory correct under concurrency and compensation | R-005, R-006, R-011, R-012; ADR-0006, 0007, 0011, 0012 | `AT-INV-01` balance/concurrency; `AT-INV-02` feeding compensation | `docs/evidence/m5-operations/tests/inventory.md` |
| Expenses enforce authorization and correction policy | R-005, R-016, R-032, R-033; ADR-0006, 0015, 0031, 0032 | `AT-EXP-01` capability/tenancy; `AT-EXP-02` effective correction/void | `docs/evidence/m5-operations/tests/expenses.md`, `security/authorization.md` |
| Pipeline stages deduplicate independently | R-012, R-014; ADR-0012, 0014 | `AT-NOT-01` fact/intent/outbox/job/attempt boundary matrix | `docs/evidence/m5-operations/tests/notifications.md` |
| Reminder schedules use effective history and explain their due facts | R-005, R-031, R-044; ADR-0006, 0014, 0030, 0038 | `AT-REM-01` fixed/event-relative correction/void/reinstate/rebuild matrix | `docs/evidence/m5-operations/tests/reminders.md` |
| Lease expiry, crash recovery, retry, reconciliation, dead letters | R-013, R-024; ADR-0013, 0023 | `AT-JOB-01` lease/fencing/crash matrix; `AT-JOB-02` retry/dead-letter/reconcile | `docs/evidence/m5-operations/tests/jobs.md`, `operations/crash-recovery.md` |
| External uncertain crash window is controlled | R-013, R-014; TM-11; ADR-0013, 0014 | `AT-EXT-01` accepted-effect crash and recovery | `docs/evidence/m5-operations/tests/external-effects.md` |
| Existing platform and keeper history remain compatible | R-002, R-004, R-034, R-039 | `AT-COMP-M5-01` Phase 2/3/4 fixtures and migration lifecycle | `docs/evidence/m5-operations/operations/compatibility.md` |
| Local Docker/ARM64 development qualification | R-041; ADR-0036 | `DEV-PLAT-M5-01` amd64 Compose plus ARM64 build | `docs/evidence/m5-operations/containers/README.md` |

The evidence root will also contain `README.md`, `browser/README.md`,
`accessibility/README.md`, `reviews/README.md`, `approvals/release/README.md`,
`evidence-manifest.json`, and `checksums.sha256`. Every record will retain the source revision,
environment, exact reproduction command, result, and reviewer.

## Proposed commit sequence

1. `docs: add Phase 5 operational workflows plan`
2. `test: define M5 contracts and migration boundaries`
3. `feat: add inventory events and balance projection`
4. `feat: make feeding inventory consumption atomic`
5. `feat: add authorized expense workflows`
6. `feat: add reminder rules and factual occurrences`
7. `feat: add notification intent and outbox handoff`
8. `feat: add leased durable job execution`
9. `feat: add retry reconciliation and dead letters`
10. `test: prove external effect crash recovery`
11. `feat: add accessible operational workflow screens`
12. `test: qualify Phase 5 operational workflows`
13. `docs: record M5 implementation evidence`

Each implementation commit follows red/green/refactor discipline and is independently reviewable.
Rollback before acceptance is a normal revert of the affected commit; schema rollback uses the
tested Alembic downgrade only after stopping workers and confirming no newer M5 data must be kept.
Existing M3/M4 events are never rewritten as a rollback technique.

## Owner-approved implementation decisions

1. The expense policy is Owner/Administrator only, requires a correction/void reason, has no age
   cutoff, and does not support reinstatement in M5.
2. The deterministic local qualification provider proves the real at-least-once,
   provider-idempotency, external-operation-ID, and reconciliation contracts without selecting or
   contacting a production email/SMS provider.
3. Delivery uses five maximum attempts with bounded exponential backoff and injected jitter,
   matching the accepted runtime-operations default.

## M6 extension points retained without M6 implementation

M6 consumes Reminder Rules, effective reminder facts, effective feeding/measurement/shed/bath
history, and enclosure cleaning/water-change history. It may add weight and length trends, feeding
outcome/interval statistics, shed and other husbandry-frequency statistics, due/overdue dashboard
presentation, and explainable estimated feeding or shed windows when sufficient history exists.

Optional species/life-stage reference profiles are curated, sourced, versioned reference data.
They prefer ranges, leave unsupported combinations empty, and never silently replace the owner’s
schedule. M6 analytics, recommendations, and reference profiles remain read-side components with no
new prediction/statistics/recommendation aggregate. These deterministic extensions are not the
deferred AI assistant.

The owner approved these decisions and the scheduling amendment on August 10, 2026. Phase 5
implementation may proceed; Phase 6 remains prohibited.
