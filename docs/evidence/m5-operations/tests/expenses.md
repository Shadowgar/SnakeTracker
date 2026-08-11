# M5 Expense Policy

Result: **Pass**

Source revision: `de39d1d17448d0016a0b83e13bcf301c23cc390b`
Reviewer: Codex final qualification; owner accepted August 11, 2026.

Tests prove Owner and Administrator authorization, household isolation, validation, idempotency,
append-only correction lineage, effective-value reads, voiding with a reason, and the intentional
M5 prohibition on reinstatement. Expense mutations also append conventional security-audit
records outside domain-event history.

Reproduce:

```sh
uv run pytest -q tests/integration/test_expenses.py tests/browser/test_operational_workflows.py
```

The real-browser evidence includes an authorized `$42.75` feeder expense and its focused
correction/void screen.
