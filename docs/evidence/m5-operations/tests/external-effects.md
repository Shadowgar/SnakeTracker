# M5 External-Effect Crash Window

Result: **Pass**

Source revision: `e1a15025b4b5caa81391866d49c1b5a050f616be`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

External execution is explicitly at least once. The local qualification provider records a stable
provider idempotency key and durable external operation identifier. Tests simulate a crash after
provider acceptance but before local completion, then prove that safe retry/reconciliation
converges on the original provider operation without issuing a second effect. Unknown providers
fail closed and terminal uncertainty remains visible for operator reconciliation.

Reproduce:

```sh
uv run pytest -q tests/integration/test_notification_delivery.py
```
