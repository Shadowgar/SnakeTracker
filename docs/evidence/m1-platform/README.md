# M1 Platform Evidence

- Execution date: 2026-08-04
- Implementation revision: `da061911a7956892adbf8b5a1414e7407ce05b2a`
- Architecture baseline: `bb3ab394a1487943424dad6d7544995c71156c98`
- Branch: `phase1/platform-foundation`
- Operator: Codex automation in the local `rocco` workspace
- Reviewer: Pending owner review

## Outcome

Phase 1 implementation is complete, but M1 is **not yet fully qualified**. All local mandatory
software checks pass. Native Raspberry Pi 5 execution and proof that the candidate Pi database
path is on the pinned SSD remain open; no Pi host was available in this workspace. The WSL2
development run also exceeded the idle-CPU target and is retained as a failed, non-qualifying
measurement rather than being promoted or discarded.

| M1 exit criterion | Result | Evidence |
|---|---|---|
| Locked Python environment reproduces | Pass | [quality gate](tests/quality-gate.log) |
| amd64 and arm64 images build; native Pi smoke retained | Partial | [container evidence](containers/README.md); native Pi smoke missing |
| SQLite profile on qualified local SSD | Partial | [SQLite evidence](operations/sqlite-profile.md); profile passes, candidate Pi SSD unverified |
| Unsupported compatibility fails safely | Pass | [test mapping](tests/README.md) |
| Local and CI-adapter quality gates exist and pass validation | Pass locally | [quality gate](tests/quality-gate.log), [actionlint](tests/actionlint.log) |
| Hardened local Compose topology starts, restarts, preserves its schema, and stops cleanly | Pass locally | [development results](performance/development-host-warm/results.json) |
| Startup and idle targets pass on pinned Pi environment | Not run | [native Pi status](performance/native-pi5-status.md) |
| Structured reproducible evidence and review | Pending review | [manifest](evidence-manifest.json), [review](approvals/m1-review.md) |

The development-host run passed readiness, restart, memory, persistence, filesystem, and SQLite
contract checks. Its idle CPU p95 was 14.39%, above the 5% target, so its overall numerical result
is `FAIL`. It is expressly non-qualifying and cannot substitute for native Pi evidence.

## Inventory

- `evidence-manifest.json` — requirement and exit-criterion status with reproduction metadata.
- `checksums.sha256` — SHA-256 integrity values for raw non-harness evidence.
- `environment/` — pinned Python/uv bootstrap command and raw output.
- `tests/` — full quality output, workflow syntax validation, and acceptance-test mapping.
- `operations/` — Alembic lifecycle and SQLite pragma/filesystem evidence.
- `containers/` — amd64, arm64, hardening, and vulnerability-scan evidence.
- `performance/development-host-warm/` — raw non-qualifying harness output.
- `performance/native-pi5-status.md` — exact missing qualification procedure.
- `approvals/m1-review.md` — owner review record, intentionally pending.
