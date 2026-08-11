# M5 Job Crash-Recovery Procedure

Result: **Pass in automated recovery matrix**

Source revision: `567887cc95702fa0407cebdf12d33e22b11dd8fb`
Reviewer: Codex local qualification; owner acceptance pending.

Recovery behavior:

1. A worker claims only an available or expired job and receives a monotonically fenced lease.
2. A healthy worker renews the lease before expiry.
3. A restarted worker may take over only after expiry; the previous fence cannot complete it.
4. A pre-effect failure retries within the configured ceiling and then dead-letters.
5. A known provider operation is reconciled by durable external operation ID.
6. An uncertain post-effect crash remains in reconciliation until the provider result is known;
   it is never silently reported as delivered.

Reproduce the lease, restart, retry, dead-letter, and uncertain-effect matrix:

```sh
uv run pytest -q tests/integration/test_durable_jobs.py \
  tests/integration/test_notification_delivery.py
```

The authenticated `/operations/jobs` screen exposes retry, reconciliation, and dead-letter state
without exposing application secrets.
