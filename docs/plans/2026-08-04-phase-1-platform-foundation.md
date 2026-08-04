# Phase 1 Platform Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish a reproducible, secure, ARM64-capable Python and container foundation that satisfies M1 without implementing Phase 2+ product functionality.

**Architecture:** Build the thinnest executable shell of the accepted modular monolith: a composition root, typed configuration, SQLite operational adapter, migration/compatibility framework, structured observability, health probes, and inert worker lifecycle. Keep all business domains, event storage, identity, household, UI, and public remote access absent. Local scripts are the authoritative quality interface; CI invokes the same scripts.

**Tech Stack:** Python 3.13, uv, FastAPI, Uvicorn, SQLAlchemy 2.x using the synchronous SQLite driver, Alembic, Pydantic v2/pydantic-settings, standard-library JSON logging, Prometheus client, pytest, Ruff, mypy, pip-audit, Docker/BuildKit, Docker Compose, Nginx, GitHub Actions, SQLite with FTS5.

---

## Plan status and authority

Approved for Phase 1 implementation on 2026-08-04. The immutable architecture baseline is Git commit `bb3ab39` (`docs: approve SnakeTracker architecture baseline`). ADR-0028 is active.

Proposed implementation branch: `phase1/platform-foundation`, created from `bb3ab39` after plan approval.

## Phase 1 scope

### Deliverables

1. Reproducible Python 3.13 project and exact dependency lock.
2. Importable package with bootstrap composition root and separate web/worker entry points.
3. Typed environment configuration and Docker-secret file indirection.
4. Read-only startup compatibility checks and restricted recovery-mode foundation.
5. SQLite engine factory, local-filesystem guard, approved pragma profile, and maintenance interfaces.
6. Alembic framework with an empty/base migration proving upgrade and downgrade mechanics.
7. Structured redacted logging, correlation IDs, metrics foundation, liveness, and readiness.
8. ARM64-compatible production container and local-only Docker Compose topology for web, worker, and Nginx.
9. Unified local quality script and GitHub Actions quality/build gates.
10. Versioned qualification manifest, deterministic foundation dataset seed contract, and M1 evidence procedures.

### Explicit non-goals

- Identity, passwords, sessions, CSRF, household bootstrap, roles, or authorization
- Animal, enclosure, husbandry, health, inventory, expense, reminder, or document functionality
- Domain event store, event contracts, snapshots, projections, outbox, durable jobs, or notifications
- Jinja pages, HTMX flows, PWA assets, public API v1 resources, or product UI
- Cloudflare Tunnel enablement or remote/public deployment
- Plugins, backup implementation, attachment handling, FTS data indexing, PostgreSQL, or sensor telemetry

Health endpoints and the inert worker process are platform probes, not Phase 2+ features.

## Proposed tool and dependency decisions

### Python and packaging

- Require Python `>=3.13,<3.14` for Phase 1.
- Pin one exact 3.13 patch release in `.python-version`, Docker image digest, and qualification manifest at execution time.
- Use `uv` for environment creation, dependency resolution, locking, and command execution.
- Commit `uv.lock`; CI and containers use `uv sync --frozen`.
- Keep direct dependency constraints in `pyproject.toml`; the lockfile is the exact transitive resolution.
- Use a `src/` layout and one package named `snaketracker`.
- Do not introduce a DI framework; compose concrete adapters manually in `bootstrap/application.py`.

### Runtime dependencies

- `fastapi`: web application and health routing
- `uvicorn[standard]`: ASGI server; one worker in the initial Compose profile
- `sqlalchemy`: synchronous engine/unit-of-work foundation
- `alembic`: relational migrations only
- `pydantic` and `pydantic-settings`: typed boundary/configuration validation
- `prometheus-client`: lightweight internal metrics exposition

Do not add Jinja, password, email, task-queue, plugin, or event-sourcing dependencies during Phase 1.

### Development dependencies

- `pytest`, `pytest-cov`, `pytest-timeout`: tests and coverage
- `httpx`: ASGI health-route tests
- `ruff`: formatting and linting
- `mypy`: strict static analysis
- `pip-audit`: Python dependency vulnerability reporting

All tools are invoked through `uv run` except Docker-native scanners. New dependencies require justification against Pi memory, ARM64 availability, maintenance health, and the approved architecture.

