# M5 Durable Jobs

Result: **Pass**

Source revision: `e1a15025b4b5caa81391866d49c1b5a050f616be`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

Tests cover durable ownership, lease acquisition and expiry, heartbeats, fencing tokens, safe
takeover, retry ceilings, deterministic backoff, reconciliation, terminal dead letters, and
idempotent worker execution. Invalid lease inputs and attempts that expire after an external
provider acceptance are rejected or routed to reconciliation rather than silently completed.

Reproduce:

```sh
uv run pytest -q tests/integration/test_durable_jobs.py
```
