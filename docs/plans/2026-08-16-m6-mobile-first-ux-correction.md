# M6 Mobile-First UX Correction and Runtime Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the approved Care Keeper mobile-first M6 correction and one safe, populated,
household-isolated owner-review instance at `http://localhost:8081` without altering real data.

**Architecture:** ADR-0040 adds one internal, environment-gated application use case for atomic
demo-household provisioning using the canonical household event contracts and existing operational
tables. All later demo content uses current application/domain interfaces. Presentation remains
server-rendered and strict-CSP compatible, with a single responsive information architecture and
capability-driven action registry.

**Tech Stack:** Python 3.13, FastAPI, synchronous SQLAlchemy/SQLite, Jinja, existing strict-CSP
assets, pytest, Playwright, Pa11y, Docker Compose, uv, Ruff, mypy.

---

## Scope and invariants

- Work only on `phase6/product-experience`; do not merge PR #8 or begin M7.
- Preserve the verified real database, attachment store, canonical events, and production setup
  behavior. No migration or event-contract rewrite is permitted.
- Use the already completed encrypted backup/isolated restore as the pre-change recovery point.
- Do not stop alternate review Compose projects until the promoted 8081 instance passes all
  data, migration, login, attachment, and authorization checks.
- Visible brand changes to Care Keeper; internal compatibility identifiers remain SnakeTracker.
- Demo password is accepted only as local fixture input and must not enter logs/evidence output.

### Task 1: Add the trusted local provisioner contract

**Files:**
- Modify: `src/snaketracker/application/household_bootstrap.py`
- Modify: `src/snaketracker/application/ports/__init__.py`
- Test: `tests/integration/test_household_bootstrap.py`
- Test: `tests/security/test_identity_security.py`

1. Write failing tests for the reserved deterministic identity, explicit allowed environment,
   hard failure in production/unknown environments, and absence of a FastAPI route.
2. Run `uv run pytest tests/integration/test_household_bootstrap.py tests/security/test_identity_security.py -q`
   and confirm the new tests fail for the missing use case.
3. Add typed provisioning command/result and application-owned port without changing the existing
   production `bootstrap` method.
4. Run the focused tests and confirm they pass.
5. Commit: `feat: define trusted local demo provisioning`.

### Task 2: Implement atomic canonical demo-household provisioning

**Files:**
- Modify: `src/snaketracker/infrastructure/identity/bootstrap_repository.py`
- Modify: `src/snaketracker/bootstrap/application.py`
- Create: `src/snaketracker/operations/demo_household.py`
- Test: `tests/integration/test_demo_household_provisioning.py`

1. Write failing database tests asserting one transaction contains the user, canonical
   `household.created` and `household.owner_added` events, authorization rows, completed
   idempotency result, and security audit row.
2. Add failure tests for partial-write rollback and conflicting reserved email, UUID, stream, and
   membership state; assert all pre-test row counts remain identical.
3. Add an idempotent-rerun test that returns the stored result and leaves stream/global versions
   unchanged.
4. Implement the minimum repository transaction using existing envelope/registry/checksum and
   password services. Expose only an internal CLI adapter guarded by the composition root.
5. Run `uv run pytest tests/integration/test_demo_household_provisioning.py -q`.
6. Commit: `feat: provision isolated local demo household`.

### Task 3: Refactor and expand the supported demo dataset

**Files:**
- Modify: `scripts/fixtures/seed_m6_owner_review.py`
- Modify: `scripts/development/m6_owner_review_demo.sh`
- Modify: `tests/integration/test_m6_owner_review_demo.py`
- Create: `tests/fixtures/m6_demo_dataset.py`

1. Write failing tests for a deterministic 10-15 animal, 8-10 enclosure mixed collection with
   several hundred coherent events, distinct safe photos, inventory, expenses, reminders, due
   states, and sufficient/insufficient analytics histories.
2. Assert the fixture targets an existing ADR-0040 household in the supplied database and invokes
   supported HTTP/application/domain flows rather than writing product rows directly.
3. Assert reruns are idempotent and conflicts fail without a demo-only delete-all path.
4. Refactor the old standalone 18087 seeder into a shared-database population command; remove
   alternate-stack startup behavior from its development wrapper.
5. Run `uv run pytest tests/integration/test_m6_owner_review_demo.py -q`.
6. Commit: `test: expand deterministic M6 owner review household`.

### Task 4: Prove bidirectional tenant isolation

**Files:**
- Create: `tests/security/test_demo_household_isolation.py`
- Modify: `tests/integration/test_m6_owner_review_demo.py`
- Modify: `tests/integration/test_search.py`
- Modify: `tests/integration/test_reports.py`

