# Phase 5.5 Multi-species Animal Foundation Implementation Plan

> **For Codex:** Use `superpowers:executing-plans` and test-driven development after explicit owner
> approval. Do not begin M6 search, reports, dashboards, analytics, predictions, reference guidance,
> or PWA expansion.

**Goal:** Preserve every existing snake workflow while making one household collection support
usable Snake and Spider profiles whose screens, commands, reminders, and history expose only
applicable care capabilities.

**Architecture:** Keep one Animal aggregate and `animal:{uuid}` stream. Add trusted, versioned
`snake.v1` and `spider.v1` capability profiles; replay `animal.registered` v1 unchanged as snake;
use additive `animal.registered` v2 for new typed registrations. Shared services remain shared.
Spider molt/premolt are typed Animal events, while configured misting/watering stays neutral
Enclosure care. Application and domain checks both enforce capability eligibility.

**Stack:** Existing Python 3.13, FastAPI/Jinja, synchronous SQLAlchemy/SQLite, Alembic, pytest,
Playwright, Docker Compose, and committed `uv.lock`. No new frontend framework, plugin system, or
database is authorized.

---

## Scope, governance, and acceptance

ADR-0039 governs this milestone with ADR-0001, ADR-0002, ADR-0004 through ADR-0008, ADR-0011,
ADR-0012, ADR-0014 through ADR-0018, ADR-0020, ADR-0025, ADR-0026, ADR-0030 through ADR-0035, and
ADR-0038. Traceability requirements R-047 through R-053 and the unchecked M5.5 roadmap criteria are
the release blockers. Existing M0-M5 behavior is a compatibility gate, not migration input to be
normalized.

M5.5 is complete only after technical qualification, evidence capture, reviewer disposition, and
explicit owner acceptance. Until then its roadmap boxes remain unchecked and M6 remains unstarted.

## Deliverables and responsibility split

### Shared Animal foundation

- Add application-owned `AnimalType`/`CapabilityProfile` value types and a closed production
  registry containing `snake.v1` and `spider.v1`. Registry definitions declare actions,
  measurements, schedule kinds, typed contract families, and view keys; they contain no keeper
  intervals or executable user data.
- Keep household ownership, name, species, applicable sex/date fields, acquisition/source, status,
  notes, photos, enclosure assignment, feeding, inventory consumption, expenses, reminders,
  timeline, attachments, backup, authorization, and historical controls in their existing owners.
- Validate the current profile in application commands and domain policy. Route/template filtering
  improves usability but never replaces server-side rejection.

### Snake compatibility profile

- Map every legacy `animal.registered` v1 stream deterministically to `snake.v1` during replay and
  projection rebuild. Do not upcast, rewrite, or append a synthetic type event to legacy streams.
- Preserve current profile, feeding, weight, length, shed/correction, bath/soak, enclosure,
  cleaning/water, photo, reminder, inventory, expense, attachment, backup, and timeline behavior.
- Retain historical contract names and keeper terminology where it is specifically snake care.

### Spider profile

- Register `animal.registered` v2 with common profile fields plus registered animal type and
  capability-profile version. New Snake and Spider registrations both use v2 after migration.
- Add version 1 typed payloads and registry policies for `animal.molt_recorded`,
  `animal.molt_corrected`, and `animal.premolt_observed`. Molt correction is append-only and uses
  the existing effective-history rules. A later premolt observation supersedes the current state;
  no mutable business-history row is introduced.
- Reuse feeding outcome/refusal/prey facts and optional weight. Reject length, snake shed, and
  bath/soak commands for `spider.v1` even if a client posts directly to an old route.
- Add `enclosure.misting_recorded` v1 for keeper-configured watering/misting care in the neutral
  Enclosure stream. It may have a same-household related-animal subject but must not make occupancy
  or the enclosure type-specific.

### Read and user experience

- Extend `animal_current` with animal type and capability-profile version. One household list shows
  all animals with name, species, type label, photo, status, and current enclosure; filtering is
  optional presentation state, not separate storage.
- Build profile action groups and schedule choices from allow-listed capability view definitions.
  Snake retains current actions; Spider receives feeding, optional weight, molt, premolt,
  enclosure/rehousing, photos/notes, applicable schedules, expenses, and history.
- Render human-readable effective timeline entries with corrections and technical disclosure.
  Spider terminology says molt/premolt; historical snake events remain shed/bath as applicable.
- Replace globally snake-only copy only where a mixed collection makes it inaccurate. Preserve the
  SnakeTracker product name and stable contract identifiers.

## Migration and compatibility strategy

