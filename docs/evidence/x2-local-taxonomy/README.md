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
is independent of household-private FTS and never calls a provider. Existing directory
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
The committed [synthetic Pi receipt](pi-synthetic.json) uses **10,001 rows**, retaining the default
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
