# AT-MSP-05 — Mixed Household Collection

Result: **Pass** at revision `fe4a476`.

The qualification household contains Snake A, Snake B, Spider A, Spider B, and Spider C across
multiple enclosures. All five appear together with correct type and photo. Spider A is reassigned
between enclosures; old occupancy excludes it and current occupancy contains it exactly once.
Shared prey inventory is consumed by both types, authorization remains household-scoped, and
timeline terminology follows the selected profile.

See the [browser procedure and screenshots](../../browser/README.md). Reproduce the automated
fixture with `uv run pytest -q tests/browser/test_multispecies_workflow.py`.

