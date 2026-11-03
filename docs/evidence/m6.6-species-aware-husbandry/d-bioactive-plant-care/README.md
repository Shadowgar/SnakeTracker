# Bioactive enclosure and plant-care qualification

Development candidate dated November 3, 2026, stacked on Smart Care and X5. No production availability or milestone acceptance is asserted.

Enclosures own their explicit bioactive mode, plants and immutable maintenance history. Separate plant watering, enclosure cleaning and water-change schedules reuse existing reminders. Animal moves do not transfer mode/plants/history. Native manual preview/confirmation works without guidance; different plants keep independent intervals. Removing a plant retains its history while suppressing future tasks and delivery.

## Implementation and scoped checks

Core `b6f543c02e2136c8a43b01441a8b8b2703d033a7` was integrated with final C source/evidence at `49096dbbbe973c5bbe08011152bf9483f4279df8`. A shared preview-method conflict was resolved to C's richer due/explanation/source result, retaining D's disabled-rule handling and precise plant history selection.

Core targeted service/HTTP/notification/runtime recheck: **7 passed** in 27.64 seconds. Larger scoped enclosure/reminder/notification/presentation and compatibility/lifecycle groups passed 42 and 39 tests respectively, each with one test timing out during fixture SQLite commit under concurrent local I/O. Both affected tests passed in the isolated recheck with unchanged default timeouts. The actual prior binary's web and worker startup refusal passed in the compatibility group. No environmental attempt is counted as a clean full-suite pass.

The focused cases cover separate plant source histories and due dates, Animal movement, mode retry, DST local-day intervals, corrections/void/reinstate, household and role guards, CSRF, signed stale/cross-plant previews, exact receipts and concurrent confirmation, removed-plant facts, scheduler deduplication and pending-delivery suppression. Existing non-bioactive enclosure and Animal capability checks remain in the scoped and unchanged hosted suites. Ruff, mypy, architecture and protected-document freeze checks passed for the core.

## Migration and rollback

`0027_bioactive_plant_care` adds `enclosure_current.bioactive`, default false, with a native additive column operation. It does not rebuild retained tables or rewrite deployed migration history. The populated runtime hook compares all prior table values/columns, triggers and guide content across upgrade/downgrade/re-upgrade, checks integrity/FKs and immutable trigger rejection, and exercises an unsafe-downgrade refusal after a disabled plant schedule before any watering.

Reproduce on the existing disposable SQLite 3.40.1 qualification image, with no production mounts or network:

```sh
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop ALL \
  --security-opt no-new-privileges \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/qualification/src \
  -v "$PWD:/qualification:ro" --entrypoint python \
  snaketracker:sqlite340-380db246f090 \
  /qualification/scripts/qualification/bioactive_sqlite_runtime.py
```

The wrapper asserts actual SQLite 3.40.1; the hook verifies `trusted_schema=OFF`. It creates only a disposable temporary database. `tests/integration/test_bioactive_compatibility.py` runs actual prior source `47f14b4790874bcf73d39331c0feb9fb4f04cbe5` through web and worker startup and verifies schema27 refusal before mutable startup with unchanged database bytes.

Downgrade is blocked by retained bioactive-mode/watering/correction events or any plant-targeted reminder history, even disabled rules. Disabling features does not make an older binary safe. Historical restoration and its recovery-point boundary remain distinct from binary rollback.

## Browser, source and release boundaries

`scripts/qualification/bioactive_browser_review.js` uses the existing fictional loopback fixture, blocks external requests and exercises independent plant schedules, Today/Calendar/reminders, watering, correction/void/reinstate and moving the Animal while retaining the empty enclosure's mode/plants/history. Representative captures and machine results accompany final qualification.

No new care research or numeric guidance is added. Existing pot-grown plant reference is linked with explicit enclosure-interval and animal-safety limits. Bioactive mode never implies no cleaning and never changes Animal capabilities. Existing source bundles remain unchanged.

The [user-facing release draft](whats-new-draft.md) is prepared for the existing Updates page; no release-ledger entry is published. Physical-device/screen-reader acceptance, applicable content publication/import and owner-authorized production migration/deployment remain separate from this candidate. Final exact-head hosted checks and independent review outcomes are recorded on the PR and in the integrated candidate receipt.

## Final UI and runtime receipt

At source `4fd8829f33af2a90a4783ad91b316b85b2376219`, five focused native HTTP tests passed after the precise-time follow-up; mypy, whole-repository Ruff/format and diff checks passed. Notes-only watering corrections retain the exact timestamp, including a repeated DST hour; a microsecond override-boundary regression verifies that editing notes cannot reactivate a consumed due override. Current and proposed schedules retain and display exact instants; returning from preview retains keeper choices.

The full real Chromium journey passed on that source: create bioactive habitat → add two plants → confirm 3-day and 7-day schedules → see both in Today/Calendar/reminders → water one and see its independent due transition → correct, void and reinstate watering → move the Animal and verify the original empty enclosure retains mode/plants/history. Seven representative 390px/320px/1440px screenshots are in `screenshots/`; every checked main region had zero axe WCAG A/AA violations and horizontal overflow, with zero page errors or external requests. The fixture is `/tmp/carekeeper-x5-browser-bioactive-ui-20261103`, port8123. Use `CARE_SOURCE_REVISION`, `CARE_FIXTURE`, `CARE_PLAYWRIGHT` and `CARE_AXE` with the browser script. Earlier incorrect harness expectations for a `#history` redirect and date-based agenda buckets were corrected; no product pass was inferred from those incomplete runs.

The reproducible wrapper above passed initially at4fd8829 and again at integrated source fd781960 on actual SQLite 3.40.1, `trusted_schema=OFF`; [raw runtime log](sqlite340.log) records populated preservation, foreign keys/immutable triggers and unsafe downgrade refusal. No production data or recovery archive was used.

Final source `fd7819601a28172a085dfdff82fa69f3a9b6ca49` incorporates C's shared atomic guard and wires the native enclosure preview to its original signed source head. Interleaved watering during context loading, due calculation, application save or transaction append rejects the request. Exact completed confirmations, including unchanged-rule receipts, still replay after later care. Wrong-purpose tokens return controlled errors. Browser fields use valid millisecond values while preserving the exact retained instant in authenticated context; notes-only corrections preserve precise history.

The final scoped C/D overlap run passed **64 tests** in 72.85s; mypy, Ruff and formatting passed. The independent review's initial defects are retained in the review record with remediation rather than represented as initial clean results. Actual integrated Chromium at this source additionally passed all three precise timestamp form round trips (Smart Care/Edit again, native plant schedule/Change choices, notes-only correction), checking real input values/validity and the final SQLite values. See the [integrated precision results](../e-final-qualification/precision-browser-results.json). Ordinary UI captures above are reused at their stated revision because the final changes affect timestamp serialization and concurrency checks, not the photographed layouts.
