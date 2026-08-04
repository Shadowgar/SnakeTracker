# Planned Folder Structure

This structure is a future implementation contract; the architecture package does not create application modules.

```text
SnakeTracker/
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── compose.yaml
├── README.md
├── src/snaketracker/
│   ├── bootstrap/                 # Sole composition root
│   ├── platform/
│   │   ├── auth/
│   │   ├── tenancy/
│   │   ├── events/
│   │   ├── projections/
│   │   ├── jobs/
│   │   ├── notifications/
│   │   ├── attachments/
│   │   ├── search/
│   │   └── observability/
│   ├── domains/
│   │   ├── households/
│   │   ├── animals/
│   │   │   ├── domain/
│   │   │   │   ├── aggregate/
│   │   │   │   ├── common/
│   │   │   │   ├── profile/
│   │   │   │   ├── husbandry/
│   │   │   │   │   ├── contracts/
│   │   │   │   │   ├── upcasters/
│   │   │   │   │   └── replay_fixtures/
│   │   │   │   └── health/
│   │   │   │       ├── contracts/
│   │   │   │       ├── upcasters/
│   │   │   │       └── replay_fixtures/
│   │   │   ├── application/
│   │   │   └── presentation/
│   │   ├── enclosures/
│   │   ├── inventory/
│   │   ├── expenses/
│   │   ├── reminders/
│   │   └── documents/
│   ├── presentation/
│   │   ├── web/
│   │   │   ├── routes/
│   │   │   ├── forms/
│   │   │   ├── view_models/
│   │   │   └── templates/
│   │   └── api/v1/
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── event_store/
│   │   ├── projections/
│   │   ├── filesystem/
│   │   ├── scheduler/
│   │   ├── notifications/
│   │   └── security/
│   └── static/
├── migrations/                   # Alembic relational migrations only
│   └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── replay/
│   ├── browser/
│   ├── security/
│   ├── performance/
│   └── fixtures/
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── security/
│   ├── operations/
│   ├── requirements/
│   ├── quality/
│   ├── ux/
│   ├── roadmap/
│   ├── evidence/
│   └── plans/
├── scripts/
│   ├── development/
│   ├── maintenance/
│   ├── backup/
│   └── benchmarks/
└── deploy/
    ├── nginx/
    ├── docker/
    └── systemd/
```

## Naming and size guidance

Python modules and functions use `snake_case`; classes and event payload types use `PascalCase`; constants use `UPPER_SNAKE_CASE`. Public contracts are explicitly exported. Absolute imports start at `snaketracker`. Domain features cannot import infrastructure or sideways feature implementations.

Files should have one coherent responsibility. Size is a review signal rather than a mechanical target: review modules above roughly 400 lines, functions above roughly 40 lines, deep nesting, or high cyclomatic complexity. Generated migrations and declarative catalogs are exceptions when splitting would reduce clarity.
