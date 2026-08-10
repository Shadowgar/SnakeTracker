# M4 Final Review Disposition

Result: **Required corrections complete; owner acceptance pending**

The final internal review and CodeRabbit review were evaluated against the implemented Phase 4
contracts. Required corrections now cover effective correction-chain fallback, occurred-time
history ordering, complete validation-error context, restrictive secret setup, attachment
crash-window cleanup and lifecycle serialization, pre-decode image limits, backup connection
cleanup, invalid schedule guards, saved schedule rendering, periodic lease renewal, stable worker
lease identity, atomic duplicate backup requests, manifest-kind validation, production restore
filesystem policy, enclosure length validation, fail-closed animal status replay, and shed
completion invariants.

The reported missing schedule idempotency field was a false positive: the schedule route does not
consume `_form_idempotency_key`; its CSRF-protected upsert is verified by the browser test. Reports
that evidence PNGs were missing were also false positives caused by the review's binary-file path
filter; the files are tracked and their links pass repository validation.

Valid non-blocking maintainability suggestions—test-fixture deduplication, helper extraction,
stylistic cleanup, and broader docstring coverage—are deferred because they do not change M4
behavior or safety. The owner-review correction verifies that assignment history names the actual
target enclosure and that current occupancy follows the latest assignment. Projection-aware
voiding of `animal.enclosure_assigned` remains unsupported: the application service rejects it and
the keeper UI now explicitly withholds Void and Reinstate controls for that contract. Enabling the
operation requires an explicit effective-current-enclosure design rather than silently changing
the accepted event contract. The single-worker local Compose
topology is qualified; stronger multi-worker SQLite lease-claim serialization is deferred with
remote/production hardening.

The final incremental CodeRabbit review raised two required corrections. The attachment-staging
idempotency lookup is now inside the filesystem lifecycle lock with deterministic winner recovery,
and backup heartbeat startup failures now pass through durable run/request failure handling. Both
findings have focused regression tests and are included in the full gate.

GitHub Quality, Container, and GitGuardian checks are required on the final evidence commit. The
external CodeRabbit incremental rerun completed successfully after reviewing the final correction
files.
