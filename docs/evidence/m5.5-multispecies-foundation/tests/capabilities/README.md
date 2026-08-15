# AT-MSP-01 — Capability Registry

Result: **Pass** at revision `fe4a476`.

The production registry contains exactly `snake.v1` and `spider.v1`. Unit and architecture tests
prove immutable definitions, unique versioned identities, rejection of invalid/duplicate/unknown
profiles, registered action/reminder matrices, and absence of M6 or arbitrary EAV capability
models. Server-side application services enforce the same policy used by read models and views.

Reproduce with `uv run pytest -q tests/unit/domains/test_animal_capabilities.py
tests/architecture/test_phase_scope.py`.

