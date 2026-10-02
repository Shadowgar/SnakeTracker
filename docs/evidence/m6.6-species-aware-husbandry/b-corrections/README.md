# M6.6-B production correctness correction

Status: five objectives implemented; final full quality gate passed. Production release is
blocked by incomplete encrypted attachment history. PR #17 remains draft; owner acceptance pending.
Authority: owner's October 1 production-correctness request. ADR-0044 and ADR-0048 remain Proposed.
Verified implementation source: `859ca2964953b26657cf4699bc128ac646c347e4`. A following evidence-only commit records this identity;
production source/tests/reference/scripts are identical to the fully qualified implementation.

## Bounded implementation and qualification sequence

1. Reproduce Add Spider in a disposable browser dataset before fixing it; test manual/provider
   failure, selected-image absence, stale text/type/results, explicit Add/Edit retention and inline linking.
2. Separate cache-only image reads from explicit enrichment and qualify every ordinary profile/image
   read state with outbound transports trapped. Render all reviewed guide claims, separate source
   positions and provenance directly on Overview; retain Directory and standalone guide routes.
3. Add a separately versioned Boa constrictor reference bundle, genuine source provenance and
   isolated idempotent import tests proving no household writes.
4. Implement ADR-0048 exact additive length v2 through every consumer: commands/deserialization,
   correction/void/reinstatement, facts/history, analytics/mm charts, numeric report/CSV, reminders
   under a fixed clock, replay and search applicability. Preserve v1 and its immutable payloads.
5. Run focused tests, desktop/mobile browser and accessibility qualification, frozen dependency sync
   and the full quality gate without relaxed timeouts or suppressed failures.
6. Verify an encrypted backup, restore only into isolated copies, compare old/candidate semantic
   state at one cutoff/clock, replay candidate projections, then commit/push the qualified source.
   Build/deploy that exact source via the existing safe process only after all gates pass; import
   Boa reference tables only and verify household/business state and attachments remain unchanged.

No X1, bulk taxonomy, Amphibians or M6.6-C work; no PR merge or milestone acceptance.

## Initial browser reproduction (before source fixes)

The isolated fixture `/tmp/m66b-browser.nAoz2jKu` uses fictional Animals and database, never production.
At source baseline `3432cb5405e8e44b6905c0d116a904121da4b44f`:

- Spider + unknown trade name + empty Directory results + blank `taxon_id` created successfully
  (`POST /animals` 303, resulting profile 200). The plain no-result failure reported by the owner
  was not reproduced with this clean state; the exact original browser state is unavailable.
- Selecting the cached Spider *Avicularia avicularia*, with no eligible reference image, submitted
  hidden `photo_preference=species_reference` and returned 422: "A licensed species reference
  image is not available." The form always submits that preference; the JavaScript reset still
  targets the removed `none` radio, so cannot reset the hidden value. Server validation incorrectly
  makes optional image availability a prerequisite for saving an explicit taxon.
- The form contains no explicit manual-entry action, only passive help text. Edit ignores submitted
  `taxon_id`. Tests additionally reproduced outbound image download during cold profile rendering.

These are verified defects; the selected-image failure is not claimed as proof of the original
unknown Spider browser state. New automated/browser coverage qualifies both paths and stale state.

## Implemented behavior

- **Manual species:** an explicit Use manual species entry action cancels pending searches and
  clears pending taxon/photo state. Blank taxon ID preserves entered text and creates an unlinked
  Snake, Spider, Lizard or Scorpion through every bounded provider failure. A selected taxon is
  optional; an available licensed reference photo is also optional.
- **Add/Edit/legacy links:** Add persists an explicitly selected compatible taxon. Edit saves an
  explicitly selected replacement through the existing immutable link command; later free-text
  identity edits retain an established link, as its help text states. An unlinked profile contains
  the search and one explicit confirmation. No fuzzy match, historical relink or capability upgrade.
