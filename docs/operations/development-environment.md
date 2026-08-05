# Development Environment

## Required tools

- Python 3.13.14 for the initial Phase 1 development-platform qualification run
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

## Qualification boundary

Docker on the development laptop is the primary environment through Phase 6. M1 requires local
quality checks, amd64 Compose execution, and a linux/arm64 image build. These establish
`M1 development-platform qualified`; they do not claim native Raspberry Pi behavior. Native Pi 5,
SSD/ext4, performance, thermal, SQLite persistence, and backup/restore qualification are mandatory
in Phase 7 or immediately before Pi deployment under ADR-0036.
