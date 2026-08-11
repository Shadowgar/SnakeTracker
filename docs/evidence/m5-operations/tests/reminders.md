# M5 Reminder Scheduling

Result: **Pass**

Source revision: `6f1bb5b8f5dc4b5d37dcf8acd839c6b2d05c6972`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

The suite verifies fixed and event-relative owner-configured schedules, UTC storage with household
timezone presentation, subject registration and ownership, calculation provenance, owner due-date
overrides, and latest-effective-history recalculation after correction, void, reinstatement, and
authoritative replay. Profile saves create or update one logical rule, reject stale versions,
disable without a keeper-facing audit-reason field, and fail closed for unsupported or missing
subjects. Feeding refusals and regurgitations do not reset accepted-feeding schedules. Weight,
length, bath, cleaning, and water-change schedules retain their established effective source-event
rules. Repeated scans, worker restarts, and duplicate execution remain idempotent. No species
advice or Phase 6 prediction logic is encoded.

Reproduce:

```sh
uv run pytest -q tests/integration/test_reminders.py tests/browser/test_operational_workflows.py
```

The retained browser workflow shows a feeding interval configured on the animal profile and its
calculated upcoming item in the care agenda. Automated browser coverage also proves overdue,
due-today, and upcoming grouping; no ordinary Add Reminder, disable-reason, or technical controls
appear on the agenda.
