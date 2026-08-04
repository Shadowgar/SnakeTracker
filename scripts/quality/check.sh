#!/usr/bin/env sh
set -eu

uv run ruff format --check .
uv run ruff check .
uv run python scripts/quality/verify_architecture.py src
uv run mypy
uv run pytest --cov=snaketracker --cov-branch --cov-report=term-missing
git diff --check