Create one forward Alembic revision, `0010_multispecies_foundation`, after
`0009_operational_workflows`. It adds non-null `animal_type` and `capability_profile_version`
projection columns using an expand/backfill/constrain sequence that SQLite can upgrade and
downgrade safely, plus an allow-listed household/type index if query measurement justifies it.
Existing rows backfill to `snake`/`1`, derived from v1 registration semantics. Event tables and
payload bytes are untouched.

Projection replay must produce the same legacy snake state from an empty read model. Unknown v2
animal types, profile versions, Spider contracts, or newer schemas stop startup/replay through the
existing compatibility mechanism. Backup/restore includes the additive projection schema and all
unchanged events/attachments. Downgrade is permitted only while no v2 registration or Spider event
would be lost; otherwise it fails safely with an operator-readable compatibility error.

## Test-driven task sequence

### Task 1 — Lock governance, scope, and compatibility fixtures

**Files:** extend `tests/architecture/`, `tests/compatibility/`, and permanent event fixtures under
`tests/fixtures/events/`; add the M5.5 evidence skeleton only when implementation starts.

Write failing scope tests that prohibit M6 packages/contracts and production loading of arbitrary
profiles. Freeze representative pre-M5.5 snake streams, projection results, backup manifests, and
keeper responses before changing runtime code.

### Task 2 — Add the capability domain model and trusted registry

**Files:** add `src/snaketracker/domains/animals/capabilities.py`; update animal application ports
and focused unit tests.

Test profile identity/version validation, exact Snake/Spider capability matrices, duplicate and
unknown registration failure, immutable definitions, and the absence of imports between feature
slices. Then implement the smallest closed registry and policy queries.

### Task 3 — Add registration v2 without changing v1

**Files:** extend animal contracts/upcasters beside their historical fixtures, production event
registry, application registration command, and unit/integration tests.

Test byte-for-byte preservation and replay of stored v1 envelopes/payload/checksums, deterministic
v1-to-`snake.v1` interpretation, typed v2 validation, unknown type/version safe failure, subject
tenancy, idempotency, and expected stream version before registering v2.

### Task 4 — Implement the additive relational migration and projections

**Files:** add `migrations/versions/0010_multispecies_foundation.py`; extend
`infrastructure/animals/projections.py`, query models, migration tests, and rebuild fixtures.

Test fresh upgrade, upgrade from an M5 database, snake backfill, downgrade safety, re-upgrade,
`foreign_key_check`, projection drop/replay, mixed-type queries, and interruption rollback. Do not
modify migrations 0001 through 0009.

### Task 5 — Enforce capabilities across existing Snake commands

**Files:** update animal application services, reminder eligibility policy, and authorization/
integration tests without changing existing v1 event schemas.

First prove every existing Snake action still succeeds. Then prove direct Spider requests for
length, shed, or bath fail with a stable validation error and append nothing. Test archived status,
cross-household requests, expected versions, idempotent retries, correction controls, and audit
redaction.

### Task 6 — Add Spider molt and premolt contracts

**Files:** add typed payloads/handlers beside Animal contracts; extend effective-history and
timeline query/rendering code; add domain, replay, correction, and integration tests.

Test first molt, repeated molts, occurred-time ordering, correction, void/reinstatement only where
the registry supplies deterministic handlers, premolt observed/cleared state, invalid target/type,
same-stream and same-household rules, replay, unknown schema, and human-readable effective history.

### Task 7 — Add neutral enclosure watering/misting care

**Files:** extend enclosure contracts/application/projections and focused occupancy/enclosure tests.

Test configured misting for a Spider enclosure, optional related-animal validation, neutral
enclosure history, reassignment, current occupancy, correction/replay behavior, and rejection when
the active profile or owner configuration does not permit the action. Preserve cleaning and water
change semantics for all existing enclosures.

### Task 8 — Reuse feeding, inventory, expenses, reminders, and attachments

**Files:** extend existing application eligibility/view-model seams and integration tests; do not
fork these modules by animal type.

Test Spider feeding acceptance/refusal/prey, optional inventory consumption, compensation after
correction/void, expense subject authorization, photos/attachments, owner-defined feeding/weight/
molt/misting/cleaning schedules, effective source recalculation, independent pipeline dedupe,
worker recovery, and absence of hard-coded husbandry intervals.

### Task 9 — Build the mixed collection and focused profile UI

**Files:** update animal list/profile/new/care templates, view models/routes, CSS, and browser tests.

