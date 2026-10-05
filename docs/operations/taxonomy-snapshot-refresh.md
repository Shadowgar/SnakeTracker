# Taxonomy snapshot refresh — planned operator procedure

Status: Planned; no import command or production promotion exists yet. Applies to the official
[iNaturalist Taxonomy DarwinCore Archive](https://www.inaturalist.org/pages/developers) after
[ADR-0046](../adr/0046-local-taxonomy-snapshot-and-provider-overlay.md) is implemented. Follow
[ADR-0018](../adr/0018-backup-and-restoration.md) and
[ADR-0026](../adr/0026-migration-and-rollback.md) for production data protection.

ADR-0046 owns durable identity, generation/overlay freshness, concurrency and rollback semantics;
this runbook owns operations. A/B are replaceable reference generations. The permanent catalog,
provider mappings/retained labels, durable overlay, Animal/Plant/guide/media references and X3
content/source/publication state are outside their rollback/cleanup scope. X2 owns selected names/
classification/provenance; X3 consumes permanent UUIDs and cannot select taxonomy independently.

1. Qualify the actual archive, intended use, provenance and attribution/rights policy; do not
   assume CC0. Resolve the official HTTPS archive endpoint and current terms/licence. Download into
   isolated
   staging outside active database, attachments and reference generation paths. Record URL,
   retrieval time, announced snapshot date, import time, byte count and checksum; bound download
   size. Keep these dates distinct; later import does not make source facts newer.
2. Validate TLS origin, response status/type, actual file type, checksum when published, and a
   locally computed checksum. Reject unexpected redirects or mismatched files.
3. Inspect archive entries before extraction. Reject absolute paths, `..`, symlinks, duplicate
   paths and unsupported members; enforce compressed/expanded byte, file-count and time bounds.
   Extract into an isolated directory with no active-data write privileges.
4. Validate DarwinCore metadata/schema and required taxon/name/parent fields. Parse bounded rows,
   normalize provider IDs, accepted names, common names, synonyms, ranks and parentage; detect
   missing parents, cycles, duplicates and invalid encodings. Record import errors, never infer
   absent values.
5. Record B's catalog/overlay starting revision watermark. Reserve/reuse permanent UUIDs through
   transactional namespaced provider get-or-create mappings under ADR-0046. Stage name-only,
   homonym and split/lump candidates for review; missing archive entries do not authorize deletion.
   Record changed names/parents, inactive/replacement candidates and provenance without rewriting
   registrations or Animal/Plant/guide links. Protect fresher overlay facts from older snapshots.
6. Build a new local SQLite reference generation with indexed normalized names and FTS/search
   structures. Validate counts, ancestry, known four-group and Amphibia samples, aliases, exact
   detail, cold/warm autocomplete, provider overlay and manual no-result behavior. Verify storage,
   CPU and RAM on the Pi. Include ancestors/taxa with no enabled Animal group and catalog fallback
   for references absent from B. A keystroke query must not scan all taxa. Live discoveries continue
   to publish permanent identity and overlay/search deltas atomically while B stages.
7. Before production promotion, complete the controlling plan's isolated encrypted-backup restore,
   applicable upgrade, replay, projection and semantic compatibility manifest at a common cutoff/
   controlled clock, even without Alembic. Rehearse B-introduced taxon → link/content → rollback A
   with useful retained labels/search, live discovery during staging/promotion, cleanup protection and failed reconciliation. Keep normal
   profiles and manual creation available locally during refresh, with zero outbound profile calls.
8. Reconcile deltas since B's starting watermark. Use a bounded SQLite writer transaction shared
   by identity/overlay publication and promotion: capture the final cutoff, reconcile through it,
   verify durable references and combined search, then atomically promote B plus its search watermark.
   No distributed lock is needed. Abort/defer on timeout, unresolved identity conflict or failed validation; leave A active. Publish subsequent discoveries
   against B after transaction completion. Retain A for rollback and verify links/search after promotion.
   Roll back only the reference/search pointer using ADR-0046's reconciliation protocol; catalog and
   live overlay remain current, including discoveries and X3 content created after A. Never restore
   over active household data as a test.
9. Remove only expired generation content/indexes under explicit retention after rollback/backup
   windows expire. Never delete referenced catalog identities/mappings, links, guide versions or
   local assets or X3 associations/versions/publication as generation cleanup. Record checksums,
   all three dates, schema/import version,
   source/licence, reviewer, reconciliation cutoffs, before/after metrics and rollback evidence.

Live iNaturalist calls remain bounded by the
[API recommended practices](https://www.inaturalist.org/pages/api%2Brecommended%2Bpractices)
and ADR-0043; do not use the API to reconstruct the archive. Only public scientific queries may
leave Care Keeper. No import, download or production action is part of the documentation pass.

Before production-sized import, the [backup release gate](backup-and-restoration.md#extension-release-gates)
requires measured database/generation/index size, WAL, scratch high water, memory/duration, restore
compatibility/replay and normal-duty impact. Synthetic fixtures qualify development, not production
archive rights or production-scale backup reliability. Initial import remains a bounded operator
workflow; no new queued job is required merely to implement X2.
