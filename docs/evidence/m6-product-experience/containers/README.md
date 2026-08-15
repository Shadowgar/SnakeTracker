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
