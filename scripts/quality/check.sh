#!/usr/bin/env sh
set -eu

uv run ruff format --check .
uv run ruff check .
uv run python scripts/quality/verify_architecture.py src
uv run python scripts/quality/verify_architecture_freeze.py
uv run python scripts/quality/verify_docs_links.py
uv run mypy
uv run pytest --cov=snaketracker --cov-branch --cov-report=term-missing --cov-report=json:coverage.json --cov-report=xml:coverage.xml --junitxml=junit.xml
uv run python scripts/quality/verify_coverage.py coverage.json
audit_requirements="$(mktemp)"
trap 'rm -f "$audit_requirements"' EXIT HUP INT TERM
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file "$audit_requirements" --quiet
uv run pip-audit --strict --requirement "$audit_requirements"
docker compose config --quiet
git diff --check
