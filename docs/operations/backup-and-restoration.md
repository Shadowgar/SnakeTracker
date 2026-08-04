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
