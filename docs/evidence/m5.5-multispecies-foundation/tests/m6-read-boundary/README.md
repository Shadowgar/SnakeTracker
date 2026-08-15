# AT-MSP-06 — M6 Read Boundary

Result: **Pass** at revision `fe4a476`.

Contract tests expose registered animal type/profile identity and applicable effective facts:
shared feeding/weight, Snake length/shed, Spider molt/premolt, neutral enclosure care, and reminder
facts. Missing inapplicable facts are not emitted as negative evidence. No search, report, chart,
analytics, prediction, guidance dataset, or PWA implementation exists in this milestone.

Reproduce with `uv run pytest -q
tests/integration/test_multispecies_animals.py::test_m6_read_boundary_exposes_only_applicable_effective_facts`.

