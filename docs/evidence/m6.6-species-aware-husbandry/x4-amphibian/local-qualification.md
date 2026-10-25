# X4 local qualification record

All databases and media are disposable fixtures. No production records, services or backups were
changed. The existing gate, 30-second test timeout, line/branch thresholds and scan policies are
unchanged. Host fixture I/O stalls were not addressed by stopping other workloads or infrastructure
changes. No repeated local full gate was launched.

## Focused results

- Contract red: 13 expected failures, 1 existing exclusion pass; initial green: 14 passed.
- Expanded pure domain/registry: 93 passed.
- Shared workflow + registration: 9 passed, default timeout, 88.15s.
- Visual/admin initial green batch: 25 passed; subsequent presentation/daily: 20 passed.
- Admin query regression: missing persisted version reproduced; final admin + PWA browser cases:
  2 passed, default timeout, 14.76s. Service-worker JavaScript executed red then green.
- Provider/archive batch: 104 passed, one existing archive self-cycle test timed out during
  database.commit. The three new qualified-ancestry tests passed in that batch.
- Actual archived old web/worker plus reconstruction: targeted 3 passed. Final compatibility
  assertions permit the normal WAL/SHM bookkeeping allowed by ADR-0045. Earlier test-fixture
  mistakes (future observation date, refusing readonly BEGIN, forbidding sidecars) were corrected;
  none were production defects. Encrypted backup initially timed out in the existing directory
  os.fsync; final complete qualification remains the hosted unchanged suite.
- Unqualified directory-link guards passed in memory without DB I/O.
- Actual v1/v2/v3 registration-history regression: v3 red while old versions passed; green 4 passed
  with existing feeding-presentation test. The original event/checksum is retained.
- Browser-discovered persisted due-reminder regression: red KeyError 'due'; final 7 agenda/history
  checks passed, including Frog/Snake and America/New_York calendar boundaries. Original facts
  and reminder rules are not changed by the display mapping.
- Exact-five-profile phase-scope regression passed after the stale four-profile expectation was
  corrected. Existing historical profile matrices remain checked independently.

## One stopped full local gate

Command: `./scripts/quality/check.sh`, unmodified. Stopped only this task's pytest process with a
graceful interrupt after repeated setup/commit timeouts. Its summary was 132 passed, 7 failed,
1 warning, 18m49s, with collection of 1,558 tests before the final presenter regression was added.
All seven failures are recorded here:

1. tests/architecture/test_phase_scope.py::test_production_capability_registry_is_closed_to_four_approved_profiles — stale exact-four expectation; fixed to exact-five and focused rerun passed.
2. tests/browser/test_product_experience.py::test_analytics_explains_estimates_and_passed_windows_in_plain_language — existing 30-second timeout.
3. tests/browser/test_product_experience.py::test_care_keeper_shell_uses_distinct_mobile_and_desktop_navigation — existing 30-second timeout.
4. tests/browser/test_product_experience.py::test_today_and_animals_are_separate_keeper_workspaces — existing 30-second timeout.
5. tests/browser/test_purchase_workflow.py::test_multiline_purchase_receives_stock_and_appears_once_in_expenses — existing 30-second timeout.
6. tests/browser/test_purchase_workflow.py::test_purchase_correction_void_and_reinstate_browser_flow[after_midnight] — existing 30-second timeout.
7. tests/browser/test_species_directory_workflow.py::test_profile_and_local_image_reads_make_zero_outbound_calls[/reference-unlinked] — existing 30-second timeout.

This run is not described as passed. Final hosted results qualify the complete amended tree.
The partial raw log is retained outside Git under output/x4-amphibian-20261025/local-quality.log.

## Browser capture corrections

A preview fixture tried 49.25mm, which the existing accepted precision contract correctly rejects;
it was corrected to 49.3mm without altering the parser. Initial network-idle navigation timed out
under local response delays; captures used actual DOM/image readiness and completed successfully.
A hidden, source-less upload-preview image is intentionally excluded from visible-image checks.
Private-image decoding was awaited before replacing the affected collection captures. An actual
persisted due-reminder rendering error found during preparation was fixed and regression-tested,
not hidden by removing its data. No production datasets or services were involved.
