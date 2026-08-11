# M5 Docker and ARM64 Evidence

Result: **Pass**

Source revision: `f976b4622a0f72bd165c906cdc8ab5d72a399cc6`  
Environment: Docker Engine 29.1.3; Compose 2.40.3; WSL2 x86_64 laptop.  
Reviewer: Codex local qualification; owner acceptance pending.

The amd64 Compose lifecycle migrated the retained local database to `0009_operational_workflows`.
`web`, `worker`, and `nginx` were healthy; web and worker ran as `1001:1001`, Nginx as `101:101`;
readiness returned `{"status":"ready"}` at `http://localhost:8081/health/ready`.

An idle non-production resource sample measured approximately 59.14 MiB web, 38.13 MiB worker,
and 8.14 MiB Nginx. These are development observations, not Raspberry Pi qualification.

The linux/arm64 OCI build completed with:

- descriptor platform: `linux/arm64`
- image digest: `sha256:c5bd7bf40915068b67f6f412c62c8c78b263e866ffacdfbacb11eda3b82ea2d7`
- archive size: 133,572,096 bytes

Reproduce:

```sh
docker compose up --build -d
docker compose ps
curl -fsS http://localhost:8081/health/ready
docker run --privileged --rm \
  tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0 \
  --install arm64
docker buildx build --platform linux/arm64 --build-arg SNAKETRACKER_UID=1001 \
  --output type=oci,dest=/tmp/snaketracker-m5-arm64.oci.tar \
  --metadata-file /tmp/snaketracker-m5-arm64-metadata.json .
```

Native Raspberry Pi execution, SSD/ext4 placement, thermal behavior, and deployment performance
remain mandatory but deferred to Phase 7/pre-deployment.