### CI provider

Use GitHub Actions as the proposed initial CI adapter. Local scripts remain authoritative so CI can migrate without changing acceptance logic. Actions must be pinned to immutable commit SHAs during implementation. ARM64 is validated through Buildx image construction in CI and native execution on the Pi qualification host.

## Proposed file-change inventory

```text
SnakeTracker/
├── .dockerignore
├── .env.example
├── .github/
│   └── workflows/
│       ├── quality.yml
│       └── container.yml
├── .python-version
├── Dockerfile
├── Makefile
├── alembic.ini
├── compose.yaml
├── pyproject.toml
├── uv.lock
├── deploy/
│   ├── docker/
│   │   └── entrypoint.sh
│   └── nginx/
│       └── nginx.conf
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_phase1_baseline.py
├── scripts/
│   ├── benchmarks/
│   │   ├── run_phase1_qualification.sh
│   │   └── verify_storage.sh
│   ├── development/
│   │   └── bootstrap.sh
│   ├── maintenance/
│   │   ├── check_database.sh
│   │   └── checkpoint_wal.sh
│   └── quality/
│       ├── check.sh
│       └── verify_architecture.py
├── src/snaketracker/
│   ├── __init__.py
│   ├── bootstrap/
│   │   ├── __init__.py
│   │   ├── application.py
│   │   ├── compatibility.py
│   │   └── configuration.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── maintenance.py
│   │   │   └── sqlite_profile.py
│   │   └── observability/
│   │       ├── __init__.py
│   │       ├── correlation.py
│   │       ├── logging.py
│   │       └── metrics.py
│   ├── presentation/
│   │   ├── __init__.py
│   │   └── health.py
│   └── worker/
│       ├── __init__.py
│       └── main.py
├── tests/
│   ├── conftest.py
│   ├── architecture/
│   │   ├── test_dependency_boundaries.py
│   │   └── test_phase_scope.py
│   ├── integration/
│   │   ├── test_alembic_lifecycle.py
│   │   ├── test_application_startup.py
│   │   ├── test_container_contract.py
│   │   ├── test_health_endpoints.py
│   │   └── test_sqlite_profile.py
│   └── unit/
│       ├── bootstrap/
│       │   ├── test_compatibility.py
│       │   └── test_configuration.py
│       └── infrastructure/
│           ├── test_correlation.py
│           ├── test_logging.py
│           └── test_sqlite_profile.py
└── docs/
    ├── evidence/m1-platform/
    │   ├── README.md
    │   ├── environment/.gitkeep
    │   ├── operations/.gitkeep
    │   ├── performance/.gitkeep
    │   └── tests/.gitkeep
    └── operations/
        ├── development-environment.md
        └── phase1-qualification.md
```

Generated evidence files are not fabricated during implementation. Commands create them from real runs or operators add manifests from the Pi host.

## Phase 1 requirements-to-tests mapping

| Requirement | Accepted ADRs | Threat controls | Planned verification | Evidence | Exit criterion |
|---|---|---|---|---|---|
| R-001 modular monolith/composition root | 0001, 0004 | TM-14 | `test_dependency_boundaries.py`; import smoke test | `m1-platform/tests/dependency-boundaries.*` | Package boundaries and composition root are enforceable |
| R-009 SQLite with PostgreSQL boundary | 0009 | TM-18 | engine-port contract and dialect-isolation tests | `m1-platform/tests/database-boundary.*` | Storage is isolated behind application-owned interfaces |
| R-010 SQLite profile/local SSD | 0010 | TM-09, TM-18 | pragma integration test; filesystem qualification procedure | `m1-platform/operations/sqlite-profile.*` | Approved profile and SSD guard pass |
| R-023 observability/health foundation | 0023 | TM-17, TM-18 | log-redaction, correlation, metric, liveness/readiness tests | `m1-platform/tests/observability.*` | Health and diagnostics are safe and useful |
| R-025 reproducible Pi qualification | 0024 | TM-18 | pinned manifest and repeatable qualification script | `m1-platform/performance/phase1-*` | Startup/idle targets measured on reference host |
| R-026 API foundation only | 0025 | TM-17 | health error/content contract test | `m1-platform/tests/health-contract.*` | Platform endpoints have stable safe responses |
| R-027 migration/rollback foundation | 0026 | TM-09, TM-20 | clean upgrade, downgrade, re-upgrade tests | `m1-platform/tests/alembic-lifecycle.*` | Migration framework is reversible at baseline |
| R-029 decision freeze compliance | 0028 | TM-20 | architecture-diff and ADR-reference gate | `m1-platform/tests/architecture-freeze.*` | No silent architectural change |
| R-034 compatibility matrix/startup | 0033 | TM-20 | supported, older, newer, malformed compatibility tests | `m1-platform/tests/compatibility.*` | Unsupported newer state fails into recovery mode |
| R-039 reproducible evidence | 0028 | TM-20 | evidence schema/path checker | `m1-platform/evidence-manifest.*` | Every M1 claim has reproduction metadata |

