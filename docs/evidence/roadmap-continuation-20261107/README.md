# Current roadmap status — November 8, 2026

**DEPLOYED AND VERIFIED:** the owner-authorized PR #34/#35 retry completed
November 8, 2026. Exact source `cf772cf8348f3eeb2ec069754b585bffd6c926cf` is live,
including the verified Plant Detail correction. See the
[November 8 retry record](production-retry-20261108.md) for exact image, recovery,
data-preservation and actual browser evidence.
**M6.6 owner acceptance and formal M7/M8 qualification remain open. M9 is a
preparation handoff; implementation has not started and public sharing is disabled.**

This is the current implementation-status supplement to the
[frozen roadmap](../../roadmap/milestones.md). Its earlier statements that X1 was
unstarted, X2–X5 were future work, and Smart Care/Bioactive remained unimplemented
have been superseded by the merged/deployed evidence below. Requirements, original
acceptance receipts and content-bound architectural approvals retain their meaning
and bytes; no unchecked requirement or Proposed ADR is silently promoted.

## Product and closeout

- **X1–X5, Smart Care, Bioactive:** integrated through normal PR #33 merge
  `71eb88c01390d3672c470c1a50a80e707233c181`, with the identical qualified source
  tree and deployed schema 27. [M6.6 closeout](m66-closeout.md) records the source,
  image and reused evidence, plus the remaining acceptance items.
- **Plant Detail correction and compatibility exporter:** PRs #34/#35 merged
  normally into `cf772cf8348f3eeb2ec069754b585bffd6c926cf`. The November 7
  attempt rolled back after an operator DNS comparison error. The separately
  authorized November 8 retry passed production acceptance: 21 authenticated
  routes, eight static/readiness checks, and Plant Detail at 1440/390/320 px with
  zero axe violations or horizontal overflow. The layout fix is live; see the
  [retry record](production-retry-20261108.md).
- **Frog content:** two version-1 guides are ready for the
  [bounded publication decision](frog-guide-publication.md). They remain unpublished.
- **M9:** the [implementation handoff](m9-handoff.md) identifies the first useful
  private album slice, required storage decision and later public-sharing boundary.

## M7/M8: completed evidence versus remaining requirements

Evidence below is reused within its original scope. The operator receipts live in
`output/combined-production-deploy-20261104/{REPORT.md,COMPLETE.json,SHA256SUMS}` in
the shared workspace, with prior X1–X5 and integrated candidate receipts linked from
[M6.6 closeout](m66-closeout.md). The later November 7 rollback and November 8
retry evidence remain separate. No migration or database restoration accompanies
this schema-27 binary update.

| Requirement | Evidence available | Still required |
| --- | --- | --- |
| Coherent encrypted backups and isolated restore | X1 normal-worker backup lease checks; current retry recovery point `741e4100-8f62-4146-9f2d-d596f9c3bc79` covers event 1,053 and all 46 attachment versions; isolated restoration passed; earlier `5a52775c-17be-4730-a6a0-b5a51de743a3` and other recovery assets remain retained | Independently retained off-device copy and independent key-recovery exercise; representative RPO 6h / RTO 60min / 20 GiB qualification |
| Upgrade and data preservation | Actual schema 25 → 26 → 27 deployment, 109 pre-existing tables preserved, event high-water 1,051 unchanged; accepted installed ARM64 migration/compatibility checks | Complete supported fresh-install/upgrade/rollback/event/projection/plugin/backup matrix and evidence accounting, including missing-plugin/newer-contract refusal |
| Security and operation | Accepted hosted gates and actual ARM64 image scan: zero **fixed** HIGH/CRITICAL findings; successful live HTTPS/PWA/worker checks and existing runbooks; both historical urllib3 alerts verified fixed | Operator incident exercise, consolidated security and owner acceptance; scan scope is not a claim of no vulnerabilities |
| Native Pi and storage | Actual native deployment, SQLite 3.40.1 migration and isolated restoration under the owner's SD-only exception | Formal representative cold/warm, CPU, memory, thermal/throttling and durability budgets; SSD/ext4 requirement remains unmet unless formally reconciled with the exception. No new SSD purchase is mandated here |
| Release evidence | Qualified source/tree/image identity, retained image and scan evidence, accepted 1,719 hosted tests for exact combined target `cf772cf8`; prior 1,710-test qualification remains historical | Retained SBOM, artifact signing/verification evidence, complete matrix, operator exercises and owner security/accessibility/performance/recovery/integrity acceptance |

Neither M7 nor M8 is recorded as complete. An actual successful deployment under
the owner's bounded exception is not the formal `Raspberry Pi deployment qualified`
designation. Same-device recovery and the formal storage qualification gap stay
visible; repeating existing backups or unchanged suites does not close them.

