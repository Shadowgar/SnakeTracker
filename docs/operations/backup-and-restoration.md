# Backup and Restoration Runbook

## Policy

The worker is the sole backup initiator. UI and CLI actions enqueue requests. A global durable lease prevents overlap. Target schedule is every six hours with seven daily, four weekly, and twelve monthly recovery points, including at least one independently stored copy.

Target RPO is six hours. Qualified RTO is 60 minutes for the representative database and 20 GiB attachment set.

## Create and verify a backup

1. Confirm no active backup lease; acquire lease with owner, token, heartbeat, expiry, and operation ID.
2. Confirm storage headroom and key availability without logging key material.
3. Produce a consistent SQLite copy using the online backup mechanism.
4. Open the completed copy read-only and capture its schema, event high-water position, compatibility data, and finalized attachment references.
5. Generate the attachment manifest from the completed copy.
6. Copy/deduplicate those immutable attachment versions.
7. Exclude sessions, CSRF state, reset/invitation secrets, staged uploads, temporary credentials, and transient leases; preserve required password hashes.
8. Write versioned manifest and checksums.
9. Encrypt using an independently managed key; never include plaintext secrets or decryption keys.
10. Verify database integrity, manifest, ciphertext readability, checksums, referenced attachments, and retention placement.
11. Record administrative health and security audit outcome; release lease.

If the worker crashes, a new worker may take an expired lease only after checking for a complete final manifest. Partial sets remain quarantined and are never advertised as recovery points.

## Restore

1. Obtain authorization and record the recovery objective.
2. Enter maintenance mode; reject ordinary traffic and stop workers.
3. Preserve the current data directories for rollback.
4. Retrieve backup and independent decryption key through separate controls.
5. Verify manifest version, application compatibility, signatures/checksums, and key identity.
6. Restore into a new directory, never over the active dataset.
7. Run SQLite integrity and foreign-key checks.
8. Scan relational schema, event contracts, upcasters, plugin handlers, and backup-manifest compatibility.
9. Verify every referenced immutable attachment.
10. Validate or rebuild projections, especially authorization.
11. Invalidate restored sessions and temporary credentials.
12. Start isolated services and run smoke tests.
13. Atomically activate restored storage.
14. Exit maintenance mode only after owner/account access and health checks pass.
15. Retain rollback data until the recovery acceptance window ends.

## Testing and evidence

Automatically restore monthly into isolation and conduct an operator-led drill quarterly. Evidence records backup ID, high-water position, manifest version, key version (not key), durations, bytes, checks, failures, restored smoke-test results, and responsible operator.

## Extension release gates

These are future release gates under the
[controlling plan](../plans/2026-10-01-extensible-animal-and-species-platform.md), not backup changes
made by the Pre-X1 documentation task. The
[private recovery qualification](../evidence/m6.6-species-aware-husbandry/b-corrections/backup-completeness/README.md)
proves finalized keeper-attachment completeness for that recovery point. It does not establish
ordinary worker reliability under the documented 16 MiB temporary-space constraint.

Before X1 release acceptance, qualify the ordinary production-equivalent backup/verification path
with intended runtime constraints. If scratch space blocks completion, make the smallest appropriate
operational correction and qualify that path. Private larger scratch alone does not close this gate.
Do not automatically redesign streaming backup.

Before production-sized X2 taxonomy import, measure database/generation/index size, WAL and temporary-
space high water; backup/restore memory, duration, compatibility/replay and effect on normal duties.
Use these measurements to decide whether streaming redesign is necessary. Required backup coverage
includes permanent catalog/mappings, durable overlay and retained labels, existing guide versions/
sources/claims, reference-media metadata/provenance and, after X3, source associations, content
versions and publication/withdrawal selections.

Keeper-owned attachments remain mandatory recovery content. Optional cached species-reference bytes
may be reacquirable only under an accepted recovery contract; durable media metadata/provenance remain
required. Missing cached bytes use an existing keeper photo or eligible bundled/group fallback while
local taxonomy/text remain available. Ordinary page/image reads never reacquire or hotlink media.
This documentation does not change the currently accepted backup format or exclusions.

Application rollback requires an actual older binary compatible with schema, event versions,
embedded identities, projection requirements and runtime formats, even without Alembic. Taxonomy
rollback changes the active reference/search pointer while preserving household/catalog/overlay/X3/
guide state. Disaster recovery restores a verified historical backup under explicit authorization
with a stated RPO and accepted post-backup loss. These are separate operations; pointer rollback is
not a restore of household data. Existing-storage startup must complete the future read-only
compatibility preflight before mutable initialization or replay; see
[ADR-0045](../adr/0045-extensible-animal-capability-evolution.md#supported-profile-release-manifest-and-startup).