## Phase 1 exit criteria

1. A clean supported environment reproduces the locked toolchain.
2. Images build for linux/amd64 and linux/arm64; native Pi smoke evidence is retained.
3. SQLite runs only on a qualified local SSD path and reports the approved pragma profile.
4. Startup refuses unsupported schema/runtime combinations and exposes restricted recovery readiness.
5. CI and the local quality script enforce formatting, linting, strict types, tests, coverage threshold, dependency audit, architecture scope, documentation links, and container checks.
6. The Compose topology starts web, worker, and Nginx locally with non-root/read-only/resource/health controls.
7. Startup and idle resource targets are measured against the pinned Phase 1 qualification environment.
8. M1 evidence contains exact commands, revision, environment, outputs, result, and reviewer fields.

## Test-driven implementation tasks

### Task 1: Establish the Python project and authoritative quality interface

**Files:**

- Create: `pyproject.toml`, `.python-version`, `uv.lock`, `Makefile`
- Create: `src/snaketracker/__init__.py`
- Create: `scripts/development/bootstrap.sh`, `scripts/quality/check.sh`
- Create: `tests/architecture/test_phase_scope.py`
- Modify: `.gitignore` only if generated tools reveal a missing safe artifact pattern

**Traceability:** R-001, R-025, R-039; ADR-0001, ADR-0024, ADR-0028; TM-14, TM-18, TM-20.

**Steps:**

1. On `phase1/platform-foundation`, write `test_phase_scope.py` to forbid Phase 2+ package paths and dependencies.
2. Run `uv run pytest tests/architecture/test_phase_scope.py -v`; expect failure because project metadata/package paths do not exist.
3. Add the minimal `src` package, Python range, dependency groups, Ruff, mypy, pytest, coverage, and build metadata.
4. Resolve and commit an exact `uv.lock`; record the selected Python 3.13 patch.
5. Add one authoritative `scripts/quality/check.sh`; Make targets delegate to it rather than duplicating logic.
6. Run `uv sync --frozen`, format/lint, mypy, and the scope test; expect success.
7. Capture tool versions and commands in `docs/evidence/m1-platform/environment/` only from the real run.
8. Commit: `chore: establish Python project toolchain`.

**Rollback point:** Revert this commit; no persistent schema or runtime data exists.

### Task 2: Enforce architecture dependency boundaries

**Files:**

- Create: `src/snaketracker/bootstrap/__init__.py`
- Create: `src/snaketracker/infrastructure/__init__.py`
- Create: `src/snaketracker/presentation/__init__.py`
- Create: `src/snaketracker/worker/__init__.py`
- Create: `tests/architecture/test_dependency_boundaries.py`
- Create: `scripts/quality/verify_architecture.py`

**Traceability:** R-001, R-003 boundary precursor, R-029; ADR-0001, ADR-0004, ADR-0028; TM-14, TM-20.

**Steps:**

1. Write failing architecture tests that define allowed import directions and prohibit product-domain packages during Phase 1.
2. Run the targeted tests and retain the expected initial failure in development output, not milestone acceptance evidence.
3. Implement the smallest static import scanner needed for the documented rules.
4. Add the scanner to `scripts/quality/check.sh`.
5. Run targeted tests and the full quality script; expect success.
6. Commit: `test: enforce architecture and phase boundaries`.

**Rollback point:** Revert without affecting runtime behavior.

### Task 3: Add typed configuration and secret indirection

**Files:**

