# AT-MSP-02 — Legacy Replay and Compatibility

Result: **Pass** at revision `fe4a476`.

The frozen `animal.registered` v1 fixture remains byte-stable and deserializes unchanged as the
legacy payload while resolving to `snake.v1`. Migration 0010 backfills only the rebuildable current
projection and never modifies stored event envelopes, payload JSON, contract identity, ordering,
or checksums. Unknown type/profile versions fail closed. The downgrade guard refuses to erase v2
or Spider meaning.

The focused 41-test migration/replay/backup suite passed. Reproduce the immutable contract portion
with `uv run pytest -q tests/unit/platform/test_event_registry.py
tests/unit/domains/test_animal_contracts.py tests/integration/test_alembic_lifecycle.py`.