- **Local reads:** profile visual resolution and `/directory/reference-images/{taxon_id}` use
  cache-only metadata/verified bytes. Missing/corrupt optional cache data falls back locally.
  Explicit `/api/directory/{taxon_id}/reference-image` remains a separate bounded acquisition action.
- **Reference:** Overview separates Your Records and Species Reference, displays every reviewed
  claim/context group directly, retains separate disagreeing positions and same-page provenance.
  Directory, taxon details and standalone guides remain secondary browse surfaces. New release asset
  key `m66b-correction-v3` invalidates the prior profile-reference browser/PWA cache.

## Boa constrictor reference

[Additive reviewed bundle](../../../../reference/care-guides/reviewed-boa-constrictor-v1.json):
34 sourced positions from seven pages/two publishers, grouped into 28 contextual facts:
22 Single source, two Corroborated and four Sources differ. Publishers are Royal Veterinary College
and ReptiFiles; publisher/title/URL/retrieval/review dates and per-claim scope/context are retained.
RVC's exact-species sheet and ReptiFiles' broader genus guide are explicitly distinguished; the latter
retains its Boa imperator/Boa constrictor and locality cautions. Different basking measurement contexts
are separate facts. Cool-side, humidity, overnight and UVB disagreement is preserved.

Source retrieval limitation: the official RVC PDF returned 403 on direct requests. Its publisher-hosted
indexed text was inspected for the included claims; ReptiFiles temperature used indexed retrieval
after direct-open timeout. This is recorded in the
[source policy](../../../operations/care-guide-sources.md); no unread/unsupported claim is added.
The original five-guide bundle is byte-identical, SHA-256
`fd3e4d6e8d96173a51cfe7d7f5c20ecbfe24aae68127a3481f42a99e05097500`.

Isolated imports are repeatable/idempotent and change only the four global care-guide tables.
Every non-guide table is hashed before/after, with populated Animal, Inventory-linked Feeding,
stock balance, reminder rule and due-fact state. Production Boa import has **not** occurred.

## Exact length consumer matrix — AT-MEASURE-01

| Consumer | Implemented and qualified behavior |
|---|---|
| Record/deserialization | Additive v2 integer `length_um`, `entered_value_scaled`, `entered_scale`, `entered_unit`; strict ints, exact equality, 100–10,000,000 um inclusive; mm one decimal place, cm/in two; no float authority or rounding |
| Corrections | Number-only, unit-only and full replacement recompute the complete exact tuple; target v1/v2 record or legacy/v2 correction chain; root URL opens latest effective number/unit |
| Void/reinstatement | Shared effective-history semantics retain mixed-version roots, corrections and source lineage |
| Current facts/history | Original entered value and explicit unit; permanent historical v1 mm interpretation |
| Analytics/charts | Exact canonical conversion before presentation; one Length (mm) axis, separate weight axis and original-unit tooltip/table |
| Reports/CSV | New `/animals/{id}/measurements/report` and `measurements.csv`; effective event/root/target IDs, schema, canonical integer um, entered number/scale/unit; existing care CSV retained |
| Search | Numeric measurements verified to participate; exact original/canonical v2 tokens, effective correction/void/reinstatement refresh and retained fact source position |
| Reminders | Fixed-clock mixed versions qualify source event, due date and one-time override consumption; correction, void and reinstatement preserve source semantics |
| Replay | Both versions registered; insights/search rebuild and catch-up retain facts; search handler 4→5 triggers existing generation rebuild |
| Browser/accessibility | Decimal input and explicit unit, accessible retained-input error, desktop 1440×900/mobile 390×844 pipeline |

V1 payloads/deserializers and stored events remain unchanged indefinitely. The v1 corrected-length
contract's correction eligibility is additively enabled to allow a v2 successor; this does not rewrite
its historical payload. Relational schema remains `0023_sourced_care_guides`; no migration is added.