- Create: `.env.example`
- Create: `src/snaketracker/bootstrap/configuration.py`
- Create: `tests/unit/bootstrap/test_configuration.py`
- Create: `docs/operations/development-environment.md`

**Traceability:** R-001, R-024 foundation; ADR-0001, ADR-0016, ADR-0023; TM-12, TM-17.

**Steps:**

1. Write tests for environment precedence, required production values, redacted representations, `_FILE` secret indirection, unreadable secret files, and prohibition on ambiguous simultaneous direct/file values.
2. Run the targeted test; expect failure because configuration does not exist.
3. Implement immutable typed settings with separate development/test/production validation.
4. Ensure `.env.example` contains placeholders only and no secret-looking defaults.
5. Document local and container configuration, secret mounting, and failure behavior.
6. Run configuration tests, secret-pattern scan, and full quality gate.
7. Commit: `feat: add typed runtime configuration`.

**Rollback point:** No stored data; revert configuration and documentation together.

### Task 4: Add startup compatibility and restricted recovery-mode foundation

**Files:**

- Create: `src/snaketracker/bootstrap/compatibility.py`
- Create: `tests/unit/bootstrap/test_compatibility.py`
- Create/modify: `src/snaketracker/bootstrap/application.py`

**Traceability:** R-027, R-034; ADR-0026, ADR-0033; TM-20.

**Steps:**

1. Write table-driven tests for supported, older-readable, newer-unknown, malformed, and missing compatibility metadata.
2. Assert incompatible newer state prevents normal readiness and yields a non-sensitive recovery reason.
3. Run tests; expect failure.
4. Implement a read-only compatibility manifest evaluator independent of domain/event code.
5. Compose it in the startup layer without adding business routes.
6. Run tests and record the compatibility matrix fixture version.
7. Commit: `feat: add safe startup compatibility checks`.

**Rollback point:** Revert before relational migrations depend on the compatibility format.

### Task 5: Qualify and configure SQLite

**Files:**

- Create: `src/snaketracker/infrastructure/database/__init__.py`
- Create: `src/snaketracker/infrastructure/database/engine.py`
- Create: `src/snaketracker/infrastructure/database/sqlite_profile.py`
- Create: `src/snaketracker/infrastructure/database/maintenance.py`
- Create: `tests/unit/infrastructure/test_sqlite_profile.py`
- Create: `tests/integration/test_sqlite_profile.py`
- Create: `scripts/benchmarks/verify_storage.sh`
- Create: `scripts/maintenance/check_database.sh`, `scripts/maintenance/checkpoint_wal.sh`

**Traceability:** R-009, R-010, R-025; ADR-0009, ADR-0010, ADR-0024; TM-09, TM-18.

**Steps:**

1. Write failing unit tests for the approved profile and integration tests against a temporary real SQLite database.
2. Test `foreign_keys=ON`, WAL, `synchronous=FULL`, bounded busy timeout, controlled auto-checkpoint, journal size limit, FTS5 availability, UTC behavior, and incremental-vacuum database creation.
3. Add negative filesystem qualification tests for unsupported or indeterminate storage; production fails closed while development can use an explicit documented test override.
4. Implement the synchronous SQLAlchemy engine factory and connection initialization with no global engine created at import time.
5. Implement bounded maintenance entry points for quick/integrity checks and WAL checkpoints; do not add scheduling or durable jobs.
6. Benchmark candidate `busy_timeout`, `wal_autocheckpoint`, and journal limit values on the Pi before finalizing the release manifest. Proposed starting values are 5,000 ms, 1,000 pages, and 256 MiB.
7. Run unit/integration tests and capture actual pragma/compile-option output.
8. Commit: `feat: establish SQLite operational profile`.

**Rollback point:** Use disposable test databases only; no user database exists in Phase 1.

### Task 6: Establish reversible Alembic migrations

**Files:**

- Create: `alembic.ini`
- Create: `migrations/env.py`, `migrations/script.py.mako`
- Create: `migrations/versions/0001_phase1_baseline.py`
- Create: `tests/integration/test_alembic_lifecycle.py`

**Traceability:** R-027, R-034; ADR-0026, ADR-0033; TM-09, TM-20.

**Steps:**

