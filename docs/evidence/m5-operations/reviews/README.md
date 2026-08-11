# M5 Review Disposition

Status: **Final substantive review complete; owner accepted**

Source revision: `de39d1d17448d0016a0b83e13bcf301c23cc390b`.

Local review concentrated on transaction atomicity, stream versions, inventory compensation,
tenant authorization, reminder effective history, independent pipeline deduplication, lease
fencing, dead-letter behavior, and the external-effect uncertain crash window. The owner's first
M5 UX review classified the standalone reminder-management flow as a required correction. The
keeper workflow was moved to animal-profile care schedules and an overdue/due-today/upcoming
agenda, with the established reminder engine and delivery pipeline preserved. Required corrections
and coverage gaps were implemented test-first before requalification. The owner accepted the
result on August 11, 2026.

The full gate reports only two non-blocking upstream observations: Starlette's TestClient adapter
warns about its future `httpx2` transition, and an intermittent SQLAlchemy cleanup ResourceWarning
may appear during lifecycle tests. Neither changes runtime state or a test result.

CodeRabbit completed a substantive review on PR #6. GitHub Copilot review was requested but was not
available for this repository. Quality and Container/Trivy were green at the reviewed branch head;
GitGuardian had no current-head check run to classify. Owner acceptance is recorded separately;
merge remains gated on the required hosted checks.

## Finding disposition

| Classification | Finding | Disposition and evidence |
| --- | --- | --- |
| Required correction | Corrected inventory-linked feeding could not be compensated when the original feeding was later voided. | Replacement consumption remains keyed to the original feeding event; correction then void is covered by `test_stock_linked_feeding_correction_replaces_consumption_atomically`. |
| Required correction | Cross-item reversal lookup lacked the inventory stream identifier. | Allocation and link updates now require household, item, and consumption event; a forged cross-item reversal fails closed. |
| Required correction | Reconciliation after an uncertain final attempt produced an unclaimable retry. | Reconciliation safely restores one attempt of retry headroom; the final-attempt recovery test proves a subsequent fenced claim. |
| Required correction | Phase 5 downgrade could violate the older outbox state constraint. | Downgrade explicitly normalizes later states to `pending`; the migration test covers a `handed_off` row. |
| Required correction | Reminder GET requests performed fact and intent writes. | `/reminders` now renders the read-only agenda; the browser test proves fact and intent counts remain unchanged. |
| Required correction | One worker duty failure terminated all duties and reminder recalculation ran every poll. | Duties have independent exception boundaries and the reminder sweep has a one-minute cadence, both covered by worker lifecycle tests. |
| Required correction | Feeding correction treated explicit zero inventory quantity as absent and changed legacy idempotency hashes when omitted. | `None` and zero are distinct; omitted optional data is excluded from the hash, with zero validation and legacy retry coverage. |
| Required correction | Reminder parsing, local-day status, stale inventory submissions, and enabled blank intervals did not fail consistently. | Typed subject references, service-level timestamp errors, household-local date comparison, `422` conflict handling, and required interval validation are covered by integration/browser tests. |
| Required correction | Capability-gated actions were rendered without corresponding capability checks. | Home operational links and the expense-create action now follow the current principal capabilities. |
| Required correction | Operator job resolution was not explicitly household-scoped. | Resolution and dead-letter reads now require household identity; a cross-household resolution test proves no state transition occurs. |
| Required correction | External-effect crash qualification depended on a production worker test switch, and transient exhaustion lacked worker-level proof. | The crash is injected by a test-only provider wrapper, production has no crash switch, and five transient attempts are proven to dead-letter. |
| Required correction | Recipient isolation was tested only with a nonexistent user. | Notification intent tests now include an active owner belonging to a different household and prove no intent or outbox write. |
| Required correction | CI used a probabilistic plaintext-substring assertion against randomized encrypted bytes. | Backup verification now deterministically checks the encrypted framing, absence of the SQLite plaintext header, ciphertext inequality, authenticated restore, and wrong-key rejection. |
| Required correction | Evidence reproduction and labels were ambiguous. | Migration commands fail fast, Compose waits for health, screenshot inventory and compatibility labels are explicit, and M6 no longer duplicates M5 due/overdue agenda scope. |
| False positive | None. | No substantive reviewer finding was rejected as a false positive. |
| Valid but deferred | Starlette TestClient `httpx2` deprecation warning. | Upstream adapter transition remains non-blocking and is retained as a warning; runtime application behavior is unaffected. |

No other substantive finding was deferred. Cosmetic suggestions that did not affect correctness were
applied where they improved evidence accuracy and were otherwise left out of the runtime change.

The remaining CodeRabbit nitpicks were classified as valid but deferred maintenance: table-driven
compatibility/subject-validation refactors, shared literal types, protocol typing refinements,
test-fixture conversion, query-count micro-optimizations, and test-only readability cleanups. They
do not change an M5 invariant, security boundary, or release result. UI suggestions that would
reopen the already accepted M5 reminder/expense experience are likewise deferred to the relevant
future product phase. CI and dependency audit reported no findings; Copilot and current-head
GitGuardian review were unavailable rather than silently treated as passing reviews.
