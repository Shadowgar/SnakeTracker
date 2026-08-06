# M3 Container and ARM64 Evidence

The isolated amd64 image `sha256:f38675856a64071acbcbdf4dc5109778bdd3cde76e8668fcefca9d212acfd435`
builds with pinned bases, configures user `snaketracker`, and passes a
Compose lifecycle using a separate project, port, and database. Migration reaches
`0004_event_platform`; web, worker, and Nginx become healthy; liveness/readiness pass; restart
preserves readiness; and teardown completes. See `amd64-build.log`, `amd64-image.txt`, and
`compose-lifecycle.log`.

The linux/arm64 OCI build succeeds using the same Dockerfile and lockfile. Its descriptor digest is
`sha256:345cfcf16ee3691c76f4e1b09bc098f55ea9633b49b0e1ac5b98b29bbbd72b14`; the
108,270,592-byte archive SHA-256 is
`83e2715f402cb8680a75da23d2177c631eaeb3e9a008c1fbbfede6d5fdbcbe0b`. Metadata is retained in
`arm64-build-metadata.json`. This proves container compatibility only. It is not native Raspberry
Pi execution, SSD, thermal, or performance evidence.
