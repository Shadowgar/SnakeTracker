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
default to 64 MiB compressed, 512 MiB expanded, 16 members, 2 million rows and 120 seconds; actual
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

The [final-source Pi receipt](pi-synthetic-final.json) imports and promotes **10,001 synthetic rows**:
import 84.719 seconds (30.300 CPU seconds), promotion 5.669 seconds including lock/commit I/O,
warm search median 84.9 ms / p95 104.3 ms, peak RSS 110,072 KiB. The default 10,000 concurrent-delta
limit is retained; this capacity measurement explicitly uses a 30-second SQL-work budget. The
installed X1 binary refuses schema 24 and the database hash remains unchanged. SHA-256 bindings
cover every application/migration Python source and the measurement script; they identify the
measured working tree before its final commit. This supersedes earlier receipts for final-source
performance evidence and remains synthetic development qualification only.
