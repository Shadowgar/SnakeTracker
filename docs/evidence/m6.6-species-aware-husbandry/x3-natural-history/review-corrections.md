# X3 final review corrections

Follow-up on October 25, 2026, to PR #25 candidate
`5306944e9e6c2ac20a3d1c8ebc288e9a47691c49`.

The first hosted [Quality run](https://github.com/Shadowgar/SnakeTracker/actions/runs/39182973075)
finished with 1,509 passes and one failure: the Directory browser workflow still asserted the
previous missing-guide wording. The assertion now requires the owner's exact message:
“No reviewed captive-care guide is available yet.” No timeout or gate threshold changed.
Container and GitGuardian passed that original candidate.

The completed hosted review found two substantive issues. Both were reproduced before fixing:

- A Natural History binding to guide version 1 disappeared after importing version 2. Animal
  and Directory views now load each binding's recorded immutable version, retaining its hash
  guard. Only bindings to the currently displayed guide suppress duplicate rows there; an old
  claim ID cannot hide a changed claim in a newer guide. The integration regression verifies
  both views, retention of the original payload, and visibility of the new guide claim.
- Equivalent biological values combined source references under only the first qualification.
  Each originating source, reference and qualification is now retained together and rendered
  together in the evidence disclosure. Equivalent values still display once and sources reached
  through several services still count by actual origin. The regression verifies both distinct
  qualifications and their reference associations.

The red run had two expected failures and three passes. The focused post-fix run passed all
46 tests across the Natural History unit/web suites and the complete Species Directory browser
workflow module; see [review-regressions.log](review-regressions.log). Ruff, formatting, mypy
(164 source files), architecture, protected-document freeze, documentation links and diff
integrity also passed. Full qualification uses fresh hosted checks on the follow-up commit.

The captured Boa fixture has descriptive sections, no biological claims or guide bindings.
Its rendered layout and content are unaffected by these corrections; the existing desktop,
390px and 320px screenshots and browser measurements remain applicable. All databases used for
regressions are temporary fixtures. No production data, migration/import, service or deployment
was touched; main and PR #21 are unchanged. Production source-rights qualification remains a
separate prerequisite. This is development evidence, not a production release record.
