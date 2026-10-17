# X2 local taxonomy implementation

Authority: owner instruction to implement the X2 tranche, controlling implementation plan,
ADR-0046, R-098/R-099/R-102, and AT-TAXBAS-01. ADR statuses and protected architecture documents
remain unchanged. Base: `a6dc77242a4066864dbe1d72c50b76690a9a1b7e`.

Implementation sequence:

1. Preserve the existing `taxa` UUID parent and all FK dependants with an explicit transactional
   Alembic migration; relax its workflow-group restriction for reference-only taxonomy.
2. Add namespaced identity allocation, durable observations/revisions/conflict decisions and a
   bounded overlay. Retain useful labels in a dedicated indexed global taxonomy search.
3. Add staged reference facts, validated ancestry, serialized promotion/rollback and explicit
   generation-only cleanup. Shared durable search avoids a discarded-generation writer race.
4. Connect existing directory search/detail/live discovery to selected local taxonomy. Expose a
   local application port for future consumers; leave Animal eligibility and manual entry intact.
5. Add a bounded offline Darwin Core reader and explicit operator commands, using only synthetic
   archives during development. No downloader, new job queue, Natural History or Animal workflow.
6. Prove AT-TAXBAS-01 races, conflicting identities, freshness, rollback, cleanup and reference
   preservation; run the unchanged quality gate and hosted checks; open a focused development PR.

Qualification distinguishes synthetic development evidence from production archive rights,
production-sized capacity/backup qualification and deployment acceptance. No live database,
production migration/import, container restart, merge or X3 implementation is authorized.

Implementation decisions: a permanent search projection participates in the identity publication
transaction. Snapshot classification entries are scoped to the selected generation. Final
promotion validates changed identities through a cutoff and switches the reference pointer and
watermark atomically. Unknown source ordering remains visible; import time never ranks freshness.
Explicit conflict decisions retain distinct permanent identities rather than rewriting links.