1. Write real-to-demo and demo-to-real denial tests for animal/enclosure/inventory/expense/reminder
   lists, direct identifier and URL access, mutations, attachment delivery, search, and reports.
2. Assert denied writes add security-audit evidence and never change target stream versions.
3. Repair only missing household filters or authorization checks; retain current protected-request
   behavior.
4. Run the new security suite plus existing cross-household tests.
5. Commit: `test: prove demo household isolation`.

### Task 5: Establish Care Keeper branding and responsive global navigation

**Files:**
- Modify: `src/snaketracker/presentation/templates/base.html`
- Create: `src/snaketracker/presentation/templates/more.html`
- Modify: `src/snaketracker/presentation/static/app.css`
- Modify: `src/snaketracker/presentation/static/manifest.webmanifest`
- Modify: `src/snaketracker/presentation/static/offline.html`
- Modify: `src/snaketracker/presentation/static/favicon.svg`
- Modify: `src/snaketracker/presentation/web.py`
- Test: `tests/integration/test_web_presentation.py`
- Test: `tests/browser/test_product_experience.py`

1. Write failing HTML/browser tests for Care Keeper visible branding, mobile bottom navigation,
   desktop equivalent navigation, active state, More destinations, safe-area padding, 44px touch
   targets, and no horizontal overflow at 390 x 844.
2. Implement server-derived navigation with Today, Animals, Enclosures, Inventory, and More; keep
   search compact and all scripts/styles external for CSP.
3. Replace keeper-visible SnakeTracker text while preserving internal identifiers.
4. Run focused integration/browser tests at mobile and desktop viewports.
5. Commit: `feat: add Care Keeper responsive navigation`.

### Task 6: Separate Today from the animal collection

**Files:**
- Modify: `src/snaketracker/application/dashboard.py`
- Modify: `src/snaketracker/presentation/web.py`
- Modify: `src/snaketracker/presentation/templates/home.html`
- Create: `src/snaketracker/presentation/templates/animal_list.html`
- Modify: `src/snaketracker/presentation/static/app.css`
- Test: `tests/integration/test_web_presentation.py`
- Test: `tests/browser/test_product_experience.py`

1. Write failing tests proving `/home` is a compact Today agenda and `/animals` is a dedicated
   photo/type/enclosure collection rather than an alias.
2. Add empty-household onboarding and dense populated-household states.
3. Implement compact Overdue, Due today, and Upcoming groups with plain language and without the
   internal phrase `Owner due-date override`; render `Custom due date` when applicable.
4. Run focused tests and commit: `feat: separate Today and animal collection`.

### Task 7: Add safe direct agenda actions and return context

**Files:**
- Modify: `src/snaketracker/presentation/animal_care_views.py`
- Modify: `src/snaketracker/presentation/web.py`
- Modify: `src/snaketracker/presentation/templates/home.html`
- Modify: `src/snaketracker/presentation/templates/animal_care_form.html`
- Test: `tests/integration/test_animal_care.py`
- Test: `tests/security/test_identity_security.py`
- Test: `tests/browser/test_product_experience.py`

1. Write failing tests for capability-registered agenda action URLs, correct animal/enclosure
   identity, safe Today/animal return contexts, and rejection of arbitrary external redirects.
2. Implement allow-listed route mappings and signed/validated local return tokens or named
   contexts; recheck capability and household authorization on GET and POST.
3. Prove a completed action returns to its origin and refreshes the agenda.
4. Commit: `feat: add direct Today care actions`.

### Task 8: Reorder animal profiles and simplify care forms

**Files:**
- Modify: `src/snaketracker/presentation/templates/animal_profile.html`
- Modify: `src/snaketracker/presentation/templates/animal_care_form.html`
- Modify: `src/snaketracker/presentation/static/app.css`
- Modify: `src/snaketracker/presentation/animal_care_views.py`
- Test: `tests/integration/test_animal_profiles.py`
- Test: `tests/browser/test_animal_care_workflow.py`
- Test: `tests/browser/test_multispecies_workflow.py`

1. Write failing snake/spider tests for identity/enclosure, large applicable actions, recent care,
   history/trends, schedule, then admin order; assert irrelevant capability actions remain absent.
2. Write form tests for common-first fields, accessible advanced disclosure, retained values and
   inline errors, correct labels/input modes, and mobile overflow/touch targets.
3. Implement template/view-definition changes without species conditionals or new domain behavior.
4. Commit: `feat: streamline mobile animal care workflows`.

### Task 9: Make analytics, search, and reports keeper-readable

