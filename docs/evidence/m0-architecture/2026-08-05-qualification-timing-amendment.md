# Architecture Amendment Evidence: Qualification Timing

- Decision: ADR-0036
- Acceptance date: 2026-08-05
- Authority: SnakeTracker owner instruction in the Phase 1 review
- Baseline commit: `bb3ab394a1487943424dad6d7544995c71156c98`
- Amendment branch: `phase1/platform-foundation`
- Reviewer: Owner review pending on PR #2

## Approved change

The owner directed that laptop Docker development continue through functional completion and that
native Raspberry Pi qualification move from M1/intermediate phases to Phase 7 or immediate
pre-deployment. The amendment creates separate `M1 development-platform qualified` and
`Raspberry Pi deployment qualified` statuses. It preserves all native Pi, SSD/ext4, cold/warm,
CPU/memory, thermal/throttling, SQLite durability/persistence, and backup/restoration requirements
before actual Pi deployment.

## Consequence review

- Data, relational schema, event contracts, upcasters, projections, plugins, and backup manifests:
  no compatibility or migration change.
- Security: no remote-access authorization and no weakened deployment storage controls.
- Schedule: no physical Pi is required in Phases 1 through 6; Phase 7 reserves native remediation
  and qualification time.
- Evidence: existing WSL2 measurements remain immutable non-production development evidence;
  native evidence moves to `/docs/evidence/m7-recovery-compatibility/performance/pi`.
- Rollback: supersede ADR-0036 and restore the earlier milestone gate without deleting raw
  evidence.

## Reproduction

From the repository root, run:

```sh
make check
git diff --check
```

PR #2 records the remote Quality and Container results for the amendment commit.

## Local verification result

- Executed: 2026-08-05T06:27:18Z
- Command: `make check`
- Result: pass
- Formatting/lint: pass (`132 files already formatted`; Ruff clean)
- Architecture freeze: pass (`36 accepted ADRs`)
- Documentation links: pass (`77 files checked`)
- Typing: pass (`24 source files`)
- Tests: pass (`94 passed`)
- Coverage: pass (`99.29%` lines; `98.78%` branches)
- Dependency audit: pass (no known vulnerabilities)
- Compose configuration and whitespace checks: pass as part of the command's zero exit status
