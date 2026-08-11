# M5 Durable Jobs

Result: **Pass**

Source revision: `6f1bb5b8f5dc4b5d37dcf8acd839c6b2d05c6972`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

Tests cover durable ownership, lease acquisition and expiry, heartbeats, fencing tokens, safe
takeover, retry ceilings, deterministic backoff, reconciliation, terminal dead letters, and
idempotent worker execution. Invalid lease inputs and attempts that expire after an external
provider acceptance are rejected or routed to reconciliation rather than silently completed.

Reproduce:

```sh
uv run pytest -q tests/integration/test_durable_jobs.py
```
