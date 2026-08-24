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
- Scenario: `four-group-owner-review.v1`
- Contents: four Snakes, three Spiders, three Lizards, and three Scorpions; 11 enclosures; 13
  distinct fictional photos; 248 domain events; shared inventory; expenses; reminders; reports;
  search; and prediction-ready plus insufficient-history examples.
- Prediction-ready: Ember, Juniper, Nova, Onyx, Pearl, and Sol.
- Intentionally insufficient: Bramble, Cobalt, and Pip.

The household itself is created atomically through the accepted ADR-0040 internal provisioner and
canonical `household.created` and `household.owner_added` events. All fictional product data is then
created through supported application/domain interfaces. Reruns return the verified manifest; an
interruption after complete population is recovered by exact shape and keeper-page verification,
without deleting or duplicating data.

An explicit `--reset-existing-demo` replacement is restricted to the deterministic demo household
ID. It retains the demo household identity and backup records, removes only its disposable product
state and files, and rebuilds its projections. It never resets the shared database or the real
household.

From the repository root:

```bash
./scripts/development/m6_owner_review_demo.sh status
./scripts/development/m6_owner_review_demo.sh seed --as-of 2026-08-24
./scripts/development/m6_owner_review_demo.sh seed --as-of 2026-08-24 --reset-existing-demo
```

The wrapper neither starts an alternate stack nor targets another port. It requires the existing
promoted database and refuses incomplete/conflicting state. The reset form is only for deliberate
replacement of the reserved demo fixture.

## Safety and scope

The real household’s identity, membership, animal, event history, and attachment records match
their pre-provisioning hashes. Automated tests cover bidirectional direct-identifier, mutation,
attachment, search, report, and list isolation. No production husbandry reference content is
enabled.

The current [four-group qualification](../four-group-expansion/README.md) records the backup,
real-household hashes, tests, and promoted Raspberry Pi 5 runtime.

This environment is local owner-review evidence only. It does not approve M6, production or remote
access, M7 deployment-performance qualification, or PR #8.