1. Write a failing isolated-database test for upgrade from empty, current-head detection, downgrade to base, and re-upgrade.
2. Assert migration execution uses application configuration and SQLite profile rather than hard-coded URLs.
3. Add Alembic configuration and a Phase 1 baseline revision containing only compatibility/operational foundation that is genuinely required; do not create domain, event, identity, or job tables.
4. Confirm upcaster paths do not exist under `migrations/`.
5. Run lifecycle and startup compatibility tests.
6. Record migration graph output as evidence.
7. Commit: `chore: establish reversible migration framework`.

**Rollback point:** Downgrade the disposable Phase 1 database to base, then revert the commit.

### Task 7: Add structured observability and health contracts

**Files:**

- Create: `src/snaketracker/infrastructure/observability/__init__.py`
- Create: `src/snaketracker/infrastructure/observability/correlation.py`
- Create: `src/snaketracker/infrastructure/observability/logging.py`
- Create: `src/snaketracker/infrastructure/observability/metrics.py`
- Create: `src/snaketracker/presentation/health.py`
- Modify: `src/snaketracker/bootstrap/application.py`
- Create: `tests/unit/infrastructure/test_correlation.py`
- Create: `tests/unit/infrastructure/test_logging.py`
- Create: `tests/integration/test_health_endpoints.py`

**Traceability:** R-024, R-026 foundation, R-034; ADR-0023, ADR-0025, ADR-0032, ADR-0033; TM-17, TM-18, TM-20.

**Steps:**

1. Write tests for correlation-ID validation/generation, JSON log shape, secret-field redaction, exception safety, and absence of request bodies.
2. Write health tests proving liveness is narrow, readiness checks configuration/database/migration compatibility, and incompatible state reports unavailable without sensitive details.
3. Write metrics tests for bounded labels; prohibit household, user, animal, path-parameter, and raw exception labels.
4. Run targeted tests; expect failure.
5. Implement standard-library JSON logging, middleware correlation context, minimal Prometheus metrics, and health routes.
6. Keep detailed diagnostics internal and unauthenticated administrative diagnostics absent until Phase 2 authorization exists.
7. Run security-focused tests, ASGI integration tests, and full quality gate.
8. Commit: `feat: add safe observability and health probes`.

**Rollback point:** Revert as one vertical slice; database compatibility remains usable from CLI tests.

### Task 8: Add the inert worker lifecycle

**Files:**

- Create: `src/snaketracker/worker/main.py`
- Create: `tests/integration/test_application_startup.py`
- Modify: `src/snaketracker/bootstrap/application.py`

**Traceability:** R-001, R-024; ADR-0001, ADR-0013 boundary only, ADR-0023; TM-18.

**Steps:**

1. Write subprocess/lifecycle tests for clean startup, readiness failure, SIGTERM, bounded shutdown, and no job execution capability.
2. Run tests; expect failure.
3. Implement separate web and worker entry points sharing configuration and observability composition.
4. The worker performs compatibility/health lifecycle only; it must not poll jobs or send external effects.
5. Run lifecycle tests and scan dependencies/packages for prohibited Phase 2+ components.
6. Commit: `feat: add Phase 1 worker lifecycle shell`.

**Rollback point:** Remove worker entry point; no durable work exists.

### Task 9: Add ARM64 Docker Compose and Nginx foundation

**Files:**

- Create: `.dockerignore`, `Dockerfile`, `compose.yaml`
- Create: `deploy/docker/entrypoint.sh`
- Create: `deploy/nginx/nginx.conf`
- Create: `tests/integration/test_container_contract.py`

**Traceability:** R-001, R-024, R-025; ADR-0001, ADR-0023, ADR-0024, ADR-0029 boundary; TM-14, TM-17, TM-18.

**Steps:**

1. Write static container-contract tests for non-root users, read-only root filesystems, explicit writable mounts, health checks, resource limits, one web worker, pinned bases, no embedded secrets, and loopback-only Nginx publication.
2. Assert no cloudflared service or remote/public binding exists in Phase 1.
3. Run contract tests; expect failure.
4. Add a multi-stage, multi-architecture image using frozen dependencies and exec-form entry points.
5. Add Compose services `web`, `worker`, and `nginx`; use local SSD volume configuration and test-safe defaults.
6. Configure Nginx health proxying and security-safe defaults without claiming the Phase 7 trusted-proxy control is complete.
7. Run `docker compose config`, build linux/amd64 and linux/arm64 with Buildx, start locally, verify health, stop cleanly, and confirm volumes survive restart.
8. Run image vulnerability scan; classify any findings under the release policy.
9. Commit: `build: add local ARM64 container foundation`.