## Browser qualification — AT-SPDIR-MANUAL-01 / AT-PROFILE-REF-01

[Final browser JSON](browser-qualification-20261001073705669.json): **84/84 cases**, 32 fictional
screenshots, zero axe violations, zero horizontal-overflow captures, zero unexpected console/page
errors and zero foreign-origin page requests across both viewports. This is candidate-working-tree
evidence (`dirtySource: true`), not a deployed-image assertion.
The final browser run precedes the additive legacy-chain/search-provenance and compatibility-harness
review fixes. No browser assets changed thereafter; later changes have dedicated HTTP/service/replay
regressions and the final full quality gate.

Cases include all four types × six provider outcomes; selected-but-no-image Add; text/type clearing;
late old search/image response; same-save Edit; inline legacy linking; all reference/no-guide/unlinked
states; Directory; record/profile/history/trends/CSV/correction and excessive precision validation.
Every real contextual fact is directly visible: six Python, seven lizard and 28 Boa groups.
48.5 in displays unchanged, plots 1231.9 mm and exports 1231900 um. Unit-only correction to 48.5 cm
exports 485000 um with root/target lineage retained. 12.25 mm fails accessibly without rounding.

Raw browser console resource errors are **26**, all retained: 24 injected provider 503/429/timeout
responses and two intentional 422 precision errors. Intermediate harness assertion/debug failures
were retained privately and corrected; the final full run passed without suppressing product errors.
Backend zero-network instrumentation separately traps provider and general urllib transports in
keeper-photo, cached-image, missing-image, unlinked and missing-optional-reference states.

Reproduction uses the guarded empty fixture preparer and loopback-only browser script:

```sh
correction_fixture=$(mktemp -d /tmp/m66b-browser.reproduce.XXXXXX)
uv run python scripts/qualification/m66b_correction_prepare_browser.py --data-dir "$correction_fixture"
# Start TEST application on 127.0.0.1:8098 using this fictional fixture.
M66B_MANIFEST="$correction_fixture/browser-manifest.json" \
  M66B_PLAYWRIGHT_MODULE=/home/rocco/.npm/_npx/705bc6b22212b352/node_modules/playwright \
  node scripts/qualification/m66b_correction_browser.js
```

The preparer rejects unrelated prefixes and populated targets; there is no overwrite/reset mode.

## Independent review and test evidence

Independent review found two Important defects, both fixed and meaningfully requalified:
legacy v1 correction-chain eligibility/root reopening, and schema changes passing the compatibility
comparison. The latter now compares normalized table/view/index/trigger definitions (including
constraints) and fails closed on a missing schema dimension. CHECK/view/trigger/index mutations fail;
active generation names normalize without masking SQL literals or care-guide schema changes.
No remaining Critical/Important code finding was reported.

Focused final results (overlapping suites, not summed):

- Manual provider failures: **24 passed** (four types × six outcomes).
- Reference/visual/profile suite before the added provider cases: **24 passed**.
- Length/legacy/search/contracts/HTTP regressions after review fixes: **116 passed**; three specific
  legacy/provenance regressions passed separately.
- Compatibility harness after schema review: **22 passed**.
- Boa complete covered suite after bounded fixture correction: **3 passed in 2.28s**.
- Frozen dependency sync: **75 packages checked**; Ruff formatting/lint passed.

The initial full gate had **857 passed, one failed** in 711.94s: the new Boa import test exceeded
the unchanged 30-second timeout while invoking the complete owner browser rehearsal. Coverage-only
isolation reproduced the timeout (36.09s). Its fixture now uses bounded real household command paths
and retains all non-guide-table invariance assertions; the covered suite passes. A temporary fixture
assertion used an upcoming rather than due reminder, then was corrected to a fixed overdue clock.
No product behavior or timeout was weakened. Final full quality gate passed: **868 tests**, 172 warnings,
554.64s; **94.46% line / 85.27% branch** coverage; no known dependency vulnerabilities; architecture,
freeze, documentation, typing, Compose configuration and diff checks passed.
[Sanitized quality receipt](quality-20261001.json) retains exact command and artifact checksums.

