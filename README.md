# Care Keeper

Care Keeper (internally packaged as `snaketracker`) is a lightweight, self-hosted exotic-animal
care application for Snakes, Spiders, Lizards, and Scorpions. Trusted capability profiles keep
shared identity, enclosure, feeding, inventory, expense, reminder, attachment, search, report, and
backup workflows consistent while showing only relevant care actions for each animal group.

The current owner-review build includes effective-history corrections, measurements, snake shed
history, neutral Spider/Scorpion molt and premolt history, baths and misting where applicable,
profile photos, reminders, reports, analytics, and deterministic care-window estimates. The major
M6 UX redesign remains deliberately paused until this four-group expansion is owner-reviewed.

## Run the local site

The owner-facing local URL is **http://localhost:8081**. Nginx listens on port 8080 only inside its
container.

Create the ignored local state and secrets once:

```sh
umask 077
mkdir -p runtime/data secrets
openssl rand -hex 32 > secrets/runtime_secret
openssl rand -hex 32 > secrets/backup_encryption_key
chmod 700 runtime/data secrets
chmod 600 secrets/runtime_secret secrets/backup_encryption_key
```

Then build and start Care Keeper:

```sh
SNAKETRACKER_DATA_DIR=./runtime/data \
SNAKETRACKER_BIND_ADDRESS=127.0.0.1 \
SNAKETRACKER_HTTP_PORT=8081 \
SNAKETRACKER_EXTERNAL_ORIGIN=http://localhost:8081 \
docker compose up -d --build
```

Open http://localhost:8081/setup on a fresh database or http://localhost:8081/login after setup.
The explicit environment values above override any stale local `.env` left by an earlier phase.
Check status with `docker compose ps`, and stop with `docker compose down`.

See [`docs/README.md`](docs/README.md) for the approved architecture package.
