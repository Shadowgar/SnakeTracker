# Phase 3 Migration Evidence

Alembic revision `0004_event_platform` follows `0003_phase2_review_hardening`. It adds only outbox
handoff, aggregate snapshot, projection definition, projection generation, and projection
checkpoint storage. It does not alter accepted Phase 2 migrations or introduce product tables.

`migration-lifecycle.log` proves fresh upgrade, downgrade, re-upgrade, constraints, minimum SQLite
schema compatibility, absence of upcasters from Alembic, and exact preservation of existing Phase
2 household event and subject rows across the forward migration. The final review additionally
proves composite projection/generation ownership foreign keys and an empty
`PRAGMA foreign_key_check` after upgrade/downgrade/re-upgrade. The isolated Compose lifecycle also
finished at `0004_event_platform`.
