# M6.6 — Species-Aware Husbandry and Bioactive Care

Owner-approved September 13, 2026 and inserted after accepted M6.5 and before M7. Evidence is
tranche-specific. M6.6 is not accepted until A–E qualify and the owner explicitly accepts it.

- [M6.6-A — Universal directory](a-universal-directory/README.md)
- [M6.6-OPS-A — Read-only platform administration, accepted September 27, 2026](ops-a-platform-admin/README.md)
- [M6.6-B — Sourced Care Guides, accepted/complete October 5, 2026](b-sourced-care-guides/README.md)

OPS-A and B acceptance do not accept M6.6 as a whole. M6.6-B is Accepted / Complete; PR #17
merged at `4be4deb146314dd7613e296a9abb12db0c0daa6b`.
OPS-B and M6.6-C, D, E, and M7 have not begun.

## Pre-X1 documentation direction

- Decision: ADR-0028
- Acceptance date: 2026-10-05
- Authority: Care Keeper owner's explicit "PRE-X1 ARCHITECTURE RECONCILIATION" instruction supplied in this session.
- Review status: Accepted for the bounded owner-directed documentation amendment only; the resulting PR remains for owner review.
- Source revision: `4be4deb146314dd7613e296a9abb12db0c0daa6b`
- Instruction artifact: `04bedbda-5471-41ba-8ef9-c6df0ae8dc33/Pasted text.txt`

This is the normal content-bound governance record for the current documentation instruction,
not an architecture summary or a reconstructed audit. The owner supplied the reconciliation
conclusions and directed updates to existing authoritative documents. No retained X1–X3 audit
transcripts were located; their independent contents are not asserted or fabricated.

The [controlling plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md), Proposed
ADRs 0045–0047, roadmap, requirements and directly relevant runbooks carry the contracts. This
record binds the resulting documentation under ADR-0028 without promoting Proposed decisions.
ADRs 0044/0048 stay Accepted and unchanged; ADRs 0045/0046/0047 stay Proposed. Historical B
acceptance and the M6.6-A owner-artifact caveat remain intact. Runtime, schema, events, production
and local workspace configuration are unchanged. X1–X5 implementation remains unstarted.
The authorized result is a focused documentation PR, no merge and no X1 work.

### Content-bound documentation scope

- Approved file: `docs/README.md` SHA-256: `be28381543d895a783990abda4c3887c397953257fa6889617d6a1e1f9932087`
- Approved file: `docs/adr/0045-extensible-animal-capability-evolution.md` SHA-256: `ffba91f501ddeee1c3df339c84c5b60d7e1f700186b536f0f8f4003279fe4b63`
- Approved file: `docs/adr/0046-local-taxonomy-snapshot-and-provider-overlay.md` SHA-256: `dd6d2f9f6541bbd482a05eadaf976c24a973939a7c63c51f9e9d14176f8a53ea`
- Approved file: `docs/adr/0047-natural-history-reference-boundary.md` SHA-256: `1a82812c4366c9eecea4c57565bc95e062348fcc84cea1ab91c6dbc096779b79`
- Approved file: `docs/operations/backup-and-restoration.md` SHA-256: `6b9c0e6236a7a33bb2cfb291830f3fd6c044739c818a3aeec119048466e22c45`
- Approved file: `docs/operations/care-guide-sources.md` SHA-256: `df2befe48db0d7de40770fde1661b0758a52d8eb9ff1e14404d88e0dd74d4443`
- Approved file: `docs/operations/runtime-operations.md` SHA-256: `a1b844fe68f135ae6366b18d108019800ea533bb670d287f0d9cc9208de26659`
- Approved file: `docs/operations/taxonomy-snapshot-refresh.md` SHA-256: `36b91bf0cf3042c820c4a0f610a871044562cba2bf531b59a980faa10b354b1f`
- Approved file: `docs/plans/2026-10-01-extensible-animal-and-species-platform.md` SHA-256: `9618760e186891a24a6c9b3c2645c4d2578129330cd199b1710a34f2f11b9477`
- Approved file: `docs/requirements/traceability-matrix.md` SHA-256: `617012a035601a73391b18bcc19a8a1342d3b6bff7dfbe101464c69706123629`
- Approved file: `docs/roadmap/milestones.md` SHA-256: `c800fcf54a3871127b80032b3db8ad88507cdd850ab18df59a00f18f14ebc76f`

### Reconciliation qualification — October 5

`uv sync --frozen` checked 75 packages. The entire unchanged `./scripts/quality/check.sh` passed
(exit 0): **900 tests passed**, zero failures/errors/skips, 172 warnings in 578.62 seconds;
**94.55% line / 85.39% branch coverage**. Formatting, Ruff, architecture, ADR/index/status and
content-bound freeze, traceability/docs links (239 files), mypy (154 source files), coverage,
dependency audit (no known vulnerabilities), Compose configuration and diff hygiene passed.

Disposable fixtures used a private `/dev/shm/pre-x1-quality-*` directory through `TMPDIR`, following
the prior qualified fixture placement; no script, threshold or timeout changed. This does not qualify
production scratch-space reliability. Local raw log: `/tmp/pre-x1-reconciliation-20261005/quality.log`.
Only documentation/governance changed; accepted ADRs 0044/0048, application/migration/runtime files
and local workspace bytes/permissions/tracking are unchanged. This is regression qualification,
not X1–X3 implementation acceptance or production deployment evidence. PR/head CI is verified
separately before marking the documentation PR ready for owner review.
