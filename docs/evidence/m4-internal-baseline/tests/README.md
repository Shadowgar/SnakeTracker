# M4 Automated Quality Evidence

Result: **Pass**

Environment: Ubuntu 24.04.3 under WSL2 on x86_64; Python 3.13.14; uv 0.12.1; SQLite 3.53.1;
Docker Engine 29.1.3; Docker Compose 2.40.3; ext4-backed development workspace.

Authoritative command:

```sh
./scripts/quality/check.sh
```

Final August 10 result:

- Ruff format: pass, 248 files checked.
- Ruff lint: pass.
- Architecture dependency validation: pass.
- Architecture freeze: pass, 37 accepted ADRs.
- Documentation links: pass, 108 files checked after the final evidence refresh.
- mypy strict: pass, 77 source files.
- pytest: **246 passed** in 29.97 seconds.
- coverage: **94.38% lines**, **85.00% branches**; both gates pass.
- pip-audit: no known vulnerabilities after upgrading cryptography to 50.0.0 and Pillow to 12.3.0.
- Compose configuration: pass.
- `git diff --check`: pass.

One upstream Starlette warning remains: FastAPI's current TestClient adapter warns about the future
`httpx2` transition. It does not affect runtime requests or the test results and is deferred to a
future dependency-compatibility update.

Migration coverage is part of `tests/integration/test_alembic_lifecycle.py`: a fresh database
upgrades through `0008_local_backups`, downgrades to base, and re-upgrades to the same head while
the Phase 2 household-event compatibility fixture remains unchanged.

A focused migration, Phase 2/3 compatibility, unknown-contract, attachment, and backup run passed
all **60 tests** after the corrected keeper UX was built. Trivy 0.69.3 reported zero fixed high or
critical vulnerabilities in the final amd64 image. The final review hardening also exercised a
deliberately slow backup with repeated durable-lease renewal.
