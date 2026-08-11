# M5 Inventory Correctness

Result: **Pass**

Source revision: `de39d1d17448d0016a0b83e13bcf301c23cc390b`
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
