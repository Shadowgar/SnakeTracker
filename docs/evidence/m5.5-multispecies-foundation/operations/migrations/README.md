# Migration and Replay Lifecycle

Result: **Pass** on August 11, 2026 at revision `fe4a476`.

A fresh temporary database upgraded through 0010, downgraded to 0009 while it contained no v2
facts, and re-upgraded to 0010. Final checks reported:

- revision `0010_multispecies_foundation`;
- `PRAGMA integrity_check`: `ok`;
- `PRAGMA foreign_key_check`: empty;
- `animal_type` and `capability_profile_version` present.

The migration suite also proves existing M5 animal rows backfill to `snake.v1`, v2/Spider facts
block destructive downgrade, earlier migrations are unchanged, and M6 tables are absent.

Reproduce with `uv run pytest -q tests/integration/test_alembic_lifecycle.py` plus the lifecycle
commands recorded in `evidence-manifest.json`.

