# M4 Docker and ARM64 Evidence

Result: **Pass**

The amd64 Compose stack built from the frozen `uv.lock`, migrated through `0008_local_backups`, ran
web and worker as non-root user `snaketracker`, and served liveness/readiness through Nginx. The
canonical local mapping is `127.0.0.1:8081 -> nginx:8080`; the external URL is
`http://localhost:8081`.

The same Dockerfile and lockfile produced a linux/arm64 OCI image under the pinned local binfmt
emulator:

- descriptor: `sha256:4d5fc2bb8e20671a52e1a95720967d129dd04c1e85b9041c53ca8509e7a14f7c`;
- OCI archive SHA-256: `e3d3cab6bf12c0334dbefb5dc285e17844a8119947d33819c3997bb23d594c33`;
- archive size: 133,036,544 bytes; and
- descriptor platform: `linux/arm64`.

Reproduction:

```sh
docker run --privileged --rm \
  tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0 \
  --install arm64
docker buildx build --platform linux/arm64 --build-arg SNAKETRACKER_UID=1001 \
  --output type=oci,dest=output/snaketracker-phase4-arm64.oci.tar \
  --metadata-file output/arm64-build-metadata.json .
```

This is ARM64 compatibility evidence only. It is not native Raspberry Pi execution, SSD/ext4,
thermal, throttling, or deployment-performance qualification.
