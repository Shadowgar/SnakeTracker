# Replacement X1 architecture amendment proposal

Authority: Owner implementation directive dated October 15, 2026; exact-content approval pending.
Review status: Pending owner review

The owner withdraws the privileged-supervisor/raw-device direction and authorizes a practical
animal capability foundation on conventional web/worker startup. This package proposes the
smallest additive clarifications and stale-status corrections in eight protected files. The
other four protected documents remain unchanged. ADR-0045/0046/0047 retain Proposed status;
accepted decisions and the architecture-freeze validator are unchanged.

Review the [unapplied exact patch](2026-10-15-course-correction.patch) and
[base/target hash manifest](2026-10-15-amendment-manifest.json). The patch is not applied to the
implementation branch. Protected originals and their existing approvals remain intact.

Patch SHA-256: `056da15ee8841351b5821fe6aaca3eeb225b75f66d01080766e89f1adf3288d7`

| Proposed file | Target SHA-256 |
|---|---|
| `docs/README.md` | `d542c0c09d8b9f492af1736737a8ad2c7928bf6e5e494675b88372bdb2072268` |
| `docs/adr/0045-extensible-animal-capability-evolution.md` | `4cae40e86e2af504b62a619da2f63746d64ffdab9800887fc4e8243b750aa71b` |
| `docs/adr/README.md` | `f3a6242c0ca8f5ad5a1cb4cf70da1a77ba0ce9377d55faeaffc290d7e9cc01ee` |
| `docs/operations/backup-and-restoration.md` | `ac92e7151524677e2657b7bfdcb69a56630187bc4bb6f589fd9f75877cf5dd47` |
| `docs/operations/runtime-operations.md` | `7f7e6ba784985138ea2ea40eff2838ed3eb79e767d33b9689e3c541083726bba` |
| `docs/plans/2026-10-01-extensible-animal-and-species-platform.md` | `2e1c51f0223dfd48049e4b97c09ffba4619838130e423d31db971499dcb59919` |
| `docs/requirements/traceability-matrix.md` | `e8649ed5b591299035ab6a2693a9bf93c84966e6f5376dc430f5c772983d701a` |
| `docs/roadmap/milestones.md` | `26db7cfc307504346410863bbab97a1ad15a2f8bdc46da91c7cfa1ac64487758` |

The package distinguishes taxonomy, workflow identity, current individual subjects, future
groups/colonies and shared environments. It preserves application-level compatibility, historical
decoding, least-privilege container controls, immutable histories and practical backup/recovery.
Normal SQLite WAL/SHM bookkeeping is explicitly permitted; no business writes are allowed on
compatibility rejection. The withdrawn kernel-level guarantees are not release prerequisites.

The [approval template](2026-10-15-owner-approval-template.md) is deliberately Pending. A separate
explicit owner decision must approve these exact bytes before applying the patch and binding
the resulting file hashes under ADR-0028. No acceptance date or Accepted review is invented here.
After approval, apply exactly this patch, publish approved evidence, and rerun governance/full
qualification against the resulting final tree. Replacement PR review may proceed with this
package pending; merge and deployment remain prohibited.
