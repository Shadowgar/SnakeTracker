# M4 Backup and Restore Evidence

Result: **Pass for the basic local M4 path**

The worker is the only backup-data initiator. Browser commands create idempotent requests or update
the schedule; one global lease excludes overlap. The pipeline creates a consistent SQLite online
copy, captures its schema revision/event head/attachment references, invalidates copied sessions,
copies referenced finalized attachments, encrypts artifacts, writes a versioned manifest with an
independently identified key, and verifies checksums before completion.

The isolated Docker qualification run completed one manual backup:

- request status: `completed`;
- run ID: `be34f59a-da28-48a8-99d1-917074b6b842`;
- copied attachment count: 1;
- copied relational revision: `0008_local_backups`; and
- restore result: `verified`, with a readable restored SQLite database and one restored attachment.

The corrected-UX image repeated the browser-to-worker path with selected-photo data. Run
`51e10d20-ac49-4872-b994-efc1c9a0e486` completed with manifest checksum
`943c429eacdb58065edd894565a60a1ec3296f3a4f5c1766eed265739f848730`; SQLite returned
`integrity_check=ok`, and the operator rehearsal returned `status=verified` with one attachment.

The final review-hardened image repeated the complete path. Run
`b9d6e3f8-faed-4525-85c4-110fef83502a` completed with manifest checksum
`cdf4313d01f6d3adbcbf56459e93bdb0b60c70d60acd795cb202fd7b22ea9941`. Restore returned
`status=verified`, one immutable attachment, `integrity_check=ok`, revision
`0008_local_backups`, and zero copied sessions. Worker qualification also proves periodic lease
renewal while a backup exceeds its initial lease interval.

Heartbeat startup is inside the run failure boundary. If the renewal thread cannot start, the
request and run are durably marked `failed` and the global lease is released; no request remains
stranded in `running`.

Operator rehearsal command:

```sh
SNAKETRACKER_DATA_DIR=./runtime/m4-qualification \
SNAKETRACKER_HTTP_PORT=18083 \
SNAKETRACKER_EXTERNAL_ORIGIN=http://127.0.0.1:18083 \
docker compose -p snaketracker-m4-qualification exec -T web \
  python -m snaketracker.operations.backup_restore \
  --run-id be34f59a-da28-48a8-99d1-917074b6b842 \
  --restore-root /var/lib/snaketracker/restore-rehearsal
```

Observed output:

```json
{"attachment_count": 1, "database_path": "/var/lib/snaketracker/restore-rehearsal/be34f59ada2848a899d1917074b6b842/snaketracker.sqlite3", "status": "verified"}
```

Reproduce the automated failure, lease, manifest, encryption, verification, and restore matrix with
`uv run pytest tests/integration/test_local_backups.py -q`. Off-device retention, independent
production-key recovery, recovery objectives, and native Pi behavior remain Phase 7 work.
