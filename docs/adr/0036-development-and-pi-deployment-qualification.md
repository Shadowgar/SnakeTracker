# ADR-0036: Separate Development-Platform and Raspberry Pi Deployment Qualification

Status: Accepted
Acceptance date: 2026-08-05

## Context

SnakeTracker is being developed on a laptop with Docker and is not yet deployed to a Raspberry
Pi. Requiring native Raspberry Pi 5, SSD, thermal, and performance evidence during Phase 1 or
intermediate feature phases would block software development without increasing confidence in a
functionally incomplete application. The architecture freeze in ADR-0028 requires this timing and
milestone change to be explicit and traceable.

## Decision

Use Docker on the development laptop as the primary environment for Phases 1 through 6. During
those phases, require the locked amd64 development environment, automated quality tests, Docker
Compose validation, and linux/arm64 multi-architecture image builds in CI. ARM64 build success is
compatibility evidence; it is not evidence of native Raspberry Pi behavior.

Define two independent statuses:

1. **M1 development-platform qualified** means the laptop Docker foundation, local automated
   quality gates, amd64 runtime, Compose lifecycle, SQLite development profile, migrations, and
   ARM64 image-build checks pass with reproducible M1 evidence.
2. **Raspberry Pi deployment qualified** means the candidate release has passed the full native
   target-hardware and storage suite. This status is evaluated in Phase 7 production hardening or
   immediately before deployment to a Raspberry Pi, after the application is functionally
   complete. It is mandatory before actual Raspberry Pi deployment.

No physical Raspberry Pi is required to accept Phases 1 through 6. Requirements that depend on
native Pi behavior are deferred deployment qualifications, not failed or missing intermediate
milestone criteria. Existing laptop and WSL2 measurements remain non-production development
evidence and may identify optimization work; they do not fail M1 merely because they were not
collected on a Pi.

Use the requirement class **DDQ (Deferred deployment qualification)** for these controls. DDQ is
inactive as an intermediate feature-phase gate and becomes a mandatory release blocker for the
named deployment target.

Before the first or any materially changed Raspberry Pi deployment, qualify the release on the
pinned Raspberry Pi 5 environment and verify:

- native Raspberry Pi 5 execution;
- database, attachments, Docker data, and backup staging on a local SSD using ext4 with reliable
  locking;
- cold- and warm-cache performance against the versioned representative dataset;
- memory and CPU budgets;
- temperature, cooling, and throttling behavior under the specified workload;
- SQLite durability, WAL/checkpoint behavior, integrity, and restart persistence; and
- coherent backup, isolated restoration, and recovered-service validation.

ADR-0010 continues to govern the deployed SQLite storage profile. A development laptop may use a
supported local filesystem and documented development classification without proving the future
Pi SSD topology. ADR-0024 continues to govern the reproducibility and rigor of native Pi budgets,
but its qualification gate moves to Phase 7/pre-deployment. ADR-0035 continues to distinguish
internal, remote, and production releases; none of those labels imply Raspberry Pi deployment
qualification unless the native gate has passed.

## Alternatives

- Require native Pi qualification at every milestone. Rejected because no Pi is currently
  deployed and early feature phases cannot exercise representative production workloads.
- Treat ARM64 emulation or multi-architecture builds as native qualification. Rejected because
  they cannot establish board, SSD, thermal, or throttling behavior.
- Remove native Pi qualification. Rejected because it would weaken the actual deployment gate.

## Tradeoffs

Development can proceed without target hardware, and native measurements occur against a
functionally representative release. In exchange, ARM64 build success provides less confidence
than native execution, so target-specific defects may be discovered later and Phase 7 must reserve
time for remediation and requalification.

## Migration and compatibility impact

There is no relational, event-contract, projection, plugin, backup-manifest, or runtime-data
migration. Milestone language, traceability, qualification procedures, and evidence statuses
change. Existing WSL2 evidence is retained with its original measurements and reclassified only in
its milestone interpretation. No downgrade behavior changes.

## Security and operational impact

Local development remains non-public and follows the approved secret, container, and SQLite
controls. This ADR does not authorize remote access. Production storage prohibitions and backup
key controls remain unchanged. Operators must prevent Pi deployment unless the deployment
qualification record matches the candidate release and environment.

## Testing and evidence

M1 retains complete local quality, migration, amd64 Compose, compatibility, and ARM64 image-build
evidence under `/docs/evidence/m1-platform`. Native Pi evidence is retained under
`/docs/evidence/m7-recovery-compatibility/performance/pi` and is linked from the release candidate's
compatibility matrix. The Phase 7 suite must include cold/warm runs, resource and thermal capture,
storage verification, SQLite persistence/durability checks, and backup/restore rehearsal.

## Schedule, roadmap, and milestone consequences

M1 may be accepted as development-platform qualified without a Pi. Phases 2 through 6 do not add a
native Pi gate. Phase 7 owns Raspberry Pi deployment qualification, which remains a blocker only
for actual Pi deployment. Phase 8 cannot approve a Raspberry Pi production launch without the
Phase 7 native evidence. Any later change to this timing or rigor requires another accepted ADR.

## Rollback

Supersede this ADR to restore an earlier native-hardware gate. Do not delete or reinterpret raw
evidence; update the traceability matrix, milestone criteria, compatibility matrix, and affected
release schedule together.
