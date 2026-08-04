#!/usr/bin/env sh
set -eu

exec uv run python scripts/benchmarks/storage_qualification.py "$@"
