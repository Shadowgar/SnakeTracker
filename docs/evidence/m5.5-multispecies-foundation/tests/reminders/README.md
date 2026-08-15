# Applicable Reminder Schedules

Result: **Pass** at revision `fe4a476`.

Reminder choices are derived from registered profile policies. Spider molt and configured
enclosure-misting schedules succeed; Snake molt/misting schedules and empty-enclosure misting
schedules fail server-side. Existing M5 fact, intent, outbox, job, and attempt deduplication and
recovery tests remain green.

Reproduce with `uv run pytest -q tests/integration/test_reminders.py
tests/integration/test_multispecies_animals.py tests/integration/test_notification_pipeline.py
tests/integration/test_durable_jobs.py tests/integration/test_notification_delivery.py`.

