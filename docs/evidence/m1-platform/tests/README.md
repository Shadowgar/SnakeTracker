# M1 Test Evidence

- Source revision: `da061911a7956892adbf8b5a1414e7407ce05b2a`
- Execution time: 2026-08-04T10:09Z
- Environment: x86_64 WSL2 development host, Python 3.13.14
- Dataset: `phase1-platform-empty-v1`
- Reviewer: Pending owner review

Raw output is retained in [quality-gate.log](quality-gate.log). The exact command was:

```sh
uv sync --frozen
./scripts/quality/check.sh
```

The separate [toolchain bootstrap record](../environment/README.md) retains the actual frozen-sync
execution; `quality-gate.log` begins with the quality command itself.

Result: 92 tests passed; Ruff formatting/linting passed; strict mypy passed; line coverage 99.29%;
branch coverage 98.78%; dependency audit found no known vulnerabilities; architecture freeze,
documentation links, Compose configuration, and whitespace checks passed.

## AT-ARCH-01

`tests/architecture/test_dependency_boundaries.py` and `tests/architecture/test_phase_scope.py` passed. They enforce inward dependencies, composition-root ownership, and the Phase 2+ package/file prohibition.

## AT-DB-01

`tests/integration/test_database_port.py` and the SQLite adapter tests passed. Application-owned ports remain independent of SQLAlchemy, while infrastructure owns the SQLite adapter.

## AT-OBS-01 foundation

`tests/integration/test_health_endpoints.py` plus correlation, logging, metrics, readiness, and application-startup tests passed. Phase 1 does not claim the Phase 2 security-audit portion of R-024.

## AT-API-FOUNDATION-01

Health endpoints return stable, non-sensitive liveness/readiness responses and a correlation header. Product API behavior remains prohibited until its later phase.

## DOC-ARCH-01

`scripts/quality/verify_architecture_freeze.py` confirmed ADR-0001 through ADR-0035 remain accepted on 2026-08-04 and `bb3ab39` remains an ancestor. No ADR conflict or architecture change was introduced.

## AT-COMP-FOUNDATION-01

`tests/unit/bootstrap/test_compatibility.py` and `tests/integration/test_application_startup.py` passed supported, empty, missing-metadata, older/newer/malformed, recovery-readiness, and worker-refusal cases.

## Workflow syntax

The exact actionlint command and zero exit status are retained in [actionlint.log](actionlint.log). GitHub Actions itself was not executed because no remote workflow run was requested or available in this workspace.
