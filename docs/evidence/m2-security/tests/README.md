# M2 Test Evidence

- Source revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Execution date: 2026-08-06
- Environment: x86_64 WSL2 laptop, Python 3.13.14
- Reviewer: Codex automated verification; final CI state retained by PR #3
- Requirements: R-015, R-016, R-017, R-024, R-033, R-039, R-043
- Threat controls: TM-01, TM-02, TM-03, TM-04, TM-09, TM-16, TM-17, TM-20

The full gate is reproducible with `./scripts/quality/check.sh`. It checks formatting, Ruff, the
ADR freeze, documentation links, strict mypy, pytest, line and branch coverage, and dependency
integrity. The final review-correction run passed 132 tests, 96.39% line coverage, 85.92% branch
coverage, all 37 accepted ADR freeze checks, 87 documentation files, strict mypy, and the dependency
audit with no known vulnerabilities.

The suites cover domain-event contracts and replay, migration lifecycle and minimum-SQLite schema
portability, bootstrap rollback/idempotency/unknown-contract failure, password verification,
session lifecycle, current authorization, durable throttling, audit records, CSRF, strict CSP,
error rendering, and the browser flow.

One non-blocking Starlette deprecation warning remains: FastAPI's current `TestClient` compatibility
shim imports the deprecated httpx-backed Starlette client. It does not affect runtime behavior and
will be removed through a future dependency update after compatibility testing.
