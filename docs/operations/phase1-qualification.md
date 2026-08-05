# Phase 1 Platform Qualification

This procedure measures the Phase 1 container and SQLite foundation on the development laptop.
Successful local quality checks, amd64 Compose execution, SQLite development-profile checks, and
linux/arm64 image builds support the status `M1 development-platform qualified`. Development
performance results remain non-production observations; numerical resource misses are recorded
for investigation but do not by themselves fail M1.

The same harness can later collect native evidence with `--classification qualifying-pi5`, but
that work belongs to Phase 7 or immediate pre-deployment qualification. It grants the separate
status `Raspberry Pi deployment qualified` only after the complete ADR-0036 suite passes.

## Prerequisites

- Checkout the exact revision under test and run `uv sync --frozen`.
- Create a dedicated, existing candidate directory on the filesystem being qualified. Pass
  that exact path with `--candidate-data-root`; the harness creates its private temporary
  data directory beneath it and rejects `/`, the operator's home directory, and missing paths.
- For M1, use a supported local development filesystem. For Pi deployment qualification, place
  the candidate data directory and Docker data root on the target local SSD/ext4 topology.
- Build `snaketracker:phase1` with the host UID: `SNAKETRACKER_UID=$(id -u) docker compose build`.
- Set applicable environment metadata for the development run. The future native suite also
  requires `SNAKETRACKER_OS_IMAGE_DIGEST`, `SNAKETRACKER_PI_FIRMWARE`,
  `SNAKETRACKER_COOLING`, and `SNAKETRACKER_ENCRYPTION_CONFIGURATION`.
- Do not claim native Pi qualification from QEMU, an ARM64 build, or another host architecture.

## Commands

M1 development-platform evidence:

```sh
mkdir -p runtime/qualification
scripts/benchmarks/run_phase1_qualification.sh \
  --classification non-qualifying-development \
  --cache-state warm \
  --cache-preparation 'existing image and host page cache; no cache reset' \
  --candidate-data-root runtime/qualification \
  --output-dir docs/evidence/m1-platform/performance/development-host
```

Deferred Phase 7/pre-deployment Pi evidence, repeated once for each cache state:

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

## M1 development-platform checks

- Readiness and restart/persistence checks complete successfully.
- Database path passes the local-filesystem guard.
- Database file and Alembic revision survive a service restart, with readiness restored within
  15 seconds.
- SQLite reports WAL, FULL (`2`), 5,000 ms busy timeout, 1,000-page automatic checkpoint, 256 MiB journal limit, incremental auto-vacuum (`2`), and `quick_check=ok`.
- SQLite FTS5 creation succeeds and the passive WAL checkpoint reports no busy writer.
- amd64 Compose services are healthy and linux/arm64 image construction passes.

Readiness within 15 seconds, total steady memory at or below 512 MiB, and aggregate idle CPU at or
below 5% of one core remain captured as development targets. A miss is a documented optimization
signal, not a failed M1 gate. These measurements must be repeated as mandatory budgets in the
native deployment suite.

## Raspberry Pi deployment qualification

Before actual Pi deployment, run the pinned cold- and warm-cache suites and verify native Pi 5
execution, local SSD/ext4 placement, CPU and memory budgets, temperature and throttling, SQLite
durability/WAL/integrity/restart persistence, and backup plus isolated restoration. Store the
evidence under `/docs/evidence/m7-recovery-compatibility/performance/pi` and record
`Raspberry Pi deployment qualified` only when every mandatory check passes.

These values are qualification defaults governed by ADR-0010, ADR-0024, and ADR-0036. A later value change requires measurement and the ADR-0028 decision-freeze process where applicable.
