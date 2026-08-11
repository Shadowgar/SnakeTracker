# M5 Expense Policy

Result: **Pass**

Source revision: `f976b4622a0f72bd165c906cdc8ab5d72a399cc6`  
Reviewer: Codex local qualification; owner acceptance pending.

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
