# X4 Amphibian Expansion Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for coordinated implementation and superpowers:dispatching-parallel-agents for independent work. Track the checks below and run a fresh whole-branch review before the owner handoff.

**Goal:** Add usable Frog tracking through the trusted amphibian.v1 profile while preserving every historical Animal and shared workflow.

**Architecture:** Extend the existing Animal aggregate, capability registry, event contracts and shared presentation. Biological identity remains in the X2 local catalog; qualified Amphibia mapping permits the initial conservative profile without specialized life-stage workflows. Use conventional startup and existing SQLite services only.

**Tech Stack:** Existing Python/FastAPI, SQLAlchemy/SQLite, Jinja/CSS and project quality tooling.

**Spec:** [Owner directive](../../evidence/m6.6-species-aware-husbandry/x4-amphibian/owner-directive.md), [controlling October 1 plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md), ADR-0039 and ADR-0045.

## Global constraints

- Start at main 4d7d769b804cd2aebafa6d4fc901f5ca4e247c84 in the isolated phase6.6/x4-amphibian-expansion branch.
- amphibian.v1 capabilities: feeding, weight, length, enclosure_assignment, photos, notes, inventory, expenses, reminders, timeline.
- Care actions: feeding, weight, length. Reminder kinds: feeding, weight, length, cleaning, water_change. Analytics: feeding, weight, length.
- Exclude shed, molt/premolt, bath/soak and misting. No inferred diets, schedules, growth targets or husbandry requirements.
- Retain v1/v2 registrations and v1 taxon links unchanged; add registration v3 with capability_profile and taxon-link v2 with expanded qualified group validation.
- Preserve completed retries, historical registry semantics, household ownership, immutable events/attachments and source rights.
- No production DB/service/deployment/import/publication operations, new infrastructure, protected-document changes or X5. Stop with a qualified PR and screenshots.

## Review focus

- Completed registration retry after profile/default eligibility changes must return the original result without rewriting events or command hashes (task 1).
- Reference-only Amphibia and unqualified/conflicting provider ancestry must not acquire registration capabilities by common-name guessing (task 2).
- Excluded care/reminder routes must reject direct POSTs as well as hiding controls, including mixed-household access (task 3).
- The actual prior release must reject v3 before mutable startup; a mocked scanner or current module reimplementation is insufficient (task 4).
- Unknown future profile fallbacks must be honest and consistent across list/profile/admin; personal photo priority and tiny-screen navigation must remain intact (task 3).

## Task 1: Trusted profile and immutable event evolution

Files: domains/animals/contracts.py, capabilities.py; platform/events/registry.py;
application/animals.py; infrastructure/animals/projections.py; bootstrap/compatibility.py and
release manifest; corresponding domain/registry/capability/registration tests.

Interface: AnimalRegisteredV3 retains common v2 registration facts, replacing animal_type and
capability_profile_version with capability_profile: str. AnimalTaxonLinkedV2 retains the v1
payload shape with a separately versioned expanded group validator. capability_profile_for_registration
supports all three versions; existing profile storage still uses type/version columns.

- [ ] Write and run failing exact-matrix, contract-roundtrip, old-decoder exclusion and registry enforcement tests.
- [ ] Add amphibian.v1, eligibility/default and event-version-aware write metadata; preserve the four historical profile definitions.
- [ ] Implement v3 creation/decoding/projection/preflight and v2 taxon-link identity extraction; never expand historical decoders silently.
- [ ] Verify registration retry/conflict behavior, immutable historical payloads and reconstruction; record results.

## Task 2: Qualified biological identity and manual entry

Files: application/species_directory.py; infrastructure/taxonomy/catalog.py, inaturalist.py,
repository.py; targeted local-catalog and directory integration tests.

Interface: SUPPORTED_GROUPS includes amphibian; qualified provider Amphibia ancestry maps to the
amphibian workflow group independently of profile registration. Existing unqualified/reference-only
taxa remain reference-only; ordinary manual registration is available without providers.

- [ ] Add failing provider-ID/ancestry, mismatched-group, reference-only and provider-outage tests.
- [ ] Extend trusted taxonomy mapping and v2 link writing without Frog-name lists or automatic enrichment.
- [ ] Verify local search/linking, historical v1 links, generation promotion/rollback and existing taxon UUID preservation.

## Task 3: Integrated Frog experience and distinct visuals

Files: presentation/animal_visuals.py, trusted presentation definitions, templates/static assets,
web.py as needed; new focused mixed-workflow and visual tests.

- [ ] Add failing tests for distinct Amphibian fallback and honest unknown-profile fallback across consumers.
- [ ] Add an original Amphibian illustration; retain dark photo-first layout, photo credits and personal-photo priority.
- [ ] Expose Amphibian Add Animal and directory selection through the trusted registry; reuse existing fields and shared controls.
- [ ] Exercise registration, photo, enclosure changes, Inventory feeding/outcomes, weight/length, correction/void, notes, expenses, reminders/Calendar, Today/Quick Log, search/history/reports/trends across five groups and two households.
- [ ] Reject excluded actions and unsupported reminders at command boundaries; preserve enclosure ownership for cleaning/water changes.

## Task 4: Compatibility and disposable-data qualification

Files: new tests/integration/test_x4_compatibility.py and test_x4_workflows.py, supporting test fixtures only.

- [ ] Build disposable populated fixtures retaining v1/v2 registrations and v1 links, source references, media and all five supported groups.
- [ ] Start the actual source from pre-X4 release 4d7d769 in a subprocess against a disposable copied DB containing new v3 facts; assert restricted recovery and no normal mutable startup or business-data changes.
- [ ] Qualify backup/restore, replay/rebuild, unchanged event hashes and profile semantics; never delete new events to make downgrade start.
- [ ] Run AT-AMPH-01, applicable AT-PRODCOMP-01 and X1 capability regressions with retained logs.

## Task 5: Browser evidence and owner PR

- [ ] Run focused checks, then the unchanged local quality gate and fresh hosted Quality/Container/security checks.
- [ ] Capture real browser screenshots at 390px, 320px and 1440px for Add Animal, Frog profile, feeding/measurement history, care/reminders, linked reference and mixed Animals list.
- [ ] Verify no overflow/broken imagery, keyboard/touch/reduced-motion behavior and no misleading care guidance.
- [ ] Add acceptance/evidence ledger and a development-only draft What's New entry; keep the production release ledger unchanged.
- [ ] Review the entire diff independently, address substantive findings, commit/push normally and open the focused X4 PR. Return exact head, results, screenshots and limits. Do not merge.

## Execution rulings

The owner explicitly directs implementation using an approved matrix, roadmap and existing design;
this ledger decomposes that authorized work and does not reopen architecture/design approval.
Independent tasks may run concurrently with separate file ownership; integration and final checks
remain coordinated. No database migration is planned unless inspection proves an additive schema
change is necessary. Existing main passed 1,513 tests; do not repeat that full baseline gate before
new focused regressions. All test databases, old-binary runs and browser fixtures are disposable.
