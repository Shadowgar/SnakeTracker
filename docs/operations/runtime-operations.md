# Runtime Operations Runbook

## Service topology

Run Nginx, one FastAPI web process, one scheduler/worker, cloudflared, and the optional backup agent through Docker Compose. For Raspberry Pi deployment, SQLite, attachments, Docker data, and backup staging must resolve to a local SSD using ext4. Do not deploy the database on NFS, SMB, a synchronized folder, or an SD card. Laptop development uses a supported local filesystem under the explicit development classification and does not prove the future Pi storage topology.

## Health

- **Liveness:** process can answer without checking every dependency.
- **Readiness:** database accessible, migrations compatible, known event contracts/plugins present, trusted projections available, and no restoration maintenance mode.
- **Administrative health:** authenticated projection lag, job/dead-letter state, WAL size, disk headroom, backup status, compatibility matrix, and audit warnings.

## SQLite maintenance

The approved SQLite profile uses foreign keys, WAL, full authoritative-write durability, bounded busy timeout, controlled checkpoints, and incremental vacuum. Development defaults are measured during M1; exact deployment values are versioned in the release qualification manifest after Phase 7/pre-deployment Pi measurement.

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

Password-reset delivery does not use the husbandry notification pipeline. It crosses a separate
identity-message port and is disabled until an adapter is explicitly configured. The local-file
adapter is development/test-only; production startup rejects it. A future production email adapter
must accept the already-constructed canonical-origin message without changing identity semantics and
must prevent reset URLs from entering provider analytics or ordinary application logs.

For emergency self-hosted recovery, a trusted local operator may run:

```text
docker compose exec web python -m snaketracker.operations.account_recovery owner@example.com
```

The command accepts an email address only, creates the same 45-minute one-time credential, audits the
operator initiation, and prints the URL to the attached terminal. It has no browser admin route and
never accepts a plaintext password argument. Do not redirect or persist its output; complete the reset
in the browser and require a fresh sign-in.

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

Application rollback requires actual older-binary support for schema, events, embedded identities,
projection requirements and runtime formats. No Alembic migration does not establish safety. If
incompatible facts have been written, use compatible code or an explicitly authorized verified
historical restore with stated RPO/loss. A taxonomy-generation pointer rollback is separate and
preserves household data, permanent identities/mappings/overlay, guides and X3 content.

## Restricted recovery mode

Unknown newer schemas/contracts, missing plugin handlers, or incompatible projection requirements prevent ordinary startup. Only local or strongly authenticated diagnostic endpoints may operate. No business writes occur. The operator installs compatible code/handlers or performs a validated restore; bypassing contract checks is prohibited.

## Planned compatibility preflight

The reconciled X1 contract for existing storage is read-only inspection → schema/Alembic → event
contracts → required embedded profile identities → projection catalog → X2 active reference
structures when implemented → X3 selected-content/publication structures when implemented. Only
then may mutable engine initialization, replay/catch-up, generation changes, scheduling, workers,
job claiming or ordinary traffic start. Initial database creation and explicit migration remain
separate workflows. X1 supplies extension points, not future X2/X3 validators.

At baseline `4be4deb`, application composition calls the SQLite engine factory before compatibility
inspection; the factory applies mutable setup. This planned order is a release requirement, not a
claim about current startup. See [ADR-0045](../adr/0045-extensible-animal-capability-evolution.md).

X1 adds no job types. Initial X2 import may be a bounded operator workflow. Before a second queued
workload, likely X3 enrichment, qualify typed claiming/lease recovery, payload validation, handlers
and retry semantics in the existing SQLite queue. Separate taxonomy/content/media adapters should
share bounded aggregate provider transport when needed; acquisition does not authorize publication.
No new broker/queue or provider coordinator is implemented by this reconciliation.

## Separate production security follow-up

Open follow-up from October 5 finalization: the running accepted image
`snaketracker:m66b-reference-density-04364cc` still contains the separately identified PCRE2/Perl
packages (`libpcre2-8-0` 10.42-1+deb12u1 and `perl-base` 5.36.0-7+deb12u3). The
[PR #17 container qualification](https://github.com/Shadowgar/SnakeTracker/actions/runs/37320148868)
reported package findings before a fresh CI rebuild passed. Successful CI for a freshly built image
does not patch an already-running production image. This records package findings and an operations
follow-up, without asserting application exploitability or a current exhaustive scan.

Remediation belongs to separately authorized security/operations work with current advisory,
package/image and recovery qualification. Do not fold OS/base-image/runtime-package upgrades or
host-service restarts into X1 architecture or this documentation task. Production is untouched.
