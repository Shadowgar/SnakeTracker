# Care Keeper

Care Keeper is a self-hosted, mobile-first app for keeping an exotic-animal household organized.
It supports snakes, lizards, spiders, and scorpions, with care actions tailored to each group. The
repository and Python package retain the historical name `snaketracker`.

## What it does

- **Animals and care:** Keep profiles, photos, enclosures, feedings, measurements, sheds or molts,
  baths, misting, and a correctable care history in one place. Today, Calendar, and Quick Log help
  with daily work.
- **Species and plants:** Search a shared species directory, link a taxon to an animal, and keep a
  plant roster for each enclosure. Manual species and plant entry remain available when external
  discovery is unavailable. Eligible species reference images include attribution; a keeper's own
  animal photo takes priority.
- **Supplies and spending:** Track stock, purchases, physical counts, stock-linked feedings,
  expenses, and item and collection reports. Purchase history supports FIFO inventory valuation;
  reports distinguish cash spent, stock on hand, and the value of supplies used.
- **Planning and insight:** Set reminders, search records, review animal analytics and care-window
  estimates, and export supported reports as CSV.
- **Household operation:** Use household-scoped accounts, encrypted backups, health checks, and a
  separate worker for scheduled jobs. The interface is server-rendered and installable as a PWA;
  care records and writes require a connection.

Care Keeper currently serves one household with multiple users. The species directory is
implemented; sourced care guides, automatic care suggestions, and bioactive plant-care workflows
are later M6.6 work. Formal Raspberry Pi deployment and release qualification are tracked in the
[roadmap](docs/roadmap/milestones.md).

## Run locally

You need Docker Engine with Compose v2 and OpenSSL. The default site is available only on the host
at **http://localhost:8081**. Create local data directories and secret files once:

```sh
umask 077
mkdir -p runtime/data secrets
openssl rand -hex 32 > secrets/runtime_secret
openssl rand -hex 32 > secrets/backup_encryption_key
chmod 700 runtime/data secrets
chmod 600 secrets/runtime_secret secrets/backup_encryption_key
```

Start the development stack from the repository root:

```sh
SNAKETRACKER_DATA_DIR=./runtime/data \
SNAKETRACKER_BIND_ADDRESS=127.0.0.1 \
SNAKETRACKER_HTTP_PORT=8081 \
SNAKETRACKER_EXTERNAL_ORIGIN=http://localhost:8081 \
docker compose up -d --build
```

Open [setup](http://localhost:8081/setup) to create the first household and owner on a fresh
database. On later visits, use [login](http://localhost:8081/login). The explicit values in the
command override any older local `.env` settings. `docker compose ps` shows service health, and
`docker compose down` stops the stack. Data and backups remain in `runtime/data`.

The Compose stack runs a migration job, one FastAPI web process, a worker, and Nginx. Nginx is the
only host-facing service. For configuration and deployment procedures, see the
[development guide](docs/operations/development-environment.md) and
[operations runbook](docs/operations/runtime-operations.md).

## Develop and verify

The application uses Python 3.13 and a locked `uv` environment. Install the required tools listed
in the [development guide](docs/operations/development-environment.md), then run:

```sh
make bootstrap
make check
```

`make check` is the same quality gate used in CI: formatting, linting, architecture and document
checks, strict typing, tests and coverage, dependency audit, and Compose validation. For a focused
test run, use `uv run pytest`.

The code is a modular FastAPI application under `src/snaketracker`. Immutable business events are
the source of truth; SQLite stores those events, current-state projections, search indexes, and
operational records. The [architecture package](docs/README.md) explains the boundaries and
decisions, while the [backup and restoration runbook](docs/operations/backup-and-restoration.md)
covers data recovery.
