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
- Authority: Care Keeper owner post-result review and approval of PR #18 at `93a871c57bbe105045adb394e60f603aab98e51e`, followed by the explicit "FINALIZE PRE-X1 ARCHITECTURE RECONCILIATION" instruction and owner review and approval of the narrow Codex P2 clarification on 2026-10-05.
- Review status: Accepted for the bounded Pre-X1 documentation reconciliation and owner-reviewed P2 ownership clarification; approval covers only the exact revised controlling-plan and ADR-0046 contents and the nine unchanged approved documents bound below.
- Source revision: `97ad89c27ca602fbf17f503e80ce230abf42f072` plus the narrowly approved X2/X3 source-association clarification
- Branch creation base: `4be4deb146314dd7613e296a9abb12db0c0daa6b`
- Instruction artifact: `dc1ebed8-8b3a-45fd-8847-6afc93aa5569/Pasted text.txt`
- Original post-result approval artifact: `166543f0-0a20-402b-a81a-cfc46418b0c5/Pasted text.txt`
- Original direction artifact: `04bedbda-5471-41ba-8ef9-c6df0ae8dc33/Pasted text.txt`

The owner reviewed the completed resulting PR before giving this October 5 approval. This
post-result review initially authorized 11 unchanged reviewed documents under ADR-0028. The owner
then reviewed and approved the Codex P2 ownership clarification on October 5: X2 owns taxonomy
provider/source references; X3 owns durable Natural History source associations. This narrow
approval revises only the controlling plan and ADR-0046; nine original approved contents remain
unchanged, including byte-identical ADR-0047. The current bindings below were independently
computed from the resulting files: 11 protected documents, two revised hashes, nine unchanged
hashes and zero unexpected changes. No unrelated architecture change or implementation is approved.
The earlier direction authorized preparation,
but marking those hashes Accepted while the PR still awaited owner review was premature. This
record corrects that sequencing; it does not treat preparation authority as post-result acceptance.
No retained X1–X3 audit transcripts were located; their independent contents are not asserted or
fabricated. The owner's supplied reconciliation conclusions remain the documentation input.

The [controlling plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md), Proposed
ADRs 0045–0047, roadmap, requirements and directly relevant runbooks carry the contracts. This
record binds the resulting documentation under ADR-0028 without promoting Proposed decisions.
ADRs 0044/0048 stay Accepted and unchanged; ADRs 0045/0046/0047 stay Proposed. Historical B
acceptance and the M6.6-A owner-artifact caveat remain intact. Runtime, schema, events, production
and local workspace configuration are unchanged. X1–X5 implementation remains unstarted.
Pre-X1 documentation reconciliation is **Approved / Complete**. The post-review instruction
now authorizes the evidence correction, exact P1/P2 thread resolution, full validation, protected-head
merge of PR #18 and production-source synchronization to merged main. Integration state is verified
in GitHub after those gates; this record does not claim a merge before it occurs. Approval does not
accept X1/X2/X3 implementation or begin X1. The next implementation tranche is X1 — Extensible Animal
Capability Foundation, under a separate instruction; this task stops before its implementation.

### Content-bound documentation scope

- Approved file: `docs/README.md` SHA-256: `be28381543d895a783990abda4c3887c397953257fa6889617d6a1e1f9932087`
- Approved file: `docs/adr/0045-extensible-animal-capability-evolution.md` SHA-256: `ffba91f501ddeee1c3df339c84c5b60d7e1f700186b536f0f8f4003279fe4b63`
- Approved file: `docs/adr/0046-local-taxonomy-snapshot-and-provider-overlay.md` SHA-256: `364636517008767b754dac7396b3ff73c734a672d4887c5cbe7883002230aeaf`
- Approved file: `docs/adr/0047-natural-history-reference-boundary.md` SHA-256: `1a82812c4366c9eecea4c57565bc95e062348fcc84cea1ab91c6dbc096779b79`
- Approved file: `docs/operations/backup-and-restoration.md` SHA-256: `6b9c0e6236a7a33bb2cfb291830f3fd6c044739c818a3aeec119048466e22c45`
- Approved file: `docs/operations/care-guide-sources.md` SHA-256: `df2befe48db0d7de40770fde1661b0758a52d8eb9ff1e14404d88e0dd74d4443`
- Approved file: `docs/operations/runtime-operations.md` SHA-256: `a1b844fe68f135ae6366b18d108019800ea533bb670d287f0d9cc9208de26659`
- Approved file: `docs/operations/taxonomy-snapshot-refresh.md` SHA-256: `36b91bf0cf3042c820c4a0f610a871044562cba2bf531b59a980faa10b354b1f`
- Approved file: `docs/plans/2026-10-01-extensible-animal-and-species-platform.md` SHA-256: `15f64f090fece4358c7e865c9f95524f2e00812e6c6b8317f528310066ba7d27`
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

### Post-review finalization qualification — October 5

The post-result owner-approval correction passed `uv sync --frozen` (75 packages) and the entire
unchanged `./scripts/quality/check.sh` (exit 0): **900 tests passed**, zero failures/errors/skips,
172 warnings in 580.43 seconds; **94.55% line / 85.37% branch coverage**. Governance/ADR/index/status,
traceability/docs links, formatting/Ruff, mypy, coverage, dependency audit (no known vulnerabilities),
Compose configuration and diff hygiene passed. At that qualification, all 11 reviewed target
contents and hash entries remained identical to the owner-reviewed PR head; only this evidence
record changed. The separately approved P2 clarification above subsequently revises two bindings.

Disposable fixtures again used private RAM scratch through `TMPDIR`; no threshold, timeout,
validator, runtime or production setting changed. Raw local log:
`/tmp/pre-x1-finalization-20261005/quality.log`. Exact-head hosted checks, the specified P1 thread
resolution, merge and production-source preservation are verified separately before integration.

### Approved P2 ownership clarification qualification — October 5

The owner-approved X2/X3 clarification passed `uv sync --frozen` (75 packages) and the entire
unchanged `./scripts/quality/check.sh` (exit 0): **900 tests passed**, zero failures/errors/skips,
172 warnings in 581.01 seconds; **94.55% line / 85.39% branch coverage**. Governance/ADR/index/status
and content-bound freeze, traceability/docs links (239 files), formatting/Ruff, mypy (154 source
files), coverage, dependency audit (no known vulnerabilities), Compose configuration and diff
hygiene passed. Exactly the controlling plan, ADR-0046 and this governance record changed in the
clarification; the protected-file comparison is 11 total, two revised, nine unchanged and zero
unexpected changes. ADR-0047 remains byte-identical.

Disposable fixtures used private RAM scratch through `TMPDIR`; no validator, threshold, timeout,
runtime or production setting changed. Raw local log:
`/tmp/pre-x1-source-clarification-20261005/quality.log`. Result-metadata additions were followed by
fresh governance and documentation checks. New-head hosted checks, the exact P2 thread resolution,
protected-head merge and read-only production/source-preservation comparison are verified
separately before integration. This qualifies documentation reconciliation only; it does not
accept X1–X3 implementation or begin X1.
