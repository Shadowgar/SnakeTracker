# Consolidated M6 Owner-Review Runtime

Status: **Pass — available for owner inspection; M6 owner acceptance pending**

On August 16, 2026, the promoted laptop/Docker runtime was rebuilt from revision `0dc458d` and
qualified at `http://localhost:8081`. It is the only running Care Keeper/SnakeTracker Compose
project. The unrelated Astronomy Hub project was not changed.

The single promoted SQLite database contains two strictly isolated households:

- the existing real household, owner identity, one animal, 15 domain events, and one immutable
  attachment version; and
- the reserved ADR-0040 fictional household with 12 animals, nine enclosures, 366 domain events,
  12 distinct profile-photo versions, shared inventory, expenses, reminders, reports, search, and
  sufficient/insufficient analytics histories.

The fictional login is `owner@m6-demo.invalid` / `m6-demo-local-only-password`. This credential is
valid only for the local owner-review environment. The real credential is intentionally omitted
from evidence.

## Qualification

- Alembic current revision: `0011_product_experience` (head).
- `/health/live` and `/health/ready`: HTTP 200.
- SQLite `PRAGMA integrity_check`: `ok`.
- Actual HTTP demo login: 303 to `/home`; Today, Animals, and immutable PNG delivery: HTTP 200.
- Trusted provisioner and bidirectional isolation suite: 12 tests passed.
- Provisioner rerun and completed-dataset recovery are idempotent; no event or schema rewrite was
  used.
- Real household, owner, membership, animal, event, and attachment row-set hashes match the
  pre-provisioning baseline; details are in [data verification](data-verification.md).
- Alternate ports 18083 through 18087 are closed. Their runtime directories were preserved.

See [runtime inventory](runtime-inventory.txt) for the final container/listener state and
[mobile-first browser evidence](../../browser/mobile-first/README.md) for the actual owner journey.

This evidence qualifies the local M6 owner-review environment only. It does not record M6 owner
acceptance or production, remote-access, or Raspberry Pi deployment qualification.
