# M5 Inventory Correctness

Result: **Pass**

Source revision: `e1a15025b4b5caa81391866d49c1b5a050f616be`
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

The final combined M5-focused run passed 51 tests. The final full repository gate passed 310 tests.
