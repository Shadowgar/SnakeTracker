# Phase 1 Platform Qualification

This procedure measures the Phase 1 container and SQLite foundation. Results are qualification evidence only when run natively on the pinned Raspberry Pi 5 environment with `--classification qualifying-pi5`. Developer and emulated ARM64 runs must be labeled `non-qualifying-development`.

## Prerequisites

- Checkout the exact revision under test and run `uv sync --frozen`.
- Create a dedicated, existing candidate directory on the filesystem being qualified. Pass
  that exact path with `--candidate-data-root`; the harness creates its private temporary
  data directory beneath it and rejects `/`, the operator's home directory, and missing paths.
- Place Docker's data root on the candidate local SSD as well so image and container I/O use
  the pinned storage topology.
- Build `snaketracker:phase1` with the host UID: `SNAKETRACKER_UID=$(id -u) docker compose build`.
- Set `SNAKETRACKER_OS_IMAGE_DIGEST`, `SNAKETRACKER_PI_FIRMWARE`,
  `SNAKETRACKER_COOLING`, and `SNAKETRACKER_ENCRYPTION_CONFIGURATION` to the pinned
  qualification values. Storage medium, controller, capacity, rotational state, and transport
  are measured from the candidate mount and cannot be supplied through environment labels.
- Record cold-cache and warm-cache runs separately. Describe the exact preparation in
  `--cache-preparation`; a qualifying Pi run rejects an unspecified preparation. Do not claim
  native Pi qualification from QEMU or another host architecture.

## Commands

Development-only evidence:

```sh
mkdir -p runtime/qualification
scripts/benchmarks/run_phase1_qualification.sh \
  --classification non-qualifying-development \
  --cache-state warm \
  --cache-preparation 'existing image and host page cache; no cache reset' \
  --candidate-data-root runtime/qualification \
  --output-dir docs/evidence/m1-platform/performance/development-host
```

Native Pi evidence, repeated once for each cache state:

```sh
scripts/benchmarks/run_phase1_qualification.sh \
  --classification qualifying-pi5 \
  --cache-state cold \
  --cache-preparation 'sync; drop Linux page cache immediately before run; image preloaded' \
  --candidate-data-root /srv/snaketracker-qualification \
  --output-dir docs/evidence/m1-platform/performance/pi5-cold

scripts/benchmarks/run_phase1_qualification.sh \
  --classification qualifying-pi5 \
  --cache-state warm \
  --cache-preparation 'run once on same boot and image before measured run; no cache reset' \
  --candidate-data-root /srv/snaketracker-qualification \
  --output-dir docs/evidence/m1-platform/performance/pi5-warm
```

The cold-cache description is an operator attestation; perform the documented cache reset using
the pinned host's approved administrative procedure before invoking the harness. The harness does
not request elevated privileges or alter host-wide cache state itself.

The harness creates a private temporary database and secret beneath the candidate directory,
starts an isolated Compose project, samples container resources 12 times at five-second intervals,
restarts the web, worker, and Nginx services, verifies the schema survives, and always tears the
project down. It never reuses or deletes the operational database. Generated artifacts are
`environment-manifest.json`, `results.json`, `compose.log`, `summary.md`, and
`artifact-hashes.json`.

## M1 targets

- Readiness within 15 seconds.
- Web, inert worker, and Nginx steady memory at or below 512 MiB total.
- Aggregate steady idle CPU at or below 5% of one core.
- Database path passes the local-filesystem guard.
- Database file and Alembic revision survive a service restart, with readiness restored within
  15 seconds.
- SQLite reports WAL, FULL (`2`), 5,000 ms busy timeout, 1,000-page automatic checkpoint, 256 MiB journal limit, incremental auto-vacuum (`2`), and `quick_check=ok`.
- SQLite FTS5 creation succeeds and the passive WAL checkpoint reports no busy writer.

These values are qualification defaults governed by ADR-0010 and ADR-0024. A later value change requires measurement and the ADR-0028 decision-freeze process where applicable.
