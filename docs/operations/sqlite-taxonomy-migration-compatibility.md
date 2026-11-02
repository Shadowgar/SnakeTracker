# SQLite 3.40.1 taxonomy migration compatibility

The supported hardened connection policy remains `PRAGMA trusted_schema=OFF`.
SQLite 3.40.1 cannot use `json_extract()` in persistent schema expressions with
that policy. Migration 0024 therefore omits the optional
`ix_taxonomy_fact_provider`, `ix_taxonomy_overlay_name` and `ix_taxonomy_fact_name`
expression indexes. Migration 0025 introduces no JSON schema expressions.

Provider identity lookups use the existing unique provider mapping index and
the `(generation_id,taxon_id)` facts primary key. Reverse lookups retain
`ix_taxonomy_fact_taxon`; local name search uses the existing FTS5 index.
Care Guide import still evaluates exact-name JSON predicates across overlays and
the active generation; include this administrative path in performance qualification.
Ordinary JSON queries remain supported. No table, payload, permanent UUID,
mapping, immutable reference, search content or connection security setting changes.

## Databases already at 0024 or 0025

Alembic does not rerun a migration already recorded as applied. A development
database upgraded by the earlier 0024 may still have these three optional indexes.
It continues to work on its existing newer SQLite runtime with the corrected code;
their presence is an optimization difference, not a different data contract.
The revision remains 0024/0025; do not downgrade or replay historical migrations.

Before moving such a database to SQLite 3.40.1, stop its application writers and
use its **existing newer SQLite runtime** to remove only these indexes. Use the
normal authorized recovery and maintenance procedure for that database. Keep
`trusted_schema=OFF` and foreign keys enabled, then execute:

```sql
PRAGMA trusted_schema=OFF;
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
DROP INDEX IF EXISTS ix_taxonomy_fact_provider;
DROP INDEX IF EXISTS ix_taxonomy_overlay_name;
DROP INDEX IF EXISTS ix_taxonomy_fact_name;
COMMIT;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Verify integrity is `ok`, there are no FK violations, and protected rows, FTS
results and references are unchanged. Close that connection and qualify startup
and writes with the destination runtime. Do not open the legacy indexed schema
on SQLite 3.40.1 first and attempt to bypass its schema security checks.
Fresh upgrades from 0023 need no cleanup: corrected 0024 never creates the indexes.

## Regression qualification

The Container gate executes
`scripts/qualification/sqlite_taxonomy_upgrade.py` against the built production
image's own application, migrations and SQLite library, without dev dependencies,
network, secrets or production volumes. It prints the actual SQLite version and
tests 0023 → 0024 → 0025, hardened fresh connections, integrity/FKs, schema
expressions, provider identity lookup plans, FTS and ordinary taxonomy writes.
The shared integration regression also checks optional-index cleanup on a newer
development runtime without changing data or the recorded migration revision.

Release qualification must additionally record the actual SQLite 3.40.1 result,
protected-data and attachment preservation, focused taxonomy/Natural History/Frog
checks and representative lookup/search timings. Successful tests using only a
newer development SQLite library do not establish this runtime compatibility.