## Isolated production comparison — AT-PRODCOMP-01

[Sanitized compatibility receipt](production-compatibility-20261001.json): common event cutoff
**1027**, UTC clock **2026-10-01T07:20:17+00:00**, schema **0023_sourced_care_guides**.
Old reads/rebuild ran in the actual deployed image `snaketracker:m66b-profile-c4740b3`, revision
`c4740b32c1b80f054725c0a037d47689bc283474`, with network disabled. Candidate used the reviewed
working tree, then was recaptured at committed source `859ca2964953b26657cf4699bc128ac646c347e4` with a second passing comparison. Both refreshed manifests have 1,373 successful application read dimensions; comparison
covers 64 table/view content dimensions and 114 normalized schema objects, with no unexpected
differences. Expected changes are only Boa rows in four reference tables and validated release
registry/handler/source evolution. A first comparison detected 21 length documents whose source
position drifted on unrelated length events; source was fixed, replayed and comparison then passed.

Includes immutable events/subjects, profiles/capabilities/effective history, Feeding/Inventory/FIFO,
balances, reminders/source/override/due/dedup, stored responses, taxon/photo preferences, all 46
attachment hashes, reference cache, Enclosure/Plant ownership, search, reports, and Admin adapters.
All asynchronous product groups rebuild at the cutoff; synchronous tables are preserved and their
actual adapters compared, **not independently reconstructed**.

Additional isolated-copy qualification: **61** real stored registration retries and 61 changed-command
conflicts left events, subjects and idempotency responses unchanged. Keeper profile/history/search,
three reports, numeric report/CSV and allowlisted Admin/support views returned 200; anonymous profile
303, anonymous/nonoperator Admin 403 and unrelated Animal 404. Read paths made zero trapped outbound
calls. New v2 record/correction and effective numeric export worked on another disposable production
copy. The actual old image rejected that copy at startup with `event_contract_unknown`, unchanged
immutable state. An initial HTTP harness reused a session rotated for a missing CSRF cookie; adding
the issued CSRF cookie qualified the real unchanged session behavior. No production session was made.

**Release compatibility is still blocked by the backup gap below.** Diagnostic supplemental file
copies support the comparison but do not qualify a complete encrypted restore.

## Backup and deployment gate

Existing worker-requested encrypted backup **bfb0efc2-0b0b-4718-b2b1-88e7d1be2970**, completed
2026-10-01T07:20:17.628750+00:00; manifest SHA-256
`9acc3d8af9833efdcfe9ed4d5a665a7713089e2c565b4584a2fbeac55e44a45a`.
Authenticated decrypt/restore and its advertised checks passed for **40 current photo versions**.
Production metadata and media contain **46 immutable versions**. The backup attachment selection
joins only current photos and omits six historical versions. Those original files still exist;
read-only copies supplemented the isolated diagnostic dataset after hash verification.

Restore retries exposed a 16MiB container `/tmp` limit and isolated bind UID mismatch; the completed
restore used a private marked host directory with appropriate isolated-only ownership. No runtime,
secret-file or production-media permissions were changed. This archive is internally verified but
is **not a complete historical attachment recovery point**. It cannot satisfy the release gate.

The runbook makes the worker the sole backup initiator. Owner scope approval is pending for a narrow
backup-selection correction and a new worker-created encrypted backup. No ad hoc operator backup,
Pi production candidate Docker build/recreate, production migration or global Boa import was performed.
The deployed image remains `snaketracker:m66b-profile-c4740b3`.

## Production integrity and owner review

