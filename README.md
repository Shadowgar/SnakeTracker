# SnakeTracker

SnakeTracker is a lightweight, self-hosted reptile husbandry tracker. The Phase 4 branch provides
the secure local household experience plus animal profiles, feeding and measurement records,
sheds, baths/soaks, enclosures, cleaning, profile photos, effective history, and basic verified
backups. Remote access and Raspberry Pi deployment qualification remain deferred.

## Run the local site

The owner-facing local URL is **http://localhost:8081**. Nginx listens on port 8080 only inside its
container.

Create the ignored local state and secrets once:

```sh
mkdir -p runtime/data secrets
openssl rand -hex 32 > secrets/runtime_secret
openssl rand -hex 32 > secrets/backup_encryption_key
```

Then build and start SnakeTracker:

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
