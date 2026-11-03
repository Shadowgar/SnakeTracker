# Smart Care Setup candidate qualification

Source revision: `a10bbbda0325504b882d85cb88e9afc1126fab74`, on X5 `5e0e3f3ffeefd801b5345b6a13b2be139a9eef66`. Development evidence dated November 3, 2026. No production availability or milestone acceptance is asserted.

Keepers can open optional Smart care setup from Animal Care, compare applicable reviewed feeding sources, explicitly select context, edit a schedule, review its exact effect and confirm. Missing guidance retains manual setup across all five registered animal groups. Existing schedules remain authoritative until explicit replacement. The flow uses existing reminders and effective care history, including corrections and voids. Guidance never enables unsupported actions or infers life stage.

## Executed checks

- 63 focused Python tests passed: `tests/browser/test_smart_care.py`, `tests/unit/test_smart_care.py`, `tests/integration/test_reminders.py`, `tests/browser/test_operational_workflows.py`. These include exact retry, altered payload rejection, concurrent-context staleness, session/household/role/CSRF isolation, source conflicts and support, legacy rules, notification deduplication and updated due state. Run with `TMPDIR=/dev/shm/carekeeper-roadmap-tests uv run pytest <paths> -q --tb=short`.
- Ruff formatting and lint passed for `src tests`; mypy passed for 165 source files.
- Actual Chromium: Care → suggestions → selected juvenile source → edit → preview → confirm → Today/Calendar/reminders → record accepted feeding → Care and Today due state advanced. Six representative captures at 390px, 320px and 1440px are in `screenshots/`.
- Every captured main region passed axe WCAG 2 A/AA and 2.1 AA checks and viewport overflow checks. No browser page errors or external requests occurred. See `browser-results.json`.

The browser run uses a newly created fictional fixture at `/tmp/carekeeper-x5-browser-smart-care-final-20261103`, with the existing licensed, locally cached amphibian photographs. No live database, service or provider is used. The exact commands are:

```sh
PYTHONPATH=. uv run python scripts/qualification/x5_browser_fixture.py \
  --data-dir /tmp/carekeeper-x5-browser-smart-care-final-20261103 \
  --media-dir /tmp/carekeeper-x5-research --port 8122
CARE_FIXTURE=/tmp/carekeeper-x5-browser-smart-care-final-20261103 \
CARE_PLAYWRIGHT=/path/to/playwright CARE_AXE=/path/to/axe.min.js \
node scripts/qualification/smart_care_browser_review.js
```

A fresh fixture directory is required for another run. The script blocks external browser requests and asserts the fictional manifest and loopback origin before writes. Earlier development exposed and fixed mobile checkbox overflow; final captures verify the correction. Earlier harness selector errors are not counted as passes.

## Review boundaries

Only reviewed feeding interval/frequency claims currently map to guided choices. Other supported tasks use manual entry. Conflicting, textual, range or non-whole-day advice requires keeper choice or entry. Skip/decline are explicitly visit-only. No new schema, reference content, taxonomy import or Natural History enrichment is added by this tranche.

Physical-device and screen-reader acceptance remain owner review items. Hosted required gates are recorded against the submitted PR head, separately from these source-revision results. Prior X5 source, migration, actual SQLite and recovery evidence is reused only for unchanged X5 components. Source publication/import prerequisites remain separate from this draft development candidate. Release notes are prepared in `whats-new-draft.md`; no release-ledger entry is published.

## Review remediation and final source checks

Final source `fa52d569e9f6e1169a6997317dcc26e397e95113` incorporates bounded independent-review fixes after the original UI receipt. Existing repeated-hour due dates retain their exact signed instant; final review displays nonzero seconds/fractions and the repeated-hour offset. Forms serialize browser-valid millisecond values while retaining full timestamp precision separately. Actual Chromium145 edit → Edit again → preview → confirm passed both `.123456` / UTC−05:00 and `.123000` / UTC−04:00 fixtures, with `.123` in real input/FormData and the original exact instant retained in SQLite; see `timestamp-browser-results.json`. Wrong-purpose signed tokens now return a controlled form error.

Signed previews also retain source-stream expectations, checked within the existing event-store write transaction after completed-receipt lookup and before writes. Care recorded between preview validation and append now rejects confirmation without a schedule event/receipt. Guarded unchanged schedules retain a receipt without manufacturing an event; exact replay still succeeds after later care. Existing commands without guards preserve their historical canonical hashes. No event contract or schema changes are required.

Final focused command: `TMPDIR=/dev/shm/carekeeper-roadmap-tests uv run pytest tests/browser/test_smart_care.py tests/integration/test_atomic_append.py tests/integration/test_reminders.py -q --tb=short` — **68 passed** in68.36s. Ruff formatting/lint, mypy (165 source files) and diff checks passed. Earlier 63-test and screenshot receipts remain attributed to their original source; no full local suite was duplicated. The initial submitted742a79b hosted gate passed1,637 tests, lines94.84% / branches86.19%, dependency audit and Container; final submitted-head hosted results are recorded on PR31 separately.