**Rollback point:** Stop Compose and remove only named Phase 1 disposable test volumes; never delete an unresolved path or user data.

### Task 10: Add CI quality and supply-chain gates

**Files:**

- Create: `.github/workflows/quality.yml`
- Create: `.github/workflows/container.yml`
- Modify: `scripts/quality/check.sh`, `Makefile`, `pyproject.toml`

**Traceability:** R-001, R-025, R-029, R-039; ADR-0024, ADR-0028; TM-14, TM-20.

**Steps:**

1. Write workflow contract tests or static assertions for immutable action pins, least permissions, frozen lock use, cache keys, artifact retention, and no secret exposure on untrusted pull requests.
2. Make the local quality script run formatting check, lint, strict types, unit/integration/architecture tests, coverage, dependency audit, documentation link check, and `git diff --check`.
3. Set an initial coverage gate for Phase 1 code at 90% lines and 85% branches; exclusions require explicit review.
4. Add CI workflows that call the same local script and separately build both target architectures.
5. Pin action revisions and container image digests selected during implementation.
6. Run the full local gate and validate workflow syntax.
7. Commit: `ci: enforce Phase 1 quality and ARM64 gates`.

**Rollback point:** Revert CI adapter without removing the authoritative local gate.

### Task 11: Build the reproducible Phase 1 qualification harness

**Files:**

- Create: `scripts/benchmarks/run_phase1_qualification.sh`
- Create: `docs/operations/phase1-qualification.md`
- Create: evidence directory placeholders under `docs/evidence/m1-platform/`
- Modify: `docs/quality/representative-dataset.md` only if a Phase 1-specific manifest extension is needed

**Traceability:** R-025, R-039; ADR-0024, ADR-0028; TM-18, TM-20.

**Steps:**

1. Define a versioned manifest schema for board/firmware, OS digest, kernel, CPU/cooling, ext4/mounts, SSD/fsync, Docker/Compose, image digests, Python, SQLite compile options, encryption state, cache state, and revision.
2. Write harness self-tests for missing fields, invalid environment, output determinism, and failure propagation.
3. Implement commands measuring container readiness time, steady idle RSS/CPU, health latency, SQLite open/write/checkpoint behavior, image size, and filesystem qualification.
4. Run first on development hardware and label it non-qualifying.
5. Run natively on the pinned Pi 5 and retain raw plus summarized evidence.
6. Confirm targets: readiness at most 15 seconds, total steady application memory at most 512 MiB, idle CPU at most 5% of one core, and no unsupported filesystem warning.
7. Commit: `test: add reproducible Phase 1 qualification harness`.

**Rollback point:** Harness is non-mutating except for explicit temporary benchmark data created under validated temporary paths.

### Task 12: Close M1 with evidence and review

**Files:**

- Modify: `docs/evidence/m1-platform/README.md`
- Create: evidence manifests/results under the prescribed M1 hierarchy
- Modify: `docs/requirements/traceability-matrix.md` only to link stable evidence identifiers, not to weaken requirements
- Create: `docs/evidence/m1-platform/approvals/m1-review.md`

**Traceability:** All Phase 1 rows, especially R-029 and R-039; ADR-0028; TM-20.

**Steps:**

1. Run `scripts/quality/check.sh` from a clean checkout with `uv sync --frozen`.
2. Run clean SQLite migration upgrade/downgrade/re-upgrade.
3. Run Compose configuration, multi-architecture build, local smoke, and clean shutdown.
4. Run the Pi qualification procedure.
5. Verify every M1 traceability row has exact command/procedure, revision, environment, raw output, result, and reviewer fields.
6. Run documentation-link, ADR-status, decision-freeze, and absence-of-Phase-2-code checks.
7. Request code review using `superpowers:requesting-code-review`.
8. Address verified findings under `superpowers:receiving-code-review`.
9. Run the complete verification suite again using `superpowers:verification-before-completion`.
10. Commit: `docs: record Phase 1 qualification evidence`.
11. Stop at M1 and request explicit approval before Phase 2.

