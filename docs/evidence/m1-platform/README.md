# M1 Platform Evidence

- Execution date: 2026-08-04
- Implementation revision: `419b8949e9ca60bce18b5b69b6730fce2e546b43`
- Architecture baseline: `bb3ab394a1487943424dad6d7544995c71156c98`
- Branch: `phase1/platform-foundation`
- Operator: Codex automation in the local `rocco` workspace
- Reviewer: Pending owner review

## Outcome

Phase 1 implementation is complete and the evidence supports **M1 development-platform
qualified**, pending owner acceptance. All mandatory local software, amd64 Compose, SQLite
development-profile, migration, and ARM64 image-build checks pass. Under ADR-0036, native
Raspberry Pi 5, SSD/ext4, thermal, and production-performance qualification is a separate Phase
7/pre-deployment gate and does not block M1 or Phases 2 through 6.

The WSL2 development measurement is retained as non-production evidence. It exceeded the
development idle-CPU target, which remains an optimization observation; it is not a failed M1
qualification and is not promoted as evidence of native Pi behavior.

| M1 exit criterion | Result | Evidence |
|---|---|---|
| Locked Python environment reproduces | Pass | [quality gate](tests/quality-gate.log) |
| amd64 Compose executes and amd64/arm64 images build | Pass | [container evidence](containers/README.md) |
| SQLite development profile on supported local filesystem | Pass | [SQLite evidence](operations/sqlite-profile.md); Pi SSD/ext4 is a deferred deployment gate |
| Unsupported compatibility fails safely | Pass | [test mapping](tests/README.md) |
| Local and CI-adapter quality gates exist and pass validation | Pass locally and remotely | [quality gate](tests/quality-gate.log), [GitHub Actions](tests/github-actions.md) |
| Hardened local Compose topology starts, restarts, preserves its schema, and stops cleanly | Pass locally | [development results](performance/development-host-warm/results.json) |
| Development startup/resource measurements retained | Pass with optimization observation | [development results](performance/development-host-warm/results.json) |
| Native Pi deployment qualification | Deferred, not an M1 criterion | [native Pi status](performance/native-pi5-status.md) |
| Structured reproducible evidence and review | Pending review | [manifest](evidence-manifest.json), [review](approvals/m1-review.md) |

The development-host run passed readiness, restart, memory, persistence, filesystem, and SQLite
contract checks. Its idle CPU p95 was 14.39%, above the 5% development target, so the original
harness summary correctly records a numerical `FAIL`. ADR-0036 preserves that raw result but
classifies it as a non-production optimization observation rather than an M1 blocker. It cannot
substitute for future native Pi evidence.

## Inventory

- `evidence-manifest.json` — requirement and exit-criterion status with reproduction metadata.
- `checksums.sha256` — SHA-256 integrity values for raw non-harness evidence.
- `environment/` — pinned Python/uv bootstrap command and raw output.
- `tests/` — full quality output, workflow syntax validation, and acceptance-test mapping.
- `operations/` — Alembic lifecycle and SQLite pragma/filesystem evidence.
- `containers/` — amd64, arm64, hardening, and vulnerability-scan evidence.
- `performance/development-host-warm/` — raw non-qualifying harness output.
- `performance/native-pi5-status.md` — deferred deployment qualification status and procedure.
- `approvals/m1-review.md` — owner review record, intentionally pending.