This correction has added only backup operational request/run metadata to production. It has not
written household/business events, altered user records, relinked Animals, changed schedules, consumed
Inventory, or changed/deleted photos. `.env`, operator allowlist, runtime DB/attachments and production
environment remain preserved. All mutations/replay/browser work use marked disposable copies.
An additional read-only live comparison confirms event high-water 1027, schema 0023, 42 unchanged
base business-table dimensions and all 46 immutable attachment hashes. Three existing September
password-reset credentials are present in live storage but intentionally absent from the restored
backup, whose pipeline excludes ephemeral authentication secrets; this is an expected recovery policy.

The five review flows are prepared and qualified in fiction: unknown Spider; same-save explicit
Directory selection; direct Boa reference; fractional length/correction/history/analytics/export;
mobile 390×844. They are **not yet available as this candidate in live production**. After complete
backup qualification and full gate, an exact committed image must be built/deployed through the
established safe process, with a separate before/after integrity receipt. PR #17 must remain open,
draft and unmerged. ADR-0044, ADR-0048 and M6.6-B acceptance remain owner decisions.

## Subsequent immutable-backup blocker resolution — October 1

The preceding incomplete-backup and pending-authorization statements record the earlier qualification.
Under the owner's subsequent narrow backup request, correction
`606e8a2024674a9c9c1f3d9903b6f41d61c31199` and packaging follow-up
`65a0b3d3d582a0ee15ce3beb6027eaee45bfe1ff` passed the full gate: **892 tests**,
**94.53% line / 85.35% branch** coverage. The
[bounded recovery qualification](backup-completeness/README.md) and
[sanitized receipt](backup-completeness/qualification-20261001.json) retain source/image proof,
the execution incident, restored hashes/counts and final production integrity.

A temporary worker based on deployed source plus only the backup patch created encrypted run
`8777f5b4-545e-4384-81e6-e50c99553bb8`, cutoff 1027, schema 0023:
**46 finalized DB versions = 46 manifest attachments = 46 restored files**, zero metadata/hash
mismatches, including all six previously omitted versions. Original images/containers, `.env`,
business state and all media remain preserved. A failed Compose cleanup dependency attempt applied
no migration; original worker resumed directly. Normal reminder calculation timestamps refreshed.
The old 40-photo archive remains historically incomplete. The backup/recovery blocker is resolved;
full M6.6-B deployment and Boa production import remain deferred. No ADR/milestone acceptance,
PR merge, X1 or M6.6-C work occurred.

## Subsequent live owner-review deployment — October 1

Under the owner's subsequent exact-head deployment request, source
`f1d4d33c27bdb79be31b7c9fbf33b5291c036377` is now live in paired web/worker image
`snaketracker:m66b-owner-review-f1d4d33`. A 15-second worker-first/web-second controlled replacement
used `--no-deps --no-build`; migration, nginx, tunnel, `.env`, settings and mounts were preserved.
Schema remains 0023. The qualified complete recovery point remains valid and unchanged.
The bounded reference-only Boa import added one version, seven sources and 34 positions/28 facts;
rerun imported zero and wrote nothing. Cutoff 1027, all 55 unchanged logical dimensions, 46 immutable
attachment versions and 77 media files match. Expected search handler 4→5 generation rotation adds
only derived objects and excludes four identity-settings care-search entries; authoritative events
are unchanged. Normal reminder calculation timestamps refreshed.

[Live deployment evidence](owner-review-deployment/README.md) and its
[sanitized receipt](owner-review-deployment/qualification-20261001.json) distinguish actual service
health, 61 real read-only profile renders with zero outbound calls, bounded 390×844 local layout replay,
and pending authenticated owner review. External browser User-Agent readiness returns 200; Python
User-Agent was blocked by unchanged Cloudflare 1010. The actual previous image now refuses the newer
projection catalog, so a plain container-only rollback is unsafe. No rollback bypass was attempted.
PR #17 remains open/draft/unmerged; M6.6-B and ADR-0044/0048 remain unaccepted. No X1, bulk taxonomy,
Amphibians or M6.6-C was started. Work stops for the five owner review flows.
