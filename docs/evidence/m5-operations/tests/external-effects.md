# M5 External-Effect Crash Window

Result: **Pass**

Source revision: `567887cc95702fa0407cebdf12d33e22b11dd8fb`
Reviewer: Codex local qualification; owner acceptance pending.

External execution is explicitly at least once. The local qualification provider records a stable
provider idempotency key and durable external operation identifier. Tests simulate a crash after
provider acceptance but before local completion, then prove that safe retry/reconciliation
converges on the original provider operation without issuing a second effect. Unknown providers
fail closed and terminal uncertainty remains visible for operator reconciliation.

Reproduce:

```sh
uv run pytest -q tests/integration/test_notification_delivery.py
```
