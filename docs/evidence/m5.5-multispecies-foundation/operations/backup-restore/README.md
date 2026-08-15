# Backup and Restore Qualification

Result: **Pass**, requalified on August 15, 2026 at revision `ebd5200`.

The existing encrypted backup pipeline copied a completed SQLite backup, captured attachment
references from that copy, verified the manifest and ciphertext, restored into an isolated root,
and read back schema 0010 with both Snake and Spider projection rows. Sessions and temporary
credentials remain excluded/invalidated; no plaintext application secret or decryption key enters
the backup set. Wrong-key, lease, idempotency, and scheduled-worker cases remain green.

Reproduce with `uv run pytest -q tests/integration/test_local_backups.py`.

The final focused 94-test qualification set repeated backup verification and isolated restore
alongside legacy replay, mixed-species replay, capability, inventory, reminder, and migration tests.
