# Native Raspberry Pi 5 Qualification Status

- Requirement: R-025 / PERF-PI-01
- ADR: ADR-0024
- Threat controls: TM-18, TM-20
- Status: **Not run — mandatory native host unavailable**
- Reviewer: Pending owner review

The available host is x86_64 WSL2 (`Linux 5.15.167.4-microsoft-standard-WSL2`), not a Raspberry Pi 5. ARM64 was built under QEMU, but emulation does not satisfy native board, cooling, SSD, filesystem, idle-resource, or thermal qualification. No result has been fabricated or promoted.

To close this criterion, check out the Phase 1 review revision on the pinned Pi, build the image natively, and run both cache states using the environment fields documented in [the qualification runbook](../../../operations/phase1-qualification.md):

```sh
uv sync --frozen
SNAKETRACKER_UID=$(id -u) docker compose build
sudo mkdir -p /srv/snaketracker-qualification
sudo chown "$(id -u):$(id -g)" /srv/snaketracker-qualification

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

Required environment metadata: pinned OS image digest, Pi firmware, cooling, CPU governor,
temperature/throttle state, measured ext4 mount and SSD device facts, Docker/Compose versions,
image digest, Python/SQLite versions and compile options, encryption configuration, boot identity,
and documented cold/warm cache preparation. Owner review is required after both runs pass.
