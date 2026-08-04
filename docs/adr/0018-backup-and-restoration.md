# ADR-0018: Use Leased, Encrypted, Verified Backups

Status: Accepted
Acceptance date: 2026-08-04

## Context
Self-hosting makes data loss and operator error primary risks.

## Decision
The worker is the sole initiator and holds a durable global lease. Complete the SQLite copy first, derive attachment references from that copy, copy exact immutable versions, encrypt with independently managed keys, verify, retain off-device, and test restoration. Preserve password hashes; omit/invalidate sessions and temporary credentials; never include plaintext secrets or decryption keys.

## Alternatives
Filesystem snapshots without manifests or ad hoc manual copies.

## Tradeoffs
Backup operations require storage, key operations, leases, and recurring drills.

## Future impact
Manifest versions and compatibility appear in every release matrix.
