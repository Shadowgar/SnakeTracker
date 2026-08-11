# AT-MSP-03 — Spider Care

Result: **Pass** at revision `fe4a476`.

Spider profiles support shared identity and photos, feeding/refusal/prey, optional weight,
molt/correction, premolt observed/cleared state, type-neutral rehousing, configured misting,
cleaning/water care, notes, inventory, expenses, reminders, and effective history. Deterministic
correction/void/reinstatement behavior is tested only where registered handlers exist.

Reproduce with `uv run pytest -q tests/integration/test_multispecies_animals.py
tests/browser/test_multispecies_workflow.py`.

