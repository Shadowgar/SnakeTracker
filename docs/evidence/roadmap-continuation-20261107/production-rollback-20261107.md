# November 7 combined-release deployment — verified rollback

**Outcome: ROLLED BACK — PRODUCTION HEALTHY.** This receipt records an unsuccessful
deployment attempt and verified binary rollback. The Plant Detail correction is
merged and qualified but is not live. No further deployment attempt was made.

| Identity | Value |
| --- | --- |
| Attempted source, containing normal PR #34/#35 merges | `cf772cf8348f3eeb2ec069754b585bffd6c926cf` |
| Qualified source tree | `a07c5083b657b5bb7329e52f9b7592223c0bf804` |
| Qualified ARM64 image | `sha256:1f9ea52a9ce535f50a2d5e4795d5f62b13c0dc4f297ac58191d6bbf1611cdc39` |
| Qualified GitHub artifact | `13565316198` |
| Restored and current production source | `8ebffb6287742f3aef5ad985ef99cf1036a3c623` |
| Restored and current production image | `sha256:ab0ddd40f4d54db63b6945146e163a0431670a62e8a112c5b06a675c1c5818f4` |
| Unchanged schema | `0027_bioactive_plant_care` (27) |

The controlled attempt began at `2026-11-07T10:13:03.023724+00:00`. Candidate
application containers started while the proxy remained closed. An operator
runtime-configuration comparison treated empty DNS lists (`[]`) and absent lists
(`null`) as different for `Dns`, `DnsOptions` and `DnsSearch`. That representation
difference triggered a configuration-drift gate even though there was no effective
runtime configuration change. The same omission behavior occurred with the old
binary during rollback. This was an operator verification defect; the attempt did
not establish a candidate application failure or successful live functional checks.

The previous binary was restored without restoring or replacing the production
database. Web, worker and nginx were healthy by
`2026-11-07T10:15:48.404552+00:00` (05:15:48 America/New_York). The measured
interruption to readiness was 158.439 seconds. Free storage at that verification
was 7,778,676,736 bytes; this is a dated observation, not a future capacity promise.

The preserved-state comparison passed across all compared business tables, event
records and retained attachment versions. Its explicit exclusions were the
transient backup lease and the derived reminder `calculated_at` timestamp. Backup
archive inventories were unchanged. The private receipts retain exact comparison
counts and attachment hashes. No schema migration, content import/publication,
authentication session or public-sharing change occurred. No later live records
were replaced by an older snapshot.

The primary machine receipt is
`output/combined-production-deploy-20261107/ROLLBACK-VERIFIED.json` in the shared
operator workspace. Supporting private evidence includes `cutover-receipt.json`,
`production-before-cutover.json`, `production-after-rollback.json` and
`rollback-state-diagnosis.json` in that directory. The preceding verified recovery
qualification is retained under `output/storage-recovery-20261107/`. Those records
remain private; this tracked summary includes no credentials or household records.

The supported release publisher subsequently appended one verified `rolled_back`
Updates entry for the restored source and actual restoration time, preserving both
previous entries. `rollback-ledger-publication.json` retains that receipt. No
successful-deployment entry was published for the candidate.

The owner's failure procedure stopped further deployment operations. A new owner
decision is required before another attempt. First correct and verify the operator
comparison of equivalent absent/empty DNS lists while preserving all meaningful
configuration checks, then refresh the required production safety gates. Retain
the exact qualified source/image/artifact and the known-good rollback image; this
incident does not call for rebuilding or rescanning unchanged application source.

M6.6 owner acceptance, formal M7/M8 qualification, content-publication decisions
and the M9 preparation boundary remain unchanged. This receipt authorizes no
deployment retry, content publication or M9 implementation.
