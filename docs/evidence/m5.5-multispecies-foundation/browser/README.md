# Mixed-collection Browser Qualification

Result: **Pass** on August 11, 2026 at revision `fe4a476`.

A real Chromium session against an isolated Docker Compose stack created one household with two
Snakes and three Spiders, uploaded five profile photos, assigned and reassigned animals across
three enclosures, consumed shared prey inventory, recorded molt/premolt/misting care, configured an
applicable reminder, and completed logout/login. The browser reported zero console errors and zero
warnings. The normal development stack remains available at `http://localhost:8081`.

Retained views:

- [Desktop mixed collection](desktop-mixed-collection-photos.png)
- [Desktop Spider profile](desktop-spider-profile.png)
- [Mobile mixed collection](mobile-mixed-collection-photos.png)
- [Mobile Spider profile](mobile-spider-profile.png)
- [Mobile Spider care history](mobile-spider-care-history.png)

The automated five-animal journey is reproducible with `uv run pytest -q
tests/browser/test_multispecies_workflow.py`.

Final review re-ran real Chromium on August 15, 2026 against an isolated Compose stack at revision
`ebd5200`. Desktop and 390×844 mobile views showed the same five animals and photos, capability-
appropriate Spider actions, correct three-Spider nursery occupancy after reassignment, shared stock
at three items after Snake and Spider feedings, effective Spider care history, and the applicable
molt reminder. Both viewports had zero console errors/warnings; mobile had no horizontal overflow.
The isolated stack was stopped afterward, while the normal development stack remained healthy on
port 8081.
