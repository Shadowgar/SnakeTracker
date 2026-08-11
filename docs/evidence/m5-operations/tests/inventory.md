# M5 Inventory Correctness

Result: **Pass**

Source revision: `6f1bb5b8f5dc4b5d37dcf8acd839c6b2d05c6972`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

The integration suite verifies household isolation, expected stream versions, command
idempotency, concurrent receipt and consumption, reservations, expiry, adjustment, reversal, and
deterministic allocation. Stock-linked feedings append the unchanged M4 feeding event and the M5
inventory consumption in one multi-stream transaction. Feeding correction, void, and reinstatement
produce compensating inventory effects without rewriting immutable history.

Reproduce:

```sh
uv run pytest -q tests/integration/test_inventory.py
uv run pytest -q tests/integration/test_inventory.py tests/browser/test_operational_workflows.py
```

The final combined M5-focused run passed 54 tests. The final full repository gate passed 311 tests.
