# M5 External-Effect Crash Window

Result: **Pass**

Source revision: `de39d1d17448d0016a0b83e13bcf301c23cc390b`
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
