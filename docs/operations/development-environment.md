# Development Environment

## Required tools

- Python 3.13.14 for the initial Phase 1 qualification run
- uv 0.12.1 or the release-pinned replacement
- Git
- Docker Engine with Compose v2 for container tasks

Run `./scripts/development/bootstrap.sh` after installing `uv` through its independently
verified installation procedure. The script installs the approved Python line and runs
`uv sync --frozen`; it never changes the operating-system Python environment.

## Configuration

Copy `.env.example` to a local ignored `.env` only for developer convenience. Runtime
configuration is supplied with `SNAKETRACKER_` variables. Production must provide an
absolute database path, an HTTPS external origin, and a runtime secret of at least 32
characters.

Secrets support a Docker-compatible `_FILE` form. Set either the direct variable or its
`_FILE` counterpart, never both. Secret values are represented by Pydantic `SecretStr`
and must not be logged, placed in Compose files, or committed. Phase 1 does not use the
generic runtime secret for identity or sessions.

## Quality gate

Run `make check` or `./scripts/quality/check.sh`. The script is authoritative locally and
in CI. Coverage exclusions are limited to the two documented non-runtime branches in
`pyproject.toml`; new exclusions require review and must not replace meaningful tests.