**Files:**
- Modify: `src/snaketracker/presentation/templates/animal_analytics.html`
- Modify: `src/snaketracker/presentation/templates/search.html`
- Modify: `src/snaketracker/presentation/templates/reports.html`
- Modify: `src/snaketracker/presentation/static/app.css`
- Test: `tests/integration/test_measurement_analytics.py`
- Test: `tests/browser/test_product_experience.py`

1. Add tests for plain-language estimate summaries, sample-progress guidance, passed windows,
   capability-aware terminology, and accessible `Why?` provenance disclosure.
2. Add mobile result/report readability and empty-state tests without changing analytics as
   non-authoritative read state.
3. Implement presentation-only improvements and preserve exact deterministic provenance.
4. Commit: `feat: clarify M6 insights and discovery`.

### Task 10: Promote and consolidate the single 8081 runtime

**Files:**
- Modify: `scripts/development/m6_owner_review_demo.sh`
- Create: `docs/evidence/m6-product-experience/owner-review/consolidated-demo/README.md`
- Create: `docs/evidence/m6-product-experience/owner-review/consolidated-demo/runtime-inventory.txt`
- Create: `docs/evidence/m6-product-experience/owner-review/consolidated-demo/data-verification.md`

1. Rebuild the promoted 8081 stack from the branch head without replacing its database/attachment
   mounts; run migration and SQLite integrity checks.
2. Capture real-household counts, attachment checksums, and both login paths before provisioning.
3. Run the ADR-0040 provisioner and supported dataset population against the promoted database.
4. Verify real counts/history remain unchanged, demo counts meet targets, both users authenticate,
   and bidirectional isolation/attachments/search/reports pass.
5. Only then stop and remove the six alternate SnakeTracker/Care Keeper Compose projects, leaving
   unrelated projects untouched. Confirm only port 8081 listens for this application.
6. Commit: `ops: consolidate M6 owner review runtime`.

### Task 11: Qualify real-browser mobile and desktop workflows

**Files:**
- Modify: `tests/browser/test_product_experience.py`
- Modify: `tests/browser/test_animal_care_workflow.py`
- Modify: `tests/browser/test_multispecies_workflow.py`
- Create: `docs/evidence/m6-product-experience/browser/mobile-first/README.md`
- Create: `docs/evidence/m6-product-experience/accessibility/critical-journeys/mobile-first.md`

1. Run a real browser through demo login, Today direct actions, animal collection/profile, snake
   and spider care, enclosures, inventory, reminders, analytics, search, reports, logout/login, and
   an empty-household fixture at 390 x 844 and desktop.
2. Assert no horizontal overflow, console/page errors, CSP violations, inaccessible names, or
   keyboard traps; run Pa11y/axe-compatible project scans for WCAG 2.2 AA.
3. Capture screenshots and documented commands without credentials or sensitive real data.
4. Commit: `test: qualify mobile-first M6 owner journeys`.

### Task 12: Run final M6 correction qualification and update evidence

**Files:**
- Modify: `docs/evidence/m6-product-experience/README.md`
- Modify: `docs/evidence/m6-product-experience/reviews/README.md`
- Modify: `docs/evidence/m6-product-experience/owner-review/README.md`
- Modify: `docs/roadmap/milestones.md`

1. Run `./scripts/quality/check.sh`, full pytest/coverage, Ruff, strict mypy, dependency audit,
   architecture/freeze/docs checks, migration upgrade/downgrade/re-upgrade, replay/compatibility,
   backup/isolated restore, attachment security, amd64 Compose lifecycle, ARM64 OCI build, browser,
   accessibility, container/Trivy, GitGuardian, and hosted PR checks.
2. Record exact revision, environment, commands, results, warnings, single runtime inventory, real
   preservation evidence, demo metrics, and isolation matrix.
3. Check only the two new M6 correction criteria after their evidence passes. Keep M6 owner
   acceptance pending and M7/M8 unchecked.
4. Push `phase6/product-experience`, update draft PR #8, and leave the populated 8081 instance
   running for owner inspection.
5. Commit: `docs: qualify M6 mobile owner review correction`.

## Rollback points

- Before Task 2: revert application code; no schema/data change exists.
- Before Task 10 provisioning: retain the verified encrypted backup run
  `3446bec0-a159-4f16-a9df-3ff1d19e20ad` and the unchanged promoted mounts.
- If provisioning or isolation fails: stop writes, keep alternate stacks running, preserve all
  databases, and restore only to an isolated rehearsal path until the fault is understood.
- If promoted-runtime proof fails: do not stop any alternate project and do not replace the real
  database.
- If an ADR/event/schema conflict appears: stop that task and present consequences before changing
  architecture.
