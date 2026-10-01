# Immutable attachment backup qualification

Authority: owner's October 1 immutable attachment backup release-blocker request.
Scope: backup correctness and one worker-created recovery point; product deployment remains deferred.

The historical backup `bfb0efc2-0b0b-4718-b2b1-88e7d1be2970` contains only 40 currently
selected photos and omits six legitimate finalized versions. Its historical evidence is retained.

## Required recovery invariant

The completed SQLite copy defines membership: every `attachment_versions` row must correspond
to exactly one encrypted manifest attachment, matching version ID, storage key, media type,
SHA-256 and size. Deterministic selection reads that copy, without a current-photo join or
filesystem discovery. Staged content is excluded. Missing, corrupt or unsupported finalized
content fails creation; manifest omissions, extras and duplicates fail verification. Restore
re-reads all restored finalized files and verifies their hashes and sizes against restored metadata.
The existing [backup runbook](../../../../operations/backup-and-restoration.md), AES-GCM format,
attachment lifecycle and schema remain authoritative.

## Bounded worker execution

Prepare a detached source at deployed revision `c4740b32c1b80f054725c0a037d47689bc283474`
plus only the qualified backup correction and required tests/tooling. Record the exact source SHA
and restricted diff. Build `deploy/docker/backup-worker.Dockerfile` from that source using the
existing deployed image, adding only the corrected pipeline and backup-only entry point.
Verify installed/source pipeline hashes and qualify the artifact on an isolated fictional fixture.

Briefly stop only the original worker, enqueue the existing application backup request and run
the temporary image once with original runtime/secrets mounts and `--no-deps`. Its entry point
requires the exact source/request, compatible data, no other pending requests and no due schedule.
It invokes the existing factory and leased backup worker, without product startup, migrations,
projection advancement or reminder/notification work. Always restart the same original worker in
a finally/trap, including on failure. Web/nginx and `.env` remain unchanged. Restore only to a
private isolated destination; record actual cutoff counts, metadata/file equality, compatibility,
bounded application smoke checks and before/after production integrity.

## Qualification status

Focused reproduction and correction tests are recorded privately pending the full gate and
production qualification. This document does not yet claim a complete production recovery point.
ADR-0044, ADR-0048 and M6.6-B remain unaccepted; PR #17 remains draft and unmerged.
