# M5 Durable Jobs

Result: **Pass**

Source revision: `de39d1d17448d0016a0b83e13bcf301c23cc390b`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

Tests cover durable ownership, lease acquisition and expiry, heartbeats, fencing tokens, safe
takeover, retry ceilings, deterministic backoff, reconciliation, terminal dead letters, and
idempotent worker execution. Invalid lease inputs and attempts that expire after an external
provider acceptance are rejected or routed to reconciliation rather than silently completed.

Reproduce:

```sh
uv run pytest -q tests/integration/test_durable_jobs.py
```
