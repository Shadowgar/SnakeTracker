# M2 Container Evidence

- Source revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Environment: Docker Engine on x86_64 WSL2
- Reviewer: Codex automated verification; final CI state retained by PR #3
- Requirements: R-039, R-041
- Result: Pass

The amd64 image builds frozen and runs as non-root user `snaketracker` (host UID 1001). Migration
exits zero; web, worker, and Nginx become healthy; Nginx is published only on loopback. The final
persisted household database migrated forward from `0002_identity_household` to
`0003_phase2_review_hardening`; readiness returned `200`, the redundant stream index was absent,
and `http://localhost:18081/` served the login page with strict security headers. The retained
August 5 fresh-install evidence used port 8081; the current owner-facing WSL2 profile uses 18081
because Windows/Hyper-V subsequently reserved 8081.

The final emulated `linux/arm64` OCI build status is **pass-emulated** after registering the local
qemu-aarch64 binfmt handler from pinned image digest
`sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0`.
Descriptor digest: `sha256:c813e6b2813b8de9bf01b895ae4fa5e07c52b5a0c648461c1caafa5d022b198a`.
OCI archive SHA-256: `f7fa1d5e6af28c9b08da1547d605f3aad7a42ea5e15226abf36697a1aa8d5388`;
size: 108,037,632 bytes. Its descriptor is `linux/arm64`. This is compatibility evidence, not
native Raspberry Pi qualification, which remains **deferred** to Phase 7/pre-deployment.

The pinned container SQLite 3.40.1 exposed that JSON functions are unsafe in schema constraints
when `trusted_schema=OFF`. The migration now retains typed application validation without those
optional constraints, and a regression test protects minimum-runtime portability.
