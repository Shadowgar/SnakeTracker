# Backup and Restore Compatibility

The accepted encrypted backup pipeline remains unchanged. M6 qualification reran manifest,
encryption, wrong-key, lease, verification, and isolated restore tests with the 0011 schema and M6
projection catalog. Sessions and temporary credentials remain excluded/invalidated as designed.

Reproduce with `uv run pytest -q tests/integration/test_local_backups.py
tests/integration/test_maintenance_cli.py`.

## Consolidated owner-review rehearsal

On August 16, 2026, the promoted worker completed encrypted backup run
`8af08b00-2be7-43c2-baea-79780b27f3fd` with manifest checksum
`f49aaa046e4a9a76964a31753b9ac600069055e3859612a7da32d397ae5c268c`. The operator CLI verified and
restored that archive inside the web container's isolated `/tmp` filesystem, where the persisted
container paths and independently mounted encryption key are valid.

The restored copy reported SQLite integrity `ok`, two households, 13 animals, all 381 immutable
domain events, 13 attachment files, and zero sessions. The live database and attachments were not
replaced or modified by the rehearsal.