Test first-run Snake and Spider creation, one mixed household list, profile photos, type labels,
current enclosure, focused applicable actions, usable empty/error/conflict states, keeper-facing
timeline wording, optional technical disclosure, CSRF, capability denial, and no cross-household
leakage. Do not build M6 filters, search, charts, or dashboards.

### Task 10 — Qualify desktop, mobile, and accessibility behavior

**Files:** extend Playwright journeys and accessibility evidence procedures.

Run mixed-collection creation, feeding, molt/premolt, rehouse, misting, reminders, correction, logout/
login, and restored-data journeys at desktop and mobile widths. Verify keyboard order, focus/error
summary behavior, 44px targets, screen-reader names, landmarks, contrast, reduced motion, and axe
results. Retain screenshots that show both animal types and the absence of irrelevant controls.

### Task 11 — Prove replay, backup, recovery, and M6 read boundaries

**Files:** extend compatibility, backup/restore, projection, qualification, and read-contract tests.

Rehearse migration upgrade/downgrade guard/re-upgrade, legacy and mixed replay, unknown-contract
restricted recovery, projection rebuild, backup verification, restore to an isolated database, and
post-restore attachments/sessions. Contract-test the M6 inputs without implementing consumers:
type/profile, effective feeding, applicable measurements, snake shed, Spider molt, reminder facts,
enclosure care, and species/life-stage reference keys.

### Task 12 — Complete qualification, evidence, and review preparation

Run the full local quality gate, line/branch coverage thresholds, Ruff, strict mypy, dependency
audit, architecture boundaries/freeze, documentation links, migrations, M0-M5 compatibility,
attachment security, backup/restore, amd64 Compose lifecycle on port 8081, ARM64 image build,
browser/accessibility suites, and GitHub Quality/Container/Trivy/security review. Measure mixed
collection replay, common route latency, database growth, and container resources on the approved
laptop/Docker dataset; retain them as qualified development evidence, not Pi results.

## Evidence structure

Implementation will create `/docs/evidence/m5.5-multispecies-foundation/` with:

- `README.md`, `evidence-manifest.json`, and `checksums.sha256`;
- `tests/{capabilities,compatibility,snake,spider-care,mixed-collection,enclosures,reminders,inventory,m6-read-boundary}/`;
- `security/{authorization,capability-enforcement,attachments}/`;
- `browser/` and `accessibility/` with desktop/mobile procedures and screenshots;
- `operations/{migrations,backup-restore}/`, `containers/`, `performance/laptop-container/`,
  `reviews/`, and `approvals/`.

Every artifact records the source revision, pinned environment, exact command/procedure, outcome,
and reviewer. Owner acceptance is added only after manual review.

## Proposed commit sequence

1. `docs: establish M5.5 multi-species architecture`
2. `docs: add M5.5 implementation plan`
3. `test: lock M5.5 compatibility and scope`
4. `feat: add animal capability profiles`
5. `feat: add versioned multi-species registration`
6. `feat: project animal capability profiles`
7. `feat: enforce animal care capabilities`
8. `feat: add spider molt and premolt care`
9. `feat: add configurable enclosure misting care`
10. `feat: integrate spider shared workflows`
11. `feat: add mixed-species keeper experience`
12. `test: qualify M5.5 compatibility and recovery`
13. `docs: record M5.5 implementation evidence`

Keep tests beside each implementation commit when practical; the named test commits mark
cross-cutting compatibility gates rather than postponing tests.

## Risks and rollback points

- **Legacy misclassification:** stop if any v1 stream cannot resolve deterministically to snake;
  do not patch stored events. Roll back before v2 registration is enabled.
- **Projection/schema downgrade:** block downgrade when v2/Spider facts exist rather than silently
  dropping authoritative meaning. A destructive strategy requires a new ADR and owner approval.
- **Scattered species conditionals:** reject implementation that bypasses the registered capability
  policy; centralize policy without moving feature ownership.
- **Shared-workflow semantic mismatch:** add a typed capability extension only where Spider facts do
  not fit the existing contract; do not duplicate feeding/inventory/reminder engines.
- **M6 scope creep:** extension-contract tests may be added, but no search, chart, report,
  prediction, recommendation, reference dataset, or PWA implementation may land.

## Explicit exclusions

M5.5 excludes M6 search/FTS UI, reports, dashboards, charts, analytics, predictions, curated
species/life-stage recommendations, PWA expansion, and global product redesign. It also excludes
expert spider breeding/incubation, venom or medical guidance, arbitrary user-defined capabilities,
third-party plugins, high-frequency sensor telemetry, remote/public deployment, Raspberry Pi
qualification, new animal types beyond Snake and Spider, and any rewrite of M0-M5 events.
