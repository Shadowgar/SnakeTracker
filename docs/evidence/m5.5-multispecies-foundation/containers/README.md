# Docker Compose and ARM64 Qualification

Result: **Pass**, requalified on August 15, 2026 at revision `ebd5200`.

The amd64 Compose lifecycle rebuilt and migrated the preserved development database to 0010. Web,
worker, and Nginx became healthy; `/health/live` and `/health/ready` passed; SQLite integrity was
`ok` with no foreign-key violations. The application process runs as UID/GID 1001.

The same Dockerfile and frozen lockfile produced an OCI descriptor for `linux/arm64`:

- image digest: `sha256:35288f3cc254936cbf8eed3652b14e6562031f00b9acd39bb3011c94ca8e2831`;
- archive SHA-256: `0e81262378a64e24b9fb3b25b45790a6cf01e58133658c00fa4f305bbc1b3b9a`;
- archive size: 133,727,232 bytes;
- configured runtime user: `snaketracker` (UID 1001 in the qualified build).

The first final-review ARM64 attempt exposed missing host QEMU/binfmt registration after a Docker
restart. Restoring the laptop's `arm64` emulator and rerunning the identical build succeeded; this
is a development-host prerequisite, not an application-code failure.

See [ARM64 build metadata](arm64-build-metadata.json). This proves container compatibility, not
native Raspberry Pi deployment qualification.
