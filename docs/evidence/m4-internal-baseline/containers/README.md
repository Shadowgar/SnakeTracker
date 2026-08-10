# M4 Docker and ARM64 Evidence

Result: **Pass**

The amd64 Compose stack built from the frozen `uv.lock`, migrated through `0008_local_backups`, ran
web and worker as non-root user `snaketracker`, and served liveness/readiness through Nginx. The
canonical local mapping is `127.0.0.1:8081 -> nginx:8080`; the external URL is
`http://localhost:8081`.

The same Dockerfile and lockfile produced a linux/arm64 OCI image under the pinned local binfmt
emulator:

- corrected-UX descriptor: `sha256:397646919b1b06d2d7a6693ad99672761fad55541a37137fbe9081481dcccd98`;
- corrected-UX OCI archive SHA-256: `18fa4c47d5fe2f498dfb0e1de8a31771e200b7cd027cccc46b06d77843b130bb`;
- corrected-UX archive size: 133,067,264 bytes; and
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
  --output type=oci,dest=output/snaketracker-phase4-arm64.oci.tar \
  --metadata-file output/arm64-build-metadata.json .
```

This is ARM64 compatibility evidence only. It is not native Raspberry Pi execution, SSD/ext4,
thermal, throttling, or deployment-performance qualification.
