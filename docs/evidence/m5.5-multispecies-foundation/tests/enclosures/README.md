# Type-neutral Enclosures

Result: **Pass** at revision `fe4a476`.

Assignment, reassignment, occupancy, cleaning, and water care remain shared Enclosure behavior.
Configured misting is stored in the Enclosure stream with an allow-listed related Animal subject.
The application rejects missing occupants, unknown profiles, Snake-only occupants, and duration
values outside 1–3600 seconds. Misting never changes occupancy semantics.

Reproduce with `uv run pytest -q tests/integration/test_enclosures.py
tests/integration/test_multispecies_animals.py`.

