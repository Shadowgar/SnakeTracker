# X2 local taxonomy foundation — development qualification

This tranche implements ADR-0046 and AT-TAXBAS-01. Production migration/import/deployment and X3
are outside its authorization. All architecture documents, hashes and ADR statuses are preserved.

`taxa` remains the permanent UUID parent for Animal, Plant, media and reviewed guide references.
Its group CHECK is removed; an empty group means reference-only, including Amphibia. Existing
registration group/profile policy is unchanged. Names never automatically merge identities.
Provider mappings are namespaced and permanent; explicit cross-provider mapping requires reviewer
and reason, and a mismatched mapping records a conflict rather than relinking existing data.

Replaceable `taxonomy_generations`/`taxonomy_facts` hold snapshot content. A durable overlay,
catalog labels, provider references and audit revisions are independent of generation cleanup.
Reads select comparable source-effective dates within the same provider. Unknown/equal ordering
and cross-provider differences retain evidence and an explicit selection state; import date never
ranks source freshness. Original provider preference is retained when another namespace is added.
Conflict resolution records who decided to retain the identities/current selection and why.

Local FTS5 search covers qualified names, aliases/common names and classification, with an indexed
catalog fallback after rollback. Indexed token matches intersect by permanent identity across
published scopes; the selected current group is checked before applying the result limit. Search
is independent of household-private FTS and never calls a provider. Candidate discovery/filtering
has a 256-identity bound and one-second SQL-work budget; an overly broad query returns an explicit
refinement message before provider discovery. This is not a total summary/ancestry response-time
guarantee. Provider discovery results are filtered using the retained selected group. Existing directory
search/detail/live discovery use the catalog. The application-owned `LocalTaxonomy` port exposes
selected summaries (including authorship), ancestry, provenance and qualified provider references; it does not create
Natural History sources or content. Existing manual entry and bounded explicit lookup remain.

Staging reserves UUIDs and private generation search rows in batches of at most 500. It publishes
no candidate facts or aliases for either new or existing identities. An ancestry validation reads
a consistent snapshot without a catalog-sized Python graph, then seals the same content revision.
Promotion and rollback atomically publish a permanent generation receipt (with source provenance),
first-qualified fallback payload,
reference pointer and final reconciliation watermark. There is no catalog-index rebuild at promotion.
Private reservation/label revisions do not consume the concurrent-delta limit; an indexed public
delta projection checks only published identity changes. Durable live discovery remains independent
of that pointer. Differing undated observations retain
the selected payload and record a conflict for an explicit decision.

Cleanup requires an explicit rollback/backup retention set and protects the active generation.
It first claims a non-promotable `retiring` state, then compacts only previously published facts
into the durable catalog and deletes their search/fact rows in transactions of at most 500.
Interrupted cleanup can resume; private rejected labels are discarded. Lightweight publication
receipts survive content cleanup, preserving the public qualification of historical conflicts. Concurrent live publication
shares the writer lock, and each batch checks protection again. Historical catalog tokens are
deduplicated during compaction. Final deletion has no remaining fact cascade. Permanent UUIDs,
mappings, qualified fallback payloads, conflict decisions, links and assets remain.

Migration `0024_local_taxonomy` rebuilds the existing parent in an explicit transactional Alembic
operation with FK checks before commit. Runtime FK enforcement remains enabled. A blocked migration
chain now rolls back in full. Empty X2 schema can downgrade; durable X2 data blocks schema downgrade
and requires forward recovery or separately approved historical restore. Reference-pointer rollback
continues to work on the X2 binary. Startup validates X2 structures before mutable initialization.

## Offline operator workflow

