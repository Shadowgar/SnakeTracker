#!/usr/bin/env sh
set -eu

exec uv run python scripts/maintenance/database_maintenance.py check "$@"
