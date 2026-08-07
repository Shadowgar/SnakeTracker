# M3 Container and ARM64 Evidence

The isolated amd64 image `sha256:932405ab26d5ed39409f1e037ce26e04273fe26745c08770042045fb6e8d12df`
builds with pinned bases, configures user `snaketracker`, and passes a
Compose lifecycle using a separate project, port, and database. Migration reaches
`0004_event_platform`; web, worker, and Nginx become healthy; liveness/readiness pass; restart
preserves readiness; and teardown completes. See `amd64-build.log`, `amd64-image.txt`, and
`compose-lifecycle.log`.

The linux/arm64 OCI build succeeds using the same Dockerfile and lockfile. Its descriptor digest is
`sha256:cc59ddab10290b2226b697bb7d5808311be56e55afb95cbe57b7d587fb6deab9`; the
108,296,704-byte archive SHA-256 is
`bf931412dbf57aec024b14513fb45373114923d09a3b7190ecbebbefdac13bf1`. Metadata is retained in
`arm64-build-metadata.json`. This proves container compatibility only. It is not native Raspberry
Pi execution, SSD, thermal, or performance evidence.
