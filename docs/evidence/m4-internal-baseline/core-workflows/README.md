# M4 Core Keeper Workflows

Result: **Pass**

The browser and service suites prove these household-scoped workflows:

- animal registration, profile editing, lifecycle status, listing, and profile display;
- feeding outcomes, weight and length measurements, sheds, and baths/soaks;
- append-only correction, void, and reinstatement with effective history and retained audit chain;
- enclosure registration/edit/status, animal-owned assignment, occupancy, cleaning, and water
  change records;
- immutable profile-photo selection and authenticated delivery;
- focused feeding, weight, length, shed, and bath pages plus a concise animal overview;
- payload-derived feeding and measurement values, corrected effective facts, void exclusion from
  normal history, and an optional technical-audit disclosure;
- current authorization checks on every Phase 4 page and command;
- household-local input/display with UTC event storage; and
- on-demand/scheduled backup controls with visible administrative health.

Primary acceptance tests:

```sh
uv run pytest \
  tests/integration/test_animal_profiles.py \
  tests/integration/test_animal_care.py \
  tests/integration/test_enclosures.py \
  tests/browser/test_animal_care_workflow.py -q
```

The complete gate collected 245 tests and passed all 245 on August 10, 2026. The corrected
real-browser
journey used a fresh Docker database and created one synthetic household, owner, animal, care
history, enclosure, attachment, backup request, and schedule. Screenshots are retained in
[browser evidence](../browser/README.md).
