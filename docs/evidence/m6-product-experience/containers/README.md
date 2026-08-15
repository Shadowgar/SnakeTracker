# Compose and ARM64 Qualification

Result: **Pass** on August 15, 2026.

The amd64 Compose stack at `http://localhost:8081` runs healthy and non-root as UID/GID 1001. The
preserved development database migrated to `0011_product_experience`; SQLite integrity is `ok` and
foreign-key violations are zero.

The frozen Dockerfile and lockfile produced a `linux/arm64` OCI image:

- manifest digest: `sha256:a4cb9ab7d9fcf52b5011237870dcaf0cfa83b6bbaa7be3fe750822c3b6a03a39`;
- archive SHA-256: `7c653cd027fe1e1c517faa80445f94f4f690ee1bdd8237ab49a8e7e4b1c5e7e7`;
- archive size: 134,224,384 bytes.

This proves ARM64 container compatibility only. Raspberry Pi deployment qualification remains M7.
