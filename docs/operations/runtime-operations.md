# Runtime Operations Runbook

## Service topology

Run Nginx, one FastAPI web process, one scheduler/worker, cloudflared, and the optional backup agent through Docker Compose. SQLite and attachment volumes must resolve to a local SSD filesystem. Do not place the database on NFS, SMB, a synchronized folder, or an SD card.

## Health

- **Liveness:** process can answer without checking every dependency.
- **Readiness:** database accessible, migrations compatible, known event contracts/plugins present, trusted projections available, and no restoration maintenance mode.
- **Administrative health:** authenticated projection lag, job/dead-letter state, WAL size, disk headroom, backup status, compatibility matrix, and audit warnings.

## SQLite maintenance

The approved SQLite profile uses foreign keys, WAL, full authoritative-write durability, bounded busy timeout, controlled checkpoints, and incremental vacuum. Exact values are versioned in the release qualification manifest after Pi measurement.

- Monitor WAL continuously; warn at 512 MiB and treat 1 GiB as critical for the representative dataset.
- Use passive checkpoints during normal service and a controlled restart checkpoint in a quiet window.
- Run quick integrity checks daily and full integrity checks on the documented schedule and before/after high-risk maintenance.
- Run query statistics maintenance after material data change.
- Perform bounded incremental vacuum only after free-space qualification.
- Optimize FTS5 through a scheduled, measured maintenance job.
- Never change durability pragmas ad hoc.

## Jobs and notifications

Workers claim jobs atomically with lease owner, opaque token, acquisition, heartbeat, expiry, attempt count, and maximum attempts. Only the current token holder can heartbeat or finish. Expired jobs are safely reclaimable. Defaults are five bounded exponential retries with jitter; exhausted or permanent failures become visible dead letters.

External execution is at least once. Each adapter documents provider idempotency, durable operation-ID reconciliation, read-before-write reconciliation, or bounded duplicate tolerance. Operators reconcile uncertain outcomes before forcing retries.

## Storage pressure

Warn below 20% free space. Below 10%, block nonessential uploads and pause projection rebuilds and vacuum. Before maintenance, require the greater of 20% free space or twice the largest rebuild group plus peak WAL plus 1 GiB. These are qualification targets tied to the current representative dataset.

## Upgrade

1. Read release compatibility matrix.
2. Verify a recent backup and independent key recovery.
3. Verify maintenance headroom.
4. Stop new maintenance work.
5. Apply expand migrations.
6. Deploy compatible readers/writers.
7. Rebuild or backfill derived state.
8. Validate health and activate new generations.
9. Retain rollback assets until the acceptance window closes.
10. Contract obsolete structures only in a later release.

If new event contracts have been written, binary rollback is allowed only when the old version reads them. Otherwise restore the pre-upgrade backup and accept the documented RPO.

## Restricted recovery mode

Unknown newer schemas/contracts, missing plugin handlers, or incompatible projection requirements prevent ordinary startup. Only local or strongly authenticated diagnostic endpoints may operate. No business writes occur. The operator installs compatible code/handlers or performs a validated restore; bypassing contract checks is prohibited.
