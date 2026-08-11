# M5 Reminder Scheduling

Result: **Pass**

Source revision: `f976b4622a0f72bd165c906cdc8ab5d72a399cc6`  
Reviewer: Codex local qualification; owner acceptance pending.

The suite verifies fixed and event-relative owner-configured schedules, UTC storage with household
timezone presentation, subject registration and ownership, calculation provenance, owner due-date
overrides, and latest-effective-history recalculation after correction, void, reinstatement, and
authoritative replay. Repeated scans, worker restarts, and duplicate execution remain idempotent.
No species advice or Phase 6 prediction logic is encoded.

Reproduce:

```sh
uv run pytest -q tests/integration/test_reminders.py tests/browser/test_operational_workflows.py
```

The retained browser workflow shows a due feeding reminder explained as seven days after the fixed
schedule anchor.
