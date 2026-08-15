# M6 Test and Compatibility Evidence

Result: **Pass** on August 15, 2026.

The complete local gate covers formatting, Ruff, architecture boundaries/freeze, documentation
links, strict mypy, tests with line/branch coverage, dependency audit, Compose validation, and diff
integrity. It passed 390 tests with 94.93% line and 85.02% branch coverage and no known dependency
vulnerabilities. The focused migration/replay/projection/search/analytics/backup suite passed 93
tests.

Reproduce with:

```sh
./scripts/quality/check.sh
uv run pytest -q tests/integration/test_alembic_lifecycle.py \
  tests/integration/test_application_startup.py tests/integration/test_event_store.py \
  tests/integration/test_atomic_append.py tests/integration/test_projection_rebuilds.py \
  tests/integration/test_product_projection_worker.py tests/integration/test_search.py \
  tests/integration/test_measurement_analytics.py tests/integration/test_multispecies_animals.py \
  tests/integration/test_local_backups.py tests/integration/test_maintenance_cli.py \
  tests/unit/bootstrap/test_compatibility.py \
  tests/unit/application/test_suggestion_policy.py
```

Focused evidence: [freshness](async-freshness/README.md), [search](search/README.md),
[reports](reports/README.md), [measurement analytics](measurement-analytics/README.md),
[feeding analytics](feeding-analytics/README.md), [husbandry analytics and suggestions](husbandry-analytics/README.md),
[dashboard](dashboard/README.md), [references](husbandry-references/README.md),
[PWA](pwa/README.md), and [API](api/README.md).
