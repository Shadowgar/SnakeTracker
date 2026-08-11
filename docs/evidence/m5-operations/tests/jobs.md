# M5 Durable Jobs

Result: **Pass**

Source revision: `f976b4622a0f72bd165c906cdc8ab5d72a399cc6`  
Reviewer: Codex local qualification; owner acceptance pending.

Tests cover durable ownership, lease acquisition and expiry, heartbeats, fencing tokens, safe
takeover, retry ceilings, deterministic backoff, reconciliation, terminal dead letters, and
idempotent worker execution. Invalid lease inputs and attempts that expire after an external
provider acceptance are rejected or routed to reconciliation rather than silently completed.

Reproduce:

```sh
uv run pytest -q tests/integration/test_durable_jobs.py
```
