# Compose and ARM64 Qualification

Result: **Pass** on August 15, 2026.

The amd64 Compose stack at `http://localhost:8081` runs healthy and non-root as UID/GID 1001. The
preserved development database migrated to `0011_product_experience`; SQLite integrity is `ok` and
foreign-key violations are zero.

The frozen Dockerfile and lockfile produced a `linux/arm64` OCI image:

- manifest digest: `sha256:8eeb18e8a199adbf22c6991b1622c5cc6f403bc74e78a0f852e72d816e4400f7`;
- archive SHA-256: `f0cdfe04a4acfb07fa03f749533e6c4ad9f0908608b38c9d3479cb64a334d890`;
- archive size: 134,254,592 bytes.

This proves ARM64 container compatibility only. Raspberry Pi deployment qualification remains M7.

## Mobile-first correction requalification

The consolidated 8081 stack was rebuilt from runtime revision `0dc458d` on August 16, 2026. Web,
worker, and Nginx were healthy; liveness/readiness passed; web and worker ran as UID 1001; and the
web root filesystem remained read-only with all Linux capabilities dropped and
`no-new-privileges` enabled.

After restoring the documented pinned ARM64 binfmt handler, the same Dockerfile and frozen lockfile
produced a new `linux/arm64` OCI archive:

- image digest: `sha256:044bda8dcc557f8b2279800800195887719e150ce270bc8b627d6fe9572b560d`;
- config digest: `sha256:ccba9bf3286abe28a995f20b94a10582b21627d19295e55f870f5ebacb123ee1`;
- archive SHA-256: `906fbbf586aa680ef88196d78ed37c2c157ac06d8315a69c94b0b234a72303bb`;
- archive size: 134,301,696 bytes.

The first local attempt failed with `exec format error` because Docker had lost its binfmt/QEMU
registration. Reinstalling the previously documented pinned handler restored the laptop
prerequisite; the unchanged build then passed. This remains emulated compatibility evidence, not
native Raspberry Pi qualification.
