# Architecture baseline documentation and governance authorization

- Decision: ADR-0028
- Acceptance date: 2026-10-01
- Authority: Care Keeper owner instruction, "CLOSE THE EXTENSIBLE-ANIMAL ARCHITECTURE BASELINE"
- Review status: Accepted for documentation and governance tooling scope only
- Source revision: `1132dc8d0da42d1d4c13cee2052fb1b10575b82b`
- Instruction artifact: `57c1e219-16d1-4834-8673-9f054c9883f8/Pasted text.txt` supplied in this session

## Authorized scope

The owner directed capability-versus-taxonomy clarification, generic architecture-freeze validation,
focused governance tests, the normal full quality gate, and a commit of the architecture/documentation
baseline on `phase6.6/sourced-care-guides`. The instruction permits pushing the existing PR branch
and requires PR #17 to remain open, draft and unmerged. It expressly prohibits PR 1 product work,
production data/migrations/deployment, and M6.6-C.

This records the actual task authorization and binds the resulting frozen-package documentation
updates below. It does **not** record owner acceptance of ADRs 0044–0048, M6.6-A, M6.6-B or X1–X5.
The existing M6.6-A owner-acceptance evidence gap remains explicit. Proposed decisions remain Proposed.
No historical approval record or accepted ADR is rewritten.

## Validator checkpoint and evidence contract

The [generic validator](../../../scripts/quality/verify_architecture_freeze.py) retains the original
M0 baseline `bb3ab394a1487943424dad6d7544995c71156c98` and pins the prior gate's committed state at
the source revision above. It discovers the inherited catalog/status assertions from that immutable
Git checkpoint, rather than keeping ADR filename/date exceptions or treating moving HEAD as approval.
Inheritance preserves existing recorded assertions; it is not new acceptance evidence or retroactive
verification of milestone owner approval. Subsequent changes are compared to this fixed checkpoint.

The validator inspects HEAD, the Git index and working tree/untracked documentation independently.
It discovers numeric ADR files, validates filenames/title IDs, unique IDs/index links and statuses,
accepts the existing `Proposed for ...` qualifier, and requires acceptance dates for Accepted or
Superseded decisions. Unrelated Markdown notes are not ADRs. A superseded decision is retained,
with `Superseded by: ADR-NNNN` identifying an Accepted successor. Proposed additions need no owner
acceptance; index membership-only updates are validated structurally.

New Accepted/Superseded content, changes to inherited accepted ADRs, and other protected package
changes require a scoped record under `docs/evidence/` with the existing Markdown evidence fields:
`Decision: ADR-NNNN`, `Authority` recording the owner instruction/review, `Review status: Accepted`
(optionally qualified by scope), and a valid ISO `Acceptance date`. Each approved target is bound
using an `Approved file` / SHA-256 line as below. ADR acceptance/amendment must cite that ADR's ID;
a different decision or an old approval hash cannot authorize changed content. This content binding
adds no ADR database/framework and leaves historical evidence untouched. The gate checks recorded
authority and exact content; human review of the authority remains part of ADR-0028 governance.

The hashes below authorize these documentation updates under ADR-0028, not promotion of any Proposed
ADR. Tooling/tests and new proposed documents are linked from the
[controlling plan](../../plans/2026-10-01-extensible-animal-and-species-platform.md).

## Reviewed content scope

- Approved file: `docs/README.md` SHA-256: `352f8f97f76a9f8d1880d9af6486d1bf3cb3940a2b522ac68f50da6605f09554`
- Approved file: `docs/adr/README.md` SHA-256: `230863710eb52a7390979e8fba354b0f6eea7e6b1c94218749349e0b0e957a9a`
- Approved file: `docs/requirements/traceability-matrix.md` SHA-256: `1b88e436ebbebdb6dc2b4df69bdd96c13213fd66aa352a5ab9aa470fa1a340a7`
- Approved file: `docs/roadmap/milestones.md` SHA-256: `f5778a01f3cb4def2cd4024f3597d89cbfdedb697f846b6eb965f09a121a18da`

## Reproduction

```sh
uv sync --frozen
uv run pytest tests/unit/scripts/test_architecture_freeze.py -q
./scripts/quality/check.sh
git diff --check
```

The authorization above does not imply milestone acceptance. The following results record
technical qualification only; commit/PR state is reported separately.


## Local full-gate qualification

- Recorded UTC: 2026-10-01 06:54:15 UTC
- Operator: Codex under the owner instruction above
- Environment: current Care Keeper ARM64 workspace; disposable fixtures only
- Command: `uv sync --frozen` followed by the unchanged `./scripts/quality/check.sh`
- Locked environment: 75 packages checked

The disk-backed run completed with 741 passed, 117 warnings and one fixture setup error: the
password-recovery household-isolation test exceeded the existing 30-second timeout during Alembic
setup of `/tmp/pytest-of-rocco/.../password-recovery.sqlite3`. `/tmp` resides on the host SD card.
The same test passed in isolation: 2.68-second disk-backed setup versus 0.31-second RAM-backed setup.
This supports an I/O timing issue; no product, migration, timeout or gate code was changed to address it.

The full retry used isolated disposable fixtures in `/dev/shm/extensible-baseline-jpq9nv3z` via
`TMPDIR`. Reproduce the fixture placement using a fresh task directory:

```sh
task_fixture_tmp="$(mktemp -d /dev/shm/extensible-baseline-XXXXXX)"
TMPDIR="$task_fixture_tmp" ./scripts/quality/check.sh
```

The unchanged full gate returned **exit 0**: **742 passed, 117 warnings in 468.25 seconds**;
**94.52% line / 85.29% branch coverage**; no known dependency vulnerabilities; formatting, lint,
architecture, freeze, links, typing, Compose configuration and whitespace passed. Existing warnings
include Starlette deprecation and unclosed-SQLite ResourceWarnings. No tests, checks or timeout were
suppressed. These fixture results do not accept M7/native production-storage qualification.

Raw local logs: `/tmp/extensible-animal-baseline-quality.log` (disk-backed run) and
`/tmp/extensible-animal-baseline-quality-ram.log` (successful retry). The latter corresponds to the
source content hashes below; no product source differs from the source revision above.

- Qualified file: `scripts/quality/verify_architecture_freeze.py` SHA-256: `9608aa43152405488ec477676a34efa2324625262099eb531bc15489101956d4`
- Qualified file: `tests/unit/scripts/test_architecture_freeze.py` SHA-256: `118d40a2a88b86b222592ffde76826533e1d5cf7a11fce8b2416278139d5668f`
