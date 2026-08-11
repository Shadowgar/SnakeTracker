# M5 Migration and Compatibility Evidence

Result: **Pass**

Source revision: `6f1bb5b8f5dc4b5d37dcf8acd839c6b2d05c6972`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

The forward revision is `0009_operational_workflows`. A fresh isolated SQLite database upgraded to
head, downgraded to base, and re-upgraded to the same head; `PRAGMA integrity_check` returned `ok`.
The migration lifecycle leaves the accepted Phase 2 household and Phase 3/4 event contracts
unchanged. A focused compatibility, event-store, animal-care, backup, and maintenance regression
run passed 38 tests in 4.65 seconds.

Reproduce:

```sh
set -euo pipefail
tmp_dir="$(mktemp -d /tmp/snaketracker-m5-migration.XXXXXX)"
SNAKETRACKER_DATABASE_PATH="$tmp_dir/migration.sqlite3" uv run alembic upgrade head
SNAKETRACKER_DATABASE_PATH="$tmp_dir/migration.sqlite3" uv run alembic downgrade base
SNAKETRACKER_DATABASE_PATH="$tmp_dir/migration.sqlite3" uv run alembic upgrade head
uv run pytest -q tests/unit/bootstrap/test_compatibility.py \
  tests/integration/test_household_bootstrap.py \
  tests/integration/test_event_store.py tests/integration/test_animal_care.py \
  tests/integration/test_local_backups.py tests/integration/test_maintenance_cli.py
```

Use a disposable database for the downgrade command. Do not downgrade the retained local keeper
database.
