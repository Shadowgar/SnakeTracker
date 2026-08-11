# M5 Inventory Correctness

Result: **Pass**

Source revision: `567887cc95702fa0407cebdf12d33e22b11dd8fb`
Reviewer: Codex local qualification; owner acceptance pending.

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

The final combined M5 focused run passed 51 tests. The full repository gate passed 305 tests.
