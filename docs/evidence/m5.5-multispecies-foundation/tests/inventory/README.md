# Shared Inventory and Compensation

Result: **Pass** at revision `fe4a476`.

The same household prey item can feed Snake or Spider profiles. Multi-stream expected versions,
idempotency, compensation, correction, void, and concurrency remain owned by the existing
inventory/event infrastructure; no type-specific inventory subsystem was introduced.

Reproduce with `uv run pytest -q tests/integration/test_inventory.py
tests/browser/test_multispecies_workflow.py`.

