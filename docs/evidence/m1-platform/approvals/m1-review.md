# M1 Owner Review

- Implementation revision: `419b8949e9ca60bce18b5b69b6730fce2e546b43`
- Evidence commit: to be recorded after commit
- Review status: **Pending**
- Reviewer: Pending owner assignment
- Approval date: Pending

## Open release blockers

- Native Raspberry Pi 5 cold-cache and warm-cache qualification has not run.
- The Pi database path has not yet been proven to use the pinned local SSD/ext4 configuration.

The non-qualifying WSL2 run recorded idle CPU p95 of 14.39%, above the 5% target. This does not
replace the required Pi measurement, but it remains an operational risk to investigate if the
native Pi run also misses the target.

The owner should not approve M1 or merge the branch until the required native Pi evidence is attached and reviewed, or an accepted ADR/governance decision explicitly changes the M1 gate.
