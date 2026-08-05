# Container and ARM64 Evidence

- Requirements: R-001, R-024 foundation, R-041
- ADRs: ADR-0023, ADR-0024, ADR-0029 boundary, ADR-0036
- Threat controls: TM-14, TM-17, TM-18, TM-20
- Source revision: `da061911a7956892adbf8b5a1414e7407ce05b2a`
- Execution time: 2026-08-04T10:04Z through 2026-08-04T10:08Z
- Reviewer: Pending owner review

Results:

- amd64 build passed. Local image ID `sha256:8a6c5dd9f017f6ef37e61b07054c94425be873fb7f5a09fc45501b05a04eaeda`; 107,286,718 bytes; configured user `snaketracker`.
- emulated linux/arm64 OCI build passed. Manifest digest `sha256:3596144019dfafa3b11f29b17a8abac6cffff3cf8f095579485a05be614b9164`; OCI archive SHA-256 `a2fad8a562769855991b1adb061fe688807012f12c36f72750f49e248b9bcb08`; 105,647,104 bytes.
- The ARM64 descriptor in [arm64-build-metadata.json](arm64-build-metadata.json) identifies `linux/arm64`. This is compatibility evidence, not native Pi execution.
- The isolated qualification Compose project completed migration, brought web/worker/Nginx
  healthy, preserved the database and Alembic revision across restart, restored readiness, and
  shut down. The non-qualifying development run exceeded the idle CPU target; see
  [compose.log](../performance/development-host-warm/compose.log) and
  [results.json](../performance/development-host-warm/results.json).
- Nginx did not expose `/internal/metrics`; static contracts verify loopback-only publication, read-only roots, dropped capabilities, resource ceilings, health checks, secret-file use, and one web worker.
- Trivy `0.73.x` image digest `sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c` scanned the current amd64 image with `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`: zero matching vulnerabilities, exit 0. Raw output is retained in [trivy-scan.log](trivy-scan.log).

Raw build output is retained in [amd64-build.log](amd64-build.log) and [arm64-build.log](arm64-build.log).

These results satisfy the M1 amd64 runtime and ARM64 build requirements. Native Raspberry Pi
execution remains a separate Phase 7/pre-deployment qualification; see
[native-pi5-status.md](../performance/native-pi5-status.md).
