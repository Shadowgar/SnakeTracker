# M6 Owner-Review Environment

Status: **available for owner inspection; M6 owner acceptance pending**

## Normal keeper-data recovery

The normal Docker stack remains at `http://localhost:8081` and continues to mount
`runtime/phase2` as its data directory. At diagnosis, its SQLite file was 753,664 bytes at
Alembic revision `0011_product_experience`; the household, active owner membership, animal, domain
events, profile-photo metadata, and immutable attachment file were present.

The rejected login request returned `403` before credential validation. Multiple GET requests for
the login page had replaced the pre-authentication CSRF cookie, invalidating a still-open earlier
form. The login/setup form response now reuses the existing pre-authentication token, while
successful authentication still rotates to the session-bound token. A browser regression opens two
login pages and submits the first form successfully. The normal database and attachments were not
reset, replaced, or copied into the demo environment.

## Disposable fictional demo

The versioned `m6-owner-review.v1` scenario uses an entirely separate database and attachment tree:

- URL: `http://localhost:18087`
- Data: `runtime/m6-owner-review-demo`
- Compose project: `snaketracker-m6-demo`
- Email: `owner@m6-demo.invalid`
- Password: `m6-demo-local-only-password`

All content is fictional and contains no production husbandry guidance. The scenario contains two
Snakes and three Spiders across four enclosures, five distinct fictional profile images, 100 domain
events, inventory and expenses, effective corrections and voiding, and searchable notes. Its Today
page has overdue, due-today, and upcoming owner-authored reminder schedules.

Juniper has feeding and shed estimates, Ember has feeding and molt estimates, and Pip deliberately
shows `Not enough history yet`. The deterministic scenario definition fixes the dates, intervals,
facts, expected visible results, and a scenario hash. Normal application commands create the UUIDs,
password salt, events, projections, and immutable attachment records, so regenerated SQLite files
are semantically equivalent rather than byte-identical.

## Reproduction

From the repository root:

```bash
scripts/development/m6_owner_review_demo.sh seed --as-of 2026-08-15
scripts/development/m6_owner_review_demo.sh start
scripts/development/m6_owner_review_demo.sh status
```

The seed command refuses to overwrite an existing demo database. Regeneration is explicit and is
restricted to a target directory whose final name contains `demo`:

```bash
scripts/development/m6_owner_review_demo.sh stop
scripts/development/m6_owner_review_demo.sh seed --as-of 2026-08-15 --replace
scripts/development/m6_owner_review_demo.sh start
```

The implementation tests prove keeper-data isolation, refusal to overwrite by default, refusal to
target a non-demo directory, five unique 640×480 PNG profile images, expected data counts, SQLite
integrity, visible estimates, the insufficient-history state, reports, search, and reminder data.

## Browser checkpoint

Real Chromium inspection on August 15, 2026 verified:

- demo login and authenticated household access;
- all five animals and their type/photo on the home collection;
- overdue, due-today, and upcoming reminder groups;
- Juniper feeding/shed estimates and their explainable windows;
- Ember feeding/molt estimates and their explainable windows;
- Pip's explicit insufficient-history state;
- search results for both Juniper and Moonlit Forest Vivarium;
- collection, care-history, and expense report navigation; and
- no browser console errors in the inspected journey.

This environment is disposable owner-review data only. It does not approve M6, production
deployment, remote access, or Raspberry Pi qualification.
