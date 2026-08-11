# Docker Compose and ARM64 Qualification

Result: **Pass** on August 11, 2026 at revision `fe4a476`.

The amd64 Compose lifecycle rebuilt and migrated the preserved development database to 0010. Web,
worker, and Nginx became healthy; `/health/live` and `/health/ready` passed; SQLite integrity was
`ok` with no foreign-key violations. The application process runs as UID/GID 1001.

The same Dockerfile and frozen lockfile produced an OCI descriptor for `linux/arm64`:

- image digest: `sha256:1b505606c2cf3a649ec40a1f999d684b5e3475c002a5d4d4bb6f2f1fc9ceb5b6`;
- archive SHA-256: `28afdbf054c54a6a1515c8ef95a1b5645753bafc7d4622808b4b1df2de91b809`;
- archive size: 133,724,672 bytes.

See [ARM64 build metadata](arm64-build-metadata.json). This proves container compatibility, not
native Raspberry Pi deployment qualification.

