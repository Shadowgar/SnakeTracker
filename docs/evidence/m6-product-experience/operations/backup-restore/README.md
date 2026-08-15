# Backup and Restore Compatibility

The accepted encrypted backup pipeline remains unchanged. M6 qualification reran manifest,
encryption, wrong-key, lease, verification, and isolated restore tests with the 0011 schema and M6
projection catalog. Sessions and temporary credentials remain excluded/invalidated as designed.

Reproduce with `uv run pytest -q tests/integration/test_local_backups.py
tests/integration/test_maintenance_cli.py`.
