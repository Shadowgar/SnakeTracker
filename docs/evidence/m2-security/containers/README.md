# M2 Container Evidence

- Retained container-run source revision: `0bcbc801c2f7fbfed0812f6ad0212eba209f307c`
- Review-correction revision: `25d52a34ce3cb343d1678de75118863d844d80b5`
- Environment: Docker Engine on x86_64 WSL2
- Reviewer: Codex automated verification; final CI state retained by PR #3
- Requirements: R-039, R-041
- Result: Pass

The amd64 image builds frozen and runs as non-root user `snaketracker` (host UID 1001). Migration
exits zero; web, worker, and Nginx become healthy; Nginx is published only on loopback. The final
fresh-install route returns `303 /setup`, and `http://localhost:8081/setup` returns the first-run
page with strict security headers. This retained August 5 run used port 8081; the current
owner-facing WSL2 profile uses port 18081 because Windows/Hyper-V subsequently reserved 8081.

The final emulated `linux/arm64` OCI build status is **pass-emulated** after registering the local
qemu-aarch64 binfmt handler. Descriptor digest:
`sha256:4b28276c1863b4a8580cb82b529746293f767cf9ff7edeb7a151a5998298a51f`.
OCI archive SHA-256: `0aac2380dc6c5495d89690d8c3f7d5ce35776e1c9d8c1cff1967a2343f6ed580`;
size: 108,032,512 bytes. Its descriptor is `linux/arm64`. This is compatibility evidence, not
native Raspberry Pi qualification, which remains **deferred** to Phase 7/pre-deployment.

The pinned container SQLite 3.40.1 exposed that JSON functions are unsafe in schema constraints
when `trusted_schema=OFF`. The migration now retains typed application validation without those
optional constraints, and a regression test protects minimum-runtime portability.
