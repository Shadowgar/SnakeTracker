# SQLite Profile and Storage Evidence

- Requirement: R-010 / OP-DB-01
- ADRs: ADR-0009, ADR-0010, ADR-0024, ADR-0036
- Threat controls: TM-09, TM-18
- Source revision: `da061911a7956892adbf8b5a1414e7407ce05b2a`
- Execution time: 2026-08-04T10:05Z
- Reviewer: Pending owner review

Command:

```sh
scripts/benchmarks/run_phase1_qualification.sh \
  --classification non-qualifying-development \
  --cache-state warm \
  --cache-preparation 'existing image and host page cache; no cache reset' \
  --candidate-data-root runtime/qualification \
  --idle-settle-seconds 5 \
  --output-dir docs/evidence/m1-platform/performance/development-host-warm
```

Measured SQLite results are in [results.json](../performance/development-host-warm/results.json).
WAL, synchronous `FULL` (`2`), 5,000 ms busy timeout, 1,000-page automatic WAL checkpoint,
268,435,456-byte journal limit, incremental auto-vacuum (`2`), FTS5 creation, passive checkpoint,
and `quick_check=ok` all passed. Two hundred FULL-durability commits measured p50 1.117 ms,
p95 1.376 ms, and max 2.183 ms on this host. The application database and
`0001_phase1_baseline` revision also survived a service restart.

The database path resolved to ext4 on `/dev/sdc` and passed the unsupported-filesystem guard.
The host reports that virtual device as rotational with no transport, so the harness correctly
marks the medium unverified. Result for M1: **pass for the supported development-filesystem and
SQLite-profile checks**. This WSL2 x86_64 result does not prove the future Raspberry Pi local-SSD
and ext4 deployment gate; that independent check remains mandatory in Phase 7/pre-deployment.
