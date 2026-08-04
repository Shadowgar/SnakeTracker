# Phase 1 Platform Qualification

This procedure measures the Phase 1 container and SQLite foundation. Results are qualification evidence only when run natively on the pinned Raspberry Pi 5 environment with `--classification qualifying-pi5`. Developer and emulated ARM64 runs must be labeled `non-qualifying-development`.

## Prerequisites

- Checkout the exact revision under test and run `uv sync --frozen`.
- Place Docker's data root and `SNAKETRACKER_DATA_DIR` on the candidate local SSD.
- Build `snaketracker:phase1` with the host UID: `SNAKETRACKER_UID=$(id -u) docker compose build`.
- Set `SNAKETRACKER_OS_IMAGE_DIGEST`, `SNAKETRACKER_PI_FIRMWARE`, `SNAKETRACKER_COOLING`, `SNAKETRACKER_STORAGE_MEDIUM=ssd`, `SNAKETRACKER_SSD_CONTROLLER`, and `SNAKETRACKER_ENCRYPTION_CONFIGURATION` to the pinned qualification values.
- Record cold-cache and warm-cache runs separately. Do not claim native Pi qualification from QEMU or another host architecture.

## Commands

Development-only evidence:

```sh
scripts/benchmarks/run_phase1_qualification.sh \
  --classification non-qualifying-development \
  --cache-state warm \
  --output-dir docs/evidence/m1-platform/performance/development-host
```

Native Pi evidence, repeated once for each cache state:

```sh
scripts/benchmarks/run_phase1_qualification.sh \
  --classification qualifying-pi5 \
  --cache-state cold \
  --output-dir docs/evidence/m1-platform/performance/pi5-cold

scripts/benchmarks/run_phase1_qualification.sh \
  --classification qualifying-pi5 \
  --cache-state warm \
  --output-dir docs/evidence/m1-platform/performance/pi5-warm
```

The harness creates a private temporary database and secret, starts an isolated Compose project, and always tears that project down. It never reuses or deletes the operational database. Generated artifacts are `environment-manifest.json`, `results.json`, `compose.log`, and `summary.md`.

## M1 targets

- Readiness within 15 seconds.
- Web, inert worker, and Nginx steady memory at or below 512 MiB total.
- Aggregate steady idle CPU at or below 5% of one core.
- Database path passes the local-filesystem guard.
- SQLite reports WAL, FULL (`2`), 5,000 ms busy timeout, 1,000-page automatic checkpoint, 256 MiB journal limit, incremental auto-vacuum (`2`), and `quick_check=ok`.

These values are qualification defaults governed by ADR-0010 and ADR-0024. A later value change requires measurement and the ADR-0028 decision-freeze process where applicable.