The command never downloads or migrates. It supports a bounded UTF-8 Darwin Core Taxon core and
VernacularName extension described by `meta.xml`, following the
[TDWG text guide](https://dwc.tdwg.org/cs/text/) and
[GBIF archive guide](https://ipt.gbif.org/manual/en/ipt/latest/dwca-guide). Unsupported extensions,
unsafe paths, symlinks, duplicate members/identities, XML entities, absent parents and cycles fail
closed. It uses private disk staging instead of extracting into application directories. Limits
default to 64 MiB compressed, 512 MiB expanded, 16 members, 2 million rows and 120 seconds of
active parser work (consumer database-staging pauses are excluded); actual
production archive shape/size/rights require separate qualification. These are development bounds,
not claimed production capacity. Only iNaturalist's qualified known ancestry IDs map current
workflow groups; other namespaces do not borrow those IDs. Other production namespaces require an
explicit HTTPS `--taxon-base-url` for their qualified identity URLs.

Dry-run and applied staging share the same source metadata, timestamp and rights validation.
Validate a synthetic/qualified local archive without database writes:

```sh
uv run python -m snaketracker.operations.taxonomy stage /isolated/synthetic.zip \
  --provider fixture --label B --source-url https://example.test/archive \
  --retrieved-at 2026-10-17T00:00:00Z --snapshot-at 2026-10-16T00:00:00Z \
  --sha256 EXPECTED_SHA256 --rights 'Synthetic fixture'
```

To stage, supply `--database /absolute/isolated/migrated.sqlite3 --apply` before `stage`.
This prints B's UUID and does not promote. Separately invoke `promote B_UUID` or `rollback A_UUID`
with the same explicit database/apply options. `cleanup B_UUID --keep A_UUID` requires the operator
to enumerate generations retained under the rollback/backup policy. `search QUERY`, `resolve UUID`
and `conflicts` inspect local data; `resolve-conflict ID --decided-by REVIEWER --reason REASON`
requires `--apply`. `promote`/`rollback` accept `--max-revisions` and
`--max-reconciliation-seconds` for separately qualified operating bounds (defaults 10,000 concurrent
identity deltas and two seconds of SQL work). These do not change application/production settings.
No queue or privileged process is involved.

## Qualification

The initial targeted taxonomy/compatibility/archive suite passed **43 tests** (one expected
duplicate-ZIP-member warning); see [the receipt](targeted-tests.log). Follow-up review corrections
have focused receipts for [14 cleanup/compatibility/migration tests](cleanup-compatibility.log),
[interrupted 501-row cleanup](cleanup-resume.log), [five private-index preflight cases](private-index-preflight.log),
[undated observation selection](undated-observation.log), and
[fallback provenance/rollback/historical upgrade](publication-regressions.log). Historical fixture
seeding reflects schema 23, while current fixtures explicitly qualify their synthetic taxa.
The [selected-consumer suite](selected-consumers.log) passed 54 tests: guide matching follows
selected names/groups, authorship follows selected facts, foreign overlays cannot replace the
chosen provider, equal-clock decisions clear resolved uncertainty, and first live disagreements
cannot replace selected generation facts without comparable ordering. The existing
[qualified-rename regression](qualified-rename.log) now supplies source-effective dates and retains
its synonym assertion plus an explicit selected-name assertion. Formatting, lint, mypy,
architecture/freeze, documentation links and diff integrity passed.

The first hosted head passed 1,238 tests (94.50% lines / 85.29% branches). Subsequent review findings
were reproduced and corrected; fresh hosted Quality, Container and security checks qualify the
final published head, with URLs/results recorded in the PR. The initial local full gate was
intentionally canceled after defects were found and is not a passing result. No gate, timeout,
assertion or coverage threshold was weakened.

Tests cover concurrent duplicate allocation, homonyms/namespaces, source ordering, replacement
conflicts, live discovery during staging/promotion, concurrent staging during validation, bounded
promotion failure, rollback/catalog fallback, FK-preserving upgrade, immutable guides and image
metadata, historical four-profile events, and encrypted ordinary-worker restore of X2 data/search.
Use [the reproducible synthetic measurement](../../../scripts/qualification/x2_local_taxonomy.py)
for Pi import, search, promotion, storage/RAM and previous-wheel compatibility evidence.
The earlier [synthetic Pi receipt](pi-synthetic.json) uses **10,001 rows**, retaining the default
10,000 concurrent-delta limit and explicitly budgeting 30 seconds of SQL work. The population
promoted successfully: import 75.596 seconds, promotion 4.288 seconds including lock/commit I/O,
warm search median 93.8 ms / p95 110.4 ms, peak RSS 107,456 KiB. An
[earlier 1,000-row receipt](pi-synthetic-1000.json) is retained separately. Both use this Pi 5 and an actual
installed X1 wheel. The old wheel rejects schema 24 before startup mutation; the script verifies
the database hash stays unchanged. [Protected-document hashes](protected-audit.json) bind the
unchanged architecture, eight X1 approved contents and quality-gate scripts to the X1 base.

Production archive rights/intended use, real dataset reconciliation and production-size normal-duty,
backup scratch/RPO, restore/replay and import capacity gates remain required before any production
import. First connection timing is not claimed to be a cold disk-cache measurement. The configured
reconciliation deadline bounds SQL work; writer-lock waits and synchronous commit I/O also affect
measured promotion wall time. The capacity qualification uses an explicit 30-second SQL budget; it does not claim a hard
two-second wall-time guarantee or production acceptance.

X1's future-profile fallback mismatch remains deferred before additional production animal groups
are enabled. This tranche adds no Animal workflows and no Natural History prose.

Additional final receipts: [11 reconciliation/decision/lifecycle tests](reconciliation-decisions.log),
[three live-after-staging conflict cases](late-discovery-conflicts.log), and
[four operator/nonfinite-budget cases](operator-budgets.log). Unknown/equal/cross-provider ordering
is backed by durable conflicts and clears after resolution; private staging conflicts block the
candidate generation without changing live selection status. Both event orders use the same rules.

Final search/operator corrections are covered by [six focused regressions](search-source-validation.log)
and [19 additional search/archive cases](bounded-search.log), including SQLite interruption and
progress-handler cleanup. No timeout or assertion was changed.

The final combined [taxonomy/directory/archive regression run](final-focused.log) passed **83 tests**
in 102.19 seconds, with only the expected duplicate-ZIP-member rejection warning.

The last hosted review's selected-snapshot and archive-schema findings were reproduced, corrected,
and independently reviewed. [29 snapshot/archive cases](snapshot-archive-review.log) and
[13 adjacent ordering cases](snapshot-ordering.log) passed. Incoming live facts are compared against
both the stored overlay and currently selected snapshot; a differing equal-date observation cannot
replace the selection because an older overlay exists. Empty Taxon cores fail both dry-run and
applied validation. Column indexes must be nonnegative bounded integers, field indexes must be
unique, and every declared column must exist in each row. The ID and taxonID mapping may share
their standard column.

Foreign snapshot facts never replace the selected provider merely through pointer promotion.
Differing cross-provider staged facts require a durable decision; late live changes record the same
conflict. When switching namespaces, the atomic promotion retains selected outgoing preferred
snapshot facts for shared identities in the existing durable overlay, with original source dates
and per-identity audit revisions. A later cleanup cannot expose a stale initial fallback or overlay.
Same-provider promotion skips this retention work. [34 focused cases](provider-relationships.log)
cover overlay and snapshot origins, an older overlay beneath a newer snapshot, explicit resolution,
foreign promotion, cleanup, accepted-name absence/cycles and live self-reference rejection.
Archive dry runs validate both parent and accepted-name relationships. Direct live self-references
fail before reserving a permanent identity.

The final combined [taxonomy/historical-compatibility/archive suite](provider-final-regressions.log)
passed **106 tests** in 113.82 seconds, with the expected duplicate-member warning only.

Final boundary review regressions passed [35 archive/consumer cases](final-boundaries.log),
[22 decision-context/order cases](decision-context.log), and the complete
[nine-test directory integration suite](directory-boundaries.log). Ordering decisions bind both
compared fact payloads, both source-effective clocks and generation scope; retrieval time is excluded.
Repeated identical comparisons retain their decision, while a different opposing fact or source
clock requires a fresh decision. Archive limits cover field/default bounds and cumulative materialized
JSON bytes, preventing metadata defaults from amplifying a small archive beyond the qualified bound.
Tokenless directory input returns HTTP 422 without a provider call. Reference-only/future groups
retain their selected facts and skip refresh through the current workflow provider adapter.

[Ten mapping/cleanup regressions](legacy-mapping-cleanup.log) passed, including an actual schema-23
providerless taxon upgraded to X2. Its first explicit mapping establishes provider preference in the
same transaction, and an alphabetically earlier second namespace cannot change it. An unknown cleanup
UUID fails explicitly before the mutation loop; interrupted cleanup of an existing generation resumes.

[47 overlay/snapshot/rollback/mapping/downgrade cases](overlay-downgrade.log) passed. A comparable
live observation newer than the stored overlay remains durable even beneath a newer active
snapshot; rollback and cleanup expose that freshest retained live observation. Equal/unknown
comparisons continue to require content-bound decisions. Conflict-only X2 evidence blocks schema
downgrade even when no generation or revision exists, preserving schema version, UUIDs and the
operator's unresolved mapping evidence.

Relationship integrity is checked before live publication and under the generation-promotion writer
lock. Parent and accepted-name walks follow namespaced identities and permanent UUIDs, so provider
aliases cannot hide cycles. Each comparison uses a coherent snapshot/overlay/fallback view, including
retained rollback generations; newer valid reparenting does not combine unselected historical edges.
Explicit alias mappings also reject cycles hidden beneath newer selected facts. First reference
publication is a public reconciliation delta, without charging a generation's own population against
the concurrent-delta cap. All accepted search tokens participate in intersection.

The [broader graph regression run](graph-regressions-before-preflight-fix.log) passed 106 cases and
identified one premature publication-marker requirement. Removing that requirement preserves the
existing permanent-identity/catalog-index integrity checks; the previously failing case then
[passed](graph-preflight.log). Additional [coherent graph-view cases](graph-views.log) and
[alias/concurrent-cycle cases](graph-aliases.log) passed. The complete unchanged hosted Quality gate
qualifies the final committed tree.

The [catalog Pi receipt](pi-synthetic-final.json) imports and promotes **10,001 synthetic rows**:
import 79.403 seconds (29.926 CPU seconds), promotion 5.631 seconds including lock/commit I/O,
warm search median 86.2 ms / p95 105.8 ms, peak RSS 110,184 KiB. The default 10,000 concurrent-delta
limit is retained; this capacity measurement explicitly uses a 30-second SQL-work budget. The
installed X1 binary refuses schema 24 and the database hash remains unchanged. SHA-256 bindings
cover every application/migration Python source and the measurement script; they identify the
measured working tree committed as `396d56bc7d52dba6dde3b522cad7031fa6a75b51`. This supersedes earlier
receipts for catalog performance evidence and remains synthetic development qualification only.

[Thirty focused graph/alias/publication cases](coherent-alias-views.log) passed after the final
alias correction. Explicit mappings validate each coherent generation/overlay/fallback selection
independently, rather than traversing a union of obsolete edges. Valid historical reparenting remains
qualifiable; partial live relationships hidden by a newer snapshot still reject alias cycles in
the rollback view. A durable newer observation that permanently clears an obsolete fallback edge
does not falsely block an alias. Independent read-only review found no remaining Important issue
in this correction.

[All 38 archive tests](archive-optional-status.log) passed after normalizing optional taxonomic-status
cells: missing, empty and whitespace-only values become `unknown`; surrounding whitespace and case
are normalized before the existing supported-status validation. Dry-run and applied staging exercise
the same reader.

The [19-test directory suite](atomic-directory-images.log) passed with publication and image
mutation in one `BEGIN IMMEDIATE` transaction. Publication returns whether the incoming observation
is actually selected; rejected facts, foreign-provider overlays and observations beneath newer
snapshots cannot mutate the selected image. Image freshness uses the observation time, retaining
a durable watermark even after deletion, so late responses cannot replace, delete or resurrect
newer image state. Image/readback failures roll back the complete observation. Missing taxonomy
images still permit the existing explicit media-provider discovery cascade.

[Provider ancestry and image race regressions](provider-ancestry-image-races.log) passed: ancestry
keeps the child's relationship provider and coherent active-generation/overlay/fallback view even
when a parent UUID prefers another provider. It never splices independently qualified provider
trees. The [historical compatibility run](image-historical-compatibility.log) also passed before
the final image-watermark correction; the unchanged hosted gate qualifies the final tree.

[All 50 archive/historical-compatibility cases](legacy-aliases-verified-archive.log) passed after
restoring retained aliases in catalog summaries for schema-23 publications without serialized
payloads. Alias-matched local search returns those same migrated synonyms/common names.
The operator now copies and hashes one bounded input stream into private temporary storage;
both dry-run and applied parsing read that verified copy for the whole operation. Replacing the
original ZIP between verification and parsing cannot change imported facts or recorded provenance.
[Two additional database/provenance assertions](verified-archive-database.log) verify the recorded
checksum and original taxon payload after that replacement. Temporary storage is cleaned on exit.

The Pi receipt above predates the later legacy-alias, operator-input, active-conflict and qualified-alias/startup and cache/name/depth corrections. Its measured
source snapshot is retained exactly; no performance claim is made for paths added afterward. The
final unchanged hosted gate qualifies the resulting committed tree.

[Six active-view conflict cases](active-view-conflicts.log) passed. Equal/unknown-order conflicts
scoped to inactive generations remain auditable and continue blocking promotion of those
generations, but do not mark a newer unambiguous selected view uncertain. Cleanup preserves the
conflict evidence. Global conflicts and conflicts attached to the active generation continue to
affect current selection. An earlier cleanup test conflated durable evidence with current
uncertainty; its corrected expectation additionally asserts preserved evidence and rollback blocking.
Independent read-only review found no Important issue in this scope correction.

The combined [taxonomy/archive/compatibility run](alias-startup-parser-regressions.log) passed
**175 tests** after qualified-alias reconciliation, active parser timing and FTS startup checks.
[Thirteen initial startup/parser cases](startup-parser-bounds.log) verify missing/mismatched
search targets reject mutable startup and consumer staging pauses do not consume parser time;
active parsing still obeys its deadline. Additional cases cover NULL metadata and missing catalog
keys. The final [two decision/key regressions](alias-decisions-missing-keys.log) passed after
excluding import-only metadata from ordering comparisons and checking catalog coverage from every
taxon. The unchanged hosted gate qualifies the final committed tree.

Already qualified same-provider IDs can coalesce to one UUID fact in either row order and across
batches. Equivalent facts choose a deterministic canonical ID; proven synonym-to-accepted links
retain bounded alias names. Other differences require a durable decision tied to the full variant
set; adding another incompatible variant requires a fresh decision. Repeated provider IDs remain
invalid. Import-only input context is bounded to 64 variants and 256 KiB per UUID. Relationships
resolve provider IDs through permanent UUIDs, so coalesced aliases work as parent targets while
UUID cycles remain invalid. Private FTS rows and the generation content revision update together.
Cleanup strips import-only metadata before projecting labels. Scientific ordering decisions bind
only factual fields and source clocks, preventing equivalent import bookkeeping from reopening a
reviewed decision. No production import capacity is claimed for this later alias path.

[Five focused regressions](cache-names-depth.log) qualify monotonic successful-provider-check
freshness independently of retained fact provenance, rejection of excess vernacular names instead
of silent truncation, and all 127 ancestors supported by the 128-node graph validator. The complete
[20-test directory suite](directory-freshness-regressions.log) also passed. Repeated successful checks
do not repeatedly call a provider merely because selected source facts retain an older date.

The hosted Quality run on `5871dc11a22b3ccc57ee332ddc7586b138a7e8c4` found two Care Guide
fixture failures (1,385 other tests passed). [Isolated reproduction](care-guide-startup-red.log)
confirmed that direct fixture inserts omitted mandatory catalog search rows and were correctly
refused by startup. Fixtures now populate schema 23 and run the real schema-24 migration; a new
taxon uses catalog publication. All original behavioral assertions remain unchanged, and the
[complete five-test Care Guide suite](care-guide-startup-green.log) passed. Runtime integrity checks,
quality gates and thresholds were preserved. Final hosted qualification applies to the pushed head.

[Repeat-promotion/rollback reproduction](rollback-own-publication-red.log) found that a generation's
own first-publication receipts were incorrectly counted as concurrent reconciliation work.
Promotion now excludes only publication receipts explicitly attributed to its target generation;
external discoveries and changes to the same permanent UUID remain bounded. Durable publication
history is preserved. The [12-case focused run](rollback-search-reconciliation-green.log) passed,
including same/new external UUIDs, rollback/re-promotion, another generation's first publication,
and the indexed query-plan assertion. No default limit was raised.

The rollback assertions also [exposed duplicate search results](generation-search-duplicates-red.log)
for one-token queries across published generation scopes. Indexed token subqueries now deduplicate
UUIDs before candidate and result limits; one- and multi-token regressions pass with a five-identity
candidate budget over repeated generation matches. The historical Pi receipt predates these
corrections too; final hosted checks qualify their functionality, not production import capacity.

[Alias and preferred-name reproduction](alias-vernacular-provenance-red.log) confirmed that first
publication updated every same-provider alias and the archive reader discarded preferred-name
markers. Publication now updates only its exact provider ID; other qualified mappings retain
their own URLs and timestamps. Serialized fallback selection also joins the exact published
provider/ID, preventing a retained alias's facts from acquiring another mapping's retrieval date
after rollback. That [fallback reproduction](alias-fallback-provenance-red.log) is covered through
cleanup and preservation of the untouched mapping.

The [28-case final focused run](alias-vernacular-final-green.log) passed: generation/live canonical/
live alias first publication, qualified alias reconciliation, historical compatibility, rollback
fallback/cleanup, preferred-marker row order/duplicates and operator staging. Vernacular markers
accept true/false and 1/0 with whitespace/case normalization; absent/empty flags preserve lexical
fallback. Invalid markers require reconciliation. Multiple flagged names use a deterministic
lexical tie-break while retaining the others as alternatives. Name and archive limits remain
unchanged. Independent read-only review found no remaining Important issue. These corrections
also postdate the historical Pi performance receipt; fresh hosted checks qualify the final source.

[Absent-identity reproduction](absent-foreign-retention-red.log) found that switching to an unrelated
provider generation retained preferred snapshots only for identities shared with the incoming
archive. Promotion now preserves selected outgoing preferred-provider facts even when their
identities are absent from that archive. Existing newer overlays remain authoritative; facts,
original source clocks and per-identity audit are retained atomically. The [12-test focused run](absent-foreign-retention-green.log)
passed for mapped/absent identities, with/without older overlays, rollback, cleanup and complete
preferred-provider ancestry/search retention. Independent read-only review found no Important
issue. Graph validation and SQL-work time guards remain enabled; no bound was raised. This path
also postdates the historical Pi receipt and carries no production-size capacity claim.

[Accepted-name ancestry reproduction](synonym-accepted-ancestry-red.log) confirmed that synonyms
without their own parent chain lost their configured group. The reader now includes parent
ancestry for each validated accepted-name target when classifying the qualified iNaturalist
namespace. Unknown namespaces remain reference-only; contradictory configured groups still
require reconciliation. The [complete 57-test archive suite](synonym-accepted-ancestry-green.log)
passed, including two accepted-name hops, explicit synonym-conflict acknowledgment, promotion
and group-filtered local synonym search. Existing missing-parent, cycle, depth, parser-time,
archive-size, preferred-name and identity guards remain enabled. The duplicate ZIP warning is
expected from its rejection fixture. No runtime Animal registration group was added. This path
also postdates the historical Pi performance receipt.

[Five orphan-index cases](orphan-search-startup-red.log) reproduced startup accepting unowned
catalog/generation FTS rows, including unknown/NULL scopes and NULL identities. Read-only startup
inspection now checks both reference directions: every catalog row must be its permanent key's
exact row and every generation row must belong to its matching fact. Valid private and published
indexes remain accepted. The [complete 29-test compatibility/Care Guide run](orphan-search-startup-green.log)
passed, including historical migration and rejection before mutable engine initialization.
Independent read-only review found no Important issue. No schema, recovery mutation or operating
limit was added. This integrity correction also postdates the historical Pi receipt.

[Legacy classification/core-name reproduction](legacy-classification-core-names-red.log) confirmed
that initial migration search documents omitted stored classification/authorship, and imports
silently lost core common names when extension names existed. The unpublished X2 migration now
indexes its frozen list of all 12 legacy labels plus retained aliases without changing historical
rows or references. Tests query unique values for every classification/authorship field immediately
after migration, without refresh.

Core common names now enter the same private bounded/deduplicated name set as extension names.
Explicit preferred extension markers remain authoritative; core/extension duplicates count once,
and combined overflow fails explicitly. The [complete 89-test compatibility/archive run](legacy-classification-core-names-green.log)
passed. Independent read-only review found no Important issue. The historical Pi receipt binds
an earlier source/migration version; these corrections carry no new performance or production
capacity claim. No production migration or import was performed.

[Providerless legacy reproduction](providerless-legacy-red.log) confirmed that migrated, locally
qualified taxa without external mappings disappeared from resolution/search despite retained
UUIDs and guide references. Catalog and directory reads now preserve payload-null legacy records
with explicit local provenance, the same permanent UUID, a local directory URL and the retained
local timestamp. Reads create no provider mapping; the first later explicit qualification still
establishes provider preference. Serialized publications continue requiring their exact external
provider/ID rather than silently becoming local if corrupted.

The [complete 51-test historical/directory/Care Guide run](providerless-legacy-green.log) passed.
Mapped and providerless historical fixtures retain raw rows, immutable guide triggers, linked
Animal/media references and alias search. Independent read-only review found no Important issue.
The historical Pi receipt predates this compatibility correction; no new performance claim is made.

[Publication/term-URI reproduction](publication-term-uri-red.log) confirmed that missing publication
rows could hide previously public taxa without blocking readiness, and foreign term URIs could
be consumed by suffix alone. Startup now validates publication coverage using durable public
lifecycle evidence while allowing explicit private snapshot reservations through qualification
and cleanup. Uncorrelated history sets avoid per-identity history scans.

Consumed fields now bind exact [Darwin Core term identifiers](https://dwc.tdwg.org/terms/) and the
[GBIF VernacularName descriptor](https://rs.gbif.org/extension/gbif/1.0/vernacularname.xml).
Unsupported namespaces cannot impersonate consumed taxonomy/preference fields; unused qualified
metadata stays outside taxonomy facts. Extension row types are exact, while legitimate Dublin
Core metadata remains acceptable. The [complete 102-test compatibility/archive run](publication-term-uri-green.log)
passed, including migrated, cleaned-snapshot and staged-then-live publication loss and valid
private reservations. Independent read-only review found no Important issue. These checks also
postdate the historical Pi receipt and add no production performance claim or infrastructure.

[Dialect, source-URL and identity regressions](dialect-url-identity-red.log) reproduced ignored
archive record/escape settings, missing URL path separators and whitespace-only provider IDs.
Unsupported record separators and escape dialects now fail explicitly before parsing; supported
LF, CRLF and CR dialects retain every record. Explicit source bases must be absolute HTTPS paths
without query or fragment, and opaque identifiers append as one encoded path component. Shared
identity validation rejects blank IDs before publication, mapping or staging can create state.

The [complete archive suite and focused identity regressions](dialect-url-identity-green.log)
passed: 91 cases, including unchanged database counts on rejected writes. Ruff, formatting, mypy,
architecture, freeze, document links and full-PR whitespace checks passed. The duplicate ZIP warning
is expected from its rejection fixture. These corrections postdate the historical Pi receipt and
make no new performance claim. No production operation or registration workflow changed.
