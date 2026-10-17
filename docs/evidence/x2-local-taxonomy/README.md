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

Local FTS5 search covers retained names, aliases/common names and classification, with an indexed
catalog fallback after rollback. Historical classification/group tokens are retained without duplicate
expansion; the selected current group is checked before applying the result limit. It is independent of household-private FTS and never calls a
provider. Existing directory search/detail/live discovery use the catalog. The application-owned
`LocalTaxonomy` port exposes selected summaries, ancestry, provenance and qualified provider
references; it does not create Natural History sources or content. Existing manual entry and
bounded explicit provider lookup remain available.

Staging reserves UUIDs without publishing them to application reads and writes batches of at most 500 records. An ancestry validation reads a
consistent snapshot without a catalog-sized Python graph, then seals only the same content revision.
Promotion and rollback use bounded SQLite writer transactions, a final revision cutoff and shared
durable search; subsequent discovery cannot publish only to an abandoned generation. Failed
validation/reconciliation/conflict resolution leaves the previous generation active. Cleanup accepts
an explicit rollback/backup retention set, always protects the active generation, and removes only
generation content/search rows. Catalog identities, mappings, conflict decisions and assets remain.

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
requires `--apply`. No queue or privileged process is involved.

## Qualification

The initial targeted taxonomy/compatibility/archive suite passed **43 tests** (one expected
duplicate-ZIP-member fixture warning); see [the receipt](targeted-tests.log). Formatting, lint,
mypy, architecture/freeze checks and documentation links passed. The first hosted head passed 1,238 tests, with 94.50% line and 85.29% branch coverage.
Hosted review then identified staging visibility and self-cycle defects. Publication markers now
keep reservations hidden from directory and guide reads until live qualification or promotion;
first-qualified facts and provenance survive rollback, with fallback source-clock reconciliation.
Direct self-cycles fail validation. Additional regressions cover these corrections; the
[latest focused receipt](publication-regressions.log) includes historical upgrade preservation,
fallback provenance and rollback ordering. One historical fixture needed direct legacy guide
seeding because the current importer intentionally requires X2 visibility; that correction passed.
The initial local full gate
was deliberately canceled after review found defects and is not a passing result. Fresh hosted
Quality, Container and security checks qualify the published PR head; their final URLs/results
are recorded in the PR. No gate, timeout, assertion or coverage threshold was weakened.

Tests cover concurrent duplicate allocation, homonyms/namespaces, source ordering, replacement
conflicts, live discovery during staging/promotion, concurrent staging during validation, bounded
promotion failure, rollback/catalog fallback, FK-preserving upgrade, immutable guides and image
metadata, historical four-profile events, and encrypted ordinary-worker restore of X2 data/search.
Use [the reproducible synthetic measurement](../../../scripts/qualification/x2_local_taxonomy.py)
for Pi import, search, promotion, storage/RAM and previous-wheel compatibility evidence.
The committed [synthetic Pi receipt](pi-synthetic.json) uses 1,000 rows on this Pi 5 and an actual
installed X1 wheel. The old wheel rejects schema 24 before startup mutation; the script verifies
the database hash stays unchanged. [Protected-document hashes](protected-audit.json) bind the
unchanged architecture, eight X1 approved contents and quality-gate scripts to the X1 base.

Production archive rights/intended use, real dataset reconciliation and production-size normal-duty,
backup scratch/RPO, restore/replay and import capacity gates remain required before any production
import. First connection timing is not claimed to be a cold disk-cache measurement.

X1's future-profile fallback mismatch remains deferred before additional production animal groups
are enabled. This tranche adds no Animal workflows and no Natural History prose.