The November 7 read-only GitHub API refresh confirmed that
[GHSA-gh4c-6fx4-qh6g](https://github.com/Shadowgar/SnakeTracker/security/dependabot/1)
(medium) and [GHSA-vxq7-64xx-v4gw](https://github.com/Shadowgar/SnakeTracker/security/dependabot/2)
(high) were both fixed October 26. The current lock has patched urllib3 2.8.0 via
development `pip-audit → requests`; the production dependency graph and retained
image inventory contain no urllib3. GitHub's generic dependency scope labels these
alerts runtime; the graph assessment is distinct. These two historical alerts are
**not remaining blockers**. [The retained API receipt](dependency-alert-refresh.json)
supersedes their old unresolved status without rewriting historical reports.

The accepted ARM64 scan already contains package inventories for Debian, Python,
uv and uvx. It can support a future offline SBOM conversion; no extra scan or rebuild
is needed solely to recover that inventory. A standard SBOM and artifact signature
have not yet been produced or verified by this task.

The prior [msgpack GHSA-j586-36cw-2gc2](https://github.com/Shadowgar/SnakeTracker/security/dependabot/81)
(high) and [Mako GHSA-5639-2j2p-m4mx](https://github.com/Shadowgar/SnakeTracker/security/dependabot/4)
(medium) alerts were fixed on the default branch on November 7 at 07:12:43 UTC.
The November 8 read-only API refresh reports **zero open Dependabot alerts**.
The exact target lock contains msgpack 1.2.3 and Mako 1.4.2. GitHub reports both as
transitive runtime dependencies; the retained production graph is distinct:
msgpack belongs to the development audit/cache path and is absent from the actual
runtime image, while Mako is an Alembic runtime dependency. This metadata refresh
reran no scan. Its receipt is `security-alert-refresh.json` in the retry output
folder. Existing qualification retains its original scope and limitations.

The first Plant Detail PR Container gate also identified CVE-2026-109518 in a cached
amd64 apt upgrade layer (apt/libapt-pkg6.0 2.6.1). Its fresh ARM64 scan already had
2.6.2 and passed. The merged candidates require at least 2.6.2 in the
Dockerfile, invalidating the stale layer and preventing its reuse. These matching
Dockerfile/lock prerequisites allow independent required gates; no ignore rule or
weakened scan threshold was added. Those candidate checks passed before merge. The unchanged qualified image is
reused for this deployment; no scan or build is repeated.

## Implemented release-readiness improvement

The new read-only exporter emits installed package/build/runtime identity and the
existing profile, event, schema, backup and **real nine-projection** declarations:

```sh
python -B -m snaketracker.operations.release_compatibility --require-build-identity
```

It opens no application database, connects to no provider and writes only JSON to
stdout. `--require-build-identity` rejects a missing configured source SHA; a normal
development export records absent identity as unrecorded. The existing ARM64 image
qualification now retains `release-compatibility.json` with the qualified image ID
and matching source SHA, after verifying the actual installed source. There is no
new scan, job or rebuild of the already deployed image for this change.

The manifest declares five readable profiles, 84 readable event contracts, nine
projections, schema 27 mutable and older recognized metadata migration-required.
Registration writes distinguish amphibian v3 from the prior profiles' v2 identity
contracts. It explicitly leaves general writers, plugins, downgrade qualification
and acceptance unrecorded. This closes an artifact-export gap, **not the complete
M8 compatibility matrix**. Focused tests cover determinism, version boundaries,
build identity and artifact retention; required PR gates assess the new candidate.

Local verification: 40 focused exporter/profile/retention tests passed; two focused
migration/readiness tests passed with the patched frozen dependency environment;
six container-contract tests and shell/version-guard checks passed. Mako traversal
and msgpack malformed-input regressions changed from reproduced failures to safe
results, while legitimate migration-template rendering, CacheControl round trips
and streaming decode passed. Strict production dependency audit checked 34 packages
and reported no known vulnerabilities. Ruff, targeted mypy, architecture boundaries,
architecture freeze, documentation links and whitespace checks passed. The full
application suite is left to the required hosted gate, not repeated locally.

## Decisions that move the roadmap forward

1. Record the remaining physical-device, screen-reader and owner acceptance
   decisions for the deployed correction. The annotated reference plate still
   needs a separately qualified replacement if a clean photograph is wanted; the
   layout correction does not authorize replacing that content.
2. Approve or decline the exact Frog Guide publication proposal; resolve the
   remaining M6.6 content, manual accessibility and owner acceptance items.
3. Name an off-device recovery destination and independently recoverable key
   arrangement, and decide the formal disposition of the existing SD-only exception.
   Use those decisions for one bounded recovery/incident qualification, not repeated
   same-device backup creation. Retain SBOM/signing evidence at the next meaningful
   release qualification; do not regenerate the accepted image solely for paperwork.
4. Approve the M9 storage/capacity and bounded private-album scope described in the
   handoff once the relevant release/privacy prerequisites are resolved.

No merge, deployment, live migration, guide/taxonomy import, new backup, public
setting change or M9 implementation is authorized by this status supplement.
