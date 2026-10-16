# X1 architecture course correction — exact-content owner approval

Authority: Explicit owner approval in the Care Keeper X1 Architecture Course Correction Approval directive
Review status: Accepted for exact-content architecture alignment only
Acceptance date: 2026-10-16
Decision: ADR-0028 content-bound amendment approval; no ADR status promotion

The owner approved the exact eight-document amendment proposed in PR #22 at
`afa2e08d059bdb64ad5f254f55f8450ed22e56bd`, including every target hash in the
[reviewed manifest](2026-10-15-amendment-manifest.json).

Approved patch SHA-256: `056da15ee8841351b5821fe6aaca3eeb225b75f66d01080766e89f1adf3288d7`

- Approved file: `docs/README.md` SHA-256: `d542c0c09d8b9f492af1736737a8ad2c7928bf6e5e494675b88372bdb2072268`
- Approved file: `docs/adr/0045-extensible-animal-capability-evolution.md` SHA-256: `4cae40e86e2af504b62a619da2f63746d64ffdab9800887fc4e8243b750aa71b`
- Approved file: `docs/adr/README.md` SHA-256: `f3a6242c0ca8f5ad5a1cb4cf70da1a77ba0ce9377d55faeaffc290d7e9cc01ee`
- Approved file: `docs/operations/backup-and-restoration.md` SHA-256: `ac92e7151524677e2657b7bfdcb69a56630187bc4bb6f589fd9f75877cf5dd47`
- Approved file: `docs/operations/runtime-operations.md` SHA-256: `7f7e6ba784985138ea2ea40eff2838ed3eb79e767d33b9689e3c541083726bba`
- Approved file: `docs/plans/2026-10-01-extensible-animal-and-species-platform.md` SHA-256: `2e1c51f0223dfd48049e4b97c09ffba4619838130e423d31db971499dcb59919`
- Approved file: `docs/requirements/traceability-matrix.md` SHA-256: `e8649ed5b591299035ab6a2693a9bf93c84966e6f5376dc430f5c772983d701a`
- Approved file: `docs/roadmap/milestones.md` SHA-256: `26db7cfc307504346410863bbab97a1ad15a2f8bdc46da91c7cfa1ac64487758`

The [reviewed patch](2026-10-15-course-correction.patch) is applied exactly. The October 15
proposal and pending template remain historical review artifacts; this dated record supplies
the subsequent explicit approval. The other four protected documents, historical governance
checkpoint, validator, and all ADR statuses remain unchanged. ADR-0045/0046/0047 remain Proposed.

The owner authorizes full unchanged quality and necessary regression, browser, compatibility,
and backup qualification, followed by committing and pushing qualified alignment to PR #22
and completing hosted checks for final owner merge review. This approval does not itself
establish qualification, milestone acceptance, or production readiness.

The practical capability foundation uses conventional application startup. Privileged supervisors,
BPF, raw-device filtering, and kernel-level writer-exclusion experiments are not X1 requirements.
The minor future-profile visual fallback mismatch remains deferred: a hypothetical registered
workflow group using `unknown` requests `unknown.webp`, while the neutral asset is `unknown.svg`.
Correct and qualify that mismatch before enabling additional production animal groups.

No automatic merge, PR #21 closure, production deployment, production data/configuration change,
Proposed ADR promotion, or X2 implementation is authorized. Stop before PR #22 merge,
production deployment, and X2 implementation.
