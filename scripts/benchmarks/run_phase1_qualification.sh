#!/usr/bin/env sh
set -eu

exec uv run python scripts/benchmarks/phase1_qualification.py "$@"
