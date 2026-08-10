# M4 Docker and ARM64 Evidence

Result: **Pass**

The amd64 Compose stack built from the frozen `uv.lock`, migrated through `0008_local_backups`, ran
web and worker as non-root user `snaketracker`, and served liveness/readiness through Nginx. The
canonical local mapping is `127.0.0.1:8081 -> nginx:8080`; the external URL is
`http://localhost:8081`.

The same Dockerfile and lockfile produced a linux/arm64 OCI image under the pinned local binfmt
emulator:

- final descriptor: `sha256:cd43e8c4775433cb3ed8c81d4b587d4c700f96e29312889b83a66f3be3423218`;
- final OCI archive SHA-256: `99aa108973dcb39105a819b9d496f001c40db452c72963b59c206ffa6392cb36`;
- final archive size: 133,098,496 bytes; and
- descriptor platform: `linux/arm64`.

The final amd64 Compose image restarted successfully with persisted data, web and worker ran as
non-root `snaketracker`, Nginx ran as `101:101`, all three services became healthy, SQLite returned
`integrity_check=ok`, and the live mapping remained `127.0.0.1:8081`. Trivy 0.69.3 found zero fixed
high or critical vulnerabilities.

Reproduction:

```sh
docker run --privileged --rm \
  tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0 \
  --install arm64
docker buildx build --platform linux/arm64 --build-arg SNAKETRACKER_UID=1001 \
  --output type=oci,dest=output/snaketracker-phase4-arm64-enclosure.oci.tar \
  --metadata-file output/arm64-enclosure-build-metadata.json .
```

This is ARM64 compatibility evidence only. It is not native Raspberry Pi execution, SSD/ext4,
thermal, throttling, or deployment-performance qualification.