**Rollback point:** If M1 fails, do not mark it accepted. Retain failed evidence, revert unsafe release changes, and correct on the Phase 1 branch.

## Ordered Git branch and commit sequence

Baseline already preserved:

1. `bb3ab39 docs: approve SnakeTracker architecture baseline`

After plan approval:

1. Create `phase1/platform-foundation` from `bb3ab39`.
2. `docs: add Phase 1 platform implementation plan`
3. `chore: establish Python project toolchain`
4. `test: enforce architecture and phase boundaries`
5. `feat: add typed runtime configuration`
6. `feat: add safe startup compatibility checks`
7. `feat: establish SQLite operational profile`
8. `chore: establish reversible migration framework`
9. `feat: add safe observability and health probes`
10. `feat: add Phase 1 worker lifecycle shell`
11. `build: add local ARM64 container foundation`
12. `ci: enforce Phase 1 quality and ARM64 gates`
13. `test: add reproducible Phase 1 qualification harness`
14. `docs: record Phase 1 qualification evidence`

Every implementation commit must be green for its scoped tests and pass `git diff --check`. Do not combine later business functionality into these commits.

## Risks and mitigations

| Risk | Impact | Mitigation and rollback |
|---|---|---|
| Python 3.13 dependency lacks ARM64 wheel | Slow/failed builds | Verify before acceptance; prefer pure Python/system-supported package; pin known-good version or replace via ADR impact review |
| SQLite FULL durability misses latency target | Slow writes | Preserve durability; benchmark SSD/profile and optimize transaction scope; revise only through ADR evidence |
| Filesystem detection false positive/negative | Unsafe production storage or blocked valid host | Fail closed in production, expose diagnostic reason, document override for tests only, validate on target Pi |
| Compose resource limits differ across runtimes | False qualification | Pin runtime/version and test native Compose behavior |
| Health checks become deep or expensive | Cascading failure | Keep liveness shallow; readiness bounded; put detailed checks in operator procedures |
| Metrics leak high-cardinality identifiers | Memory/privacy issue | Allow-list label sets and test forbidden values |
| GitHub Actions ARM build passes but Pi runtime fails | False portability confidence | Require native Pi evidence before M1 acceptance |
| Alembic baseline overreaches into Phase 2 | Scope breach | Architecture scope test forbids domain/event/identity tables and packages |
| Vulnerability scanner availability/noise | Unstable CI | Pin scanner, archive raw report, define severity and exception policy without suppressing findings silently |
| Evidence is manually claimed | Invalid milestone | Require machine output or numbered procedure with revision/environment/reviewer |

## Phase 1 decisions requiring owner approval

1. Approve `uv` and committed `uv.lock` as the packaging/lock strategy.
2. Approve synchronous SQLAlchemy with Python's SQLite driver for v1 rather than `aiosqlite`.
3. Approve GitHub Actions as the initial CI adapter while keeping local scripts authoritative.
4. Approve the proposed initial SQLite qualification defaults: FULL durability, 5-second busy timeout, 1,000-page auto-checkpoint, and 256 MiB journal limit. These values are benchmark inputs, not permanently fixed architecture. Preserve Pi measurements under M1 evidence; later changes follow ADR-0010 and ADR-0028 where applicable.
5. Approve a 90% line / 85% branch coverage gate for Phase 1 code. Exclusions must be narrow, documented, and justified; low-value tests written only to inflate coverage are prohibited.
6. Approve loopback-only Nginx in Phase 1 and complete exclusion of cloudflared/remote access until the RD gate.
7. Approve a minimal baseline Alembic revision containing no identity, event, household, animal, job, notification, or other product tables.
8. Approve the proposed branch name and commit sequence.

All eight decisions were approved on 2026-08-04. If implementation conflicts with an accepted ADR, stop the affected task and present the conflict, alternatives, migration impact, and proposed superseding ADR before changing the architecture.

## Implementation handoff

After the owner approves this plan, execute it task-by-task with `superpowers:executing-plans` or, if explicitly requested, `superpowers:subagent-driven-development`. Stop after M1 evidence and do not enter Phase 2 without a new explicit authorization.
