# M6 Owner-Review Environment

Status: **available for owner inspection; M6 owner acceptance pending**

## Single promoted runtime

Care Keeper is available only at `http://localhost:8081`. The `snaketracker` Compose project mounts
the preserved `runtime/phase2` database and attachment tree. The same SQLite database contains the
existing real household and the separate ADR-0040 fictional household; every protected request is
scoped to current membership.

The six older review projects have been stopped without deleting their runtime directories. Ports
18083 through 18087 are closed. See the [consolidation evidence](consolidated-demo/README.md).

## Fictional owner-review household

- Email: `owner@m6-demo.invalid`
- Password: `m6-demo-local-only-password`
- Scenario: `m6-owner-review.v2`
- Contents: six Snakes and six Spiders, nine enclosures, 12 distinct fictional photos, 366 domain
  events, shared inventory, expenses, reminders, reports, search, and prediction-ready plus
  insufficient-history examples.

The household itself is created atomically through the accepted ADR-0040 internal provisioner and
canonical `household.created` and `household.owner_added` events. All fictional product data is then
created through supported application/domain interfaces. Reruns return the verified manifest; an
interruption after complete population is recovered by exact shape and keeper-page verification,
without deleting or duplicating data.

From the repository root:

```bash
./scripts/development/m6_owner_review_demo.sh status
./scripts/development/m6_owner_review_demo.sh seed --as-of 2026-08-16
```

The wrapper neither starts an alternate stack nor targets another port. It requires the existing
promoted database and refuses incomplete/conflicting state.

## Safety and scope

The real household’s identity, membership, animal, event history, and attachment records match
their pre-provisioning hashes. Automated tests cover bidirectional direct-identifier, mutation,
attachment, search, report, and list isolation. No production husbandry reference content is
enabled.

This environment is local owner-review evidence only. It does not approve M6, production
deployment, remote access, or Raspberry Pi qualification.
