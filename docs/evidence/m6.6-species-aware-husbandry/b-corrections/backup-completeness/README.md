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
a finally/trap using `docker start` with its recorded existing container ID, including on failure.
Do not use `docker compose start worker`: this installation traverses its migration dependency.
Web/nginx and `.env` remain unchanged. Restore only to a
private isolated destination; record actual cutoff counts, metadata/file equality, compatibility,
bounded application smoke checks and before/after production integrity.

## Qualification status

The [sanitized qualification receipt](qualification-20261001.json) records the completed recovery
point and bounded production execution. No private photos, user records or key material are included.

- Backup correction: `606e8a2024674a9c9c1f3d9903b6f41d61c31199`; packaging follow-up and fully
  qualified head: `65a0b3d3d582a0ee15ce3beb6027eaee45bfe1ff`.
- Temporary worker source: `7d2f3de801c295cda2768fc8b913e2a30fc82326`, based on the deployed
  revision plus those two cherry-picked commits. The five-file diff is limited to pipeline,
  tests, runner, Docker recipe and this qualification note. All 3,759 application files in the
  image were compared; only the two pipeline copies and runner differ from the existing image.
- Initial fictional reproduction: four finalized versions, only two archived; A and never-selected
  C omitted. Fourteen initial regressions failed. Final focused suite: **29 passed**; the same
  suite against deployed-source-plus-fix also passed **29**. Existing wrong-key/tampering and
  leased-heartbeat coverage remains. Independent static review found no actionable code defect.
- Final full gate: **892 passed**, 172 warnings, 597.70s; **94.53% lines / 85.35% branches**.
  Frozen sync checked 75 packages; dependency audit, architecture/freeze, links, typing, Compose
  configuration and diff checks passed without altered thresholds/timeouts. An initial full gate
  also passed; the final gate follows the default-user Docker entrypoint permission correction.
- Exact image fictional rehearsal: **4 DB = 4 manifest = 4 restored**, zero hash/FK errors,
  original staged file preserved and staged content excluded; restored compatibility normal.
- Production run: **`8777f5b4-545e-4384-81e6-e50c99553bb8`**, completed
  **2026-10-01T09:05:08.866674+00:00**, cutoff **1027**, schema **0023_sourced_care_guides**.
  **46 DB = 46 manifest = 46 restored**, zero metadata/hash mismatches. All six versions missing
  from the historical archive are included. Encryption remains AES-256-GCM, key ID
  `local-development-v1` (the existing configured identifier; no key material recorded).
- Encrypted manifest SHA-256:
  `11878c2e09ed66b833a64543a2d2cc7b7fae44f7b9ea8cecf0a6498994aebd76`.
- Fresh isolated decrypt/restore: SQLite integrity `ok`, zero FK errors, empty sessions/reset
  credentials, no staged files, actual restored bytes all verified. Deployed application
  compatibility and projection registry passed; **1,373** application read dimensions, zero errors.
- During the backup, all **80** non-backup table dimensions were strictly unchanged; only
  `backup_requests` and `backup_runs` changed. All **46** attachment metadata/content records and
  all **77** attachment/reference media files are unchanged. Final normalized comparison has
  zero differences; normal worker restart refreshed only `reminder_facts.calculated_at`.
  Reminder rules/schedules, Inventory, Animal links and immutable business data remain unchanged.
  `.env` (0600), operator environment, original container IDs/images and web/nginx start times
  are unchanged. Original worker is healthy, with no pending request or remaining backup lease.

## Execution incident retained

The first isolated Docker build made the new entrypoint directory 0444 through COPY permissions;
the normal user could not traverse it. A packaging follow-up creates/chmods the directory 0755
before COPY. Default-user import, fixture backup/restore and final image qualification passed.
Production was untouched during that isolated failure.

After the successful live backup, the cleanup's `docker compose start worker` unexpectedly started
the pre-existing `snaketracker:m66-a-interaction-c1` migration dependency. It exited 255 because it
could not locate already-installed revision `0023_sourced_care_guides`, with zero upgrade messages.
This command attempt was outside the intended execution path. The original worker was immediately
restarted directly with `docker start snaketracker-worker-1`; its identity/image are unchanged and
healthy. All **140** live schema objects match the completed backup made before that attempt;
schema/cutoff/business state and attachments are unchanged. No migration was applied. Future
cleanup must use the recorded container ID directly, as specified above. The receipt retains the
failed dependency attempt and direct recovery; it does not claim an incident-free execution.

The historical 40-photo archive remains retained and accurately incomplete; the corrected verifier
rejects it for missing finalized versions. The new recovery point resolves the backup release gate.
ADR-0044, ADR-0048 and M6.6-B remain unaccepted; PR #17 remains draft and unmerged.
The full product candidate and Boa guide have not been deployed/imported. No X1 or M6.6-C work.
