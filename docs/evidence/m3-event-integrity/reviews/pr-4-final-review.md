# PR #4 final review disposition

Date: August 7, 2026

Scope: CodeRabbit, GitHub Copilot, GitHub Actions, GitGuardian, dependency audit, container
scanning, and the requested long-stream snapshot verification. M3 remains
implementation-qualified with owner acceptance pending.

## Required corrections completed

| Source | Finding | Disposition and evidence |
|---|---|---|
| Copilot | The envelope payload union was coupled to household/control contracts. | Replaced by a contract-owned structural payload type with dataclass enforcement; `test_event_envelope_accepts_contract_owned_payload_without_platform_union`. |
| Copilot, CodeRabbit | Qualification workers mutated shared result state. | Workers now return immutable results and the caller aggregates sequentially. |
| CodeRabbit | Evidence revisions and reproduction command were inconsistent. | Both revision fields now use full `75b6804f1b7dbec93a17b74651f17953510eaac9`; the command names the built image and supplies the required bind mount, entry point, database, and output directory. |
| CodeRabbit | Projection generations were not relationally bound to their owning projection. | Added composite ownership foreign keys for active generations and checkpoints; migration upgrade/downgrade/re-upgrade and foreign-key checks pass. |
| CodeRabbit | Malformed snapshot JSON escaped quarantine. | Deserialization failures are quarantined with `snapshot_deserialization_invalid`, older snapshots remain eligible, and authoritative replay returns complete state. |
| CodeRabbit | One cleanup call removed only one failed generation per projection. | Cleanup enumerates every failed generation; two-failure/one-cleanup integration test passes. The duplicate test-only comment is covered by the same correction. |
| CodeRabbit | Projection replay omitted household and stream identity. | `ProjectionEvent` now carries household ID, stream type, and stream ID; generated rows prove tenant/stream identity. |
| CodeRabbit | `GenerationLayout.generation_id` was unrelated random data. | Removed the unused ambiguous field; component names remain derived only from registered definitions and actual generation IDs. |
| CodeRabbit | Correction age used truncated days and accepted predated controls. | Full `timedelta` comparison now rejects negative age and `limit + 1 microsecond`; exact boundaries remain deterministic. |
| CodeRabbit | Compensation was not bound to an allowed contract and target. | Registry capabilities now allow-list compensation contracts; policy validates target event, household, correlation, and causation. |
| CodeRabbit | Void/reinstate did not apply to replacement chains. | Effective-state reduction resolves the complete correction chain and fails on cycles; void/reinstate chain tests pass. |
| CodeRabbit | Snapshot retention policy was not enforced. | Snapshot saves transactionally retain the newest two active snapshots while preserving quarantined diagnostic rows. |
| CodeRabbit | Malformed `ZoneInfo` keys raised raw `ValueError`. | Both conversion paths translate `ValueError` and `ZoneInfoNotFoundError` to fail-closed `EventValidationError`. |
| CodeRabbit | Qualification SQLite handle stayed open. | The raw connection now uses `contextlib.closing` plus its transaction context. |
| CodeRabbit | Bulk qualification duplicated the event checksum algorithm. | Bulk rows call the same `canonical_event_checksum` used by production `event_checksum`. |
| CodeRabbit | `actual_events` copied the target value. | The harness queries the persisted count and adds `event_count_matches_target` to the pass/fail targets. |
| CodeRabbit | Empty latency samples crashed instead of recording failure. | Empty samples produce deterministic infinite p95, so the target fails without losing evidence. |
| Requested verification | Normal loading did not prove snapshot-tail replay on a 10,000-event stream. | `AggregateLoader` validates snapshot state/boundary and stream head, begins after snapshot version 9,900, and replays exactly 100 events. Thirty Docker samples all reported 100; p95 was 15.76 ms. Corrupt, malformed, incompatible, and invalid-boundary tests prove quarantine and complete authoritative fallback. |

## False positives

| Source | Finding | Evidence |
|---|---|---|
| CodeRabbit | The SQLite driver must be switched to autocommit before `BEGIN IMMEDIATE`. | Append and multi-stream append issue `BEGIN IMMEDIATE` as the first statement on a fresh connection. Concurrent-writer and rollback integration tests pass under the approved engine profile. Switching the shared engine to autocommit would weaken other `engine.begin()` transactions. |
| CodeRabbit | Expired idempotency rows should stop matching retries. | ADR-0012 defines expiry as bounded-cleanup eligibility after retaining completed records for at least 90 days. Until cleanup, an equivalent retry must continue returning the stored result; ignoring expired rows would instead collide with the permanent uniqueness constraint. |
| Copilot | Suspended membership or disabled user rows are invalid event subjects. | ADR-0031 and the domain catalog require registered type, entity existence, same-household ownership, and current actor permission. Historical subjects remain existing household-owned entities after access is disabled. The actor is independently required to have an active membership. |

## Valid but deferred

| Finding | Reason |
|---|---|
| GitHub Actions Node 20/punycode/url.parse deprecation warnings | The warnings originate in pinned third-party actions, not runtime application code. They are non-blocking while GitHub forces Node 24; update pins when upstream releases compatible actions. |
| Starlette TestClient `httpx2` migration warning | The current pinned FastAPI/Starlette stack remains functional and all browser/security tests pass. Track with the next dependency qualification rather than changing the HTTP test stack during M3 review. |
| Trivy 0.70 update notice | The pinned scanner completed successfully with zero HIGH/CRITICAL fixed vulnerabilities. Scanner-version maintenance is separate from an application finding. |

## Checks with no substantive findings

- GitGuardian: passed; no secret finding.
- Trivy container scan: zero HIGH/CRITICAL fixed vulnerabilities at the reviewed head.
- `pip-audit --strict`: zero known dependency vulnerabilities.
- GitHub Quality and Container workflows were green on the pre-correction head and must rerun on
  the final pushed head.

## Review conclusion

All substantive findings are corrected, explicitly deferred, or rejected with contract and test
evidence. No Phase 4 contract, animal feature, public event API, delivery worker, durable job,
notification, or external side effect was introduced.
