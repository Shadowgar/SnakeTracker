# Existing Snake Compatibility

Result: **Pass** at revision `fe4a476`.

The full 335-test repository suite retains all accepted M4/M5 Snake profile, photo, feeding,
weight, length, shed/correction, bath, enclosure, inventory, expense, reminder, timeline,
attachment, and backup workflows. Snake profiles expose Snake actions and reject Spider molt,
premolt, and misting commands without appending events.

Reproduce with `uv run pytest -q tests/browser/test_animal_care_workflow.py
tests/integration/test_animal_care.py tests/integration/test_inventory.py
tests/integration/test_multispecies_animals.py`.

