from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command

from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository
from snaketracker.operations.natural_history import MAX_BUNDLE_BYTES, load_version, main
from tests.integration import test_local_taxonomy as taxonomy
from tests.integration.test_bioactive_plant_care import _plants
from tests.integration.test_natural_history import boa, version
from tests.integration.test_reminders import _setup
from tests.integration.test_taxonomy_compatibility import config_for

catalog = taxonomy.catalog


@pytest.mark.parametrize("schema", ["0025_natural_history", "0026_amphibian_care_guides"])
def test_explicit_offline_dry_run_retain_select_history_and_withdraw(
    catalog, tmp_path, monkeypatch, capsys, schema
):
    command.downgrade(config_for(Path(catalog.engine.url.database)), schema)
    identifier = boa(catalog)
    item = version(identifier)
    bundle = tmp_path / "source.json"
    bundle.write_text(item.payload)
    database = catalog.engine.url.database

    def invoke(arguments):
        monkeypatch.setattr("sys.argv", ["natural_history", *arguments])
        main()
        return capsys.readouterr().out

    assert json.loads(invoke(["retain", str(bundle)]))["dry_run"]
    assert json.loads(
        invoke(
            [
                "select",
                "unused",
                "1",
                "--sha256",
                item.digest,
                "--expected-revision",
                "0",
                "--actor",
                "reviewer",
                "--reason",
                "fixture",
            ]
        )
    )["dry_run"]
    result = json.loads(invoke(["--database", database, "--apply", "retain", str(bundle)]))
    assert result["published"] is False
    association = result["association"]
    with pytest.raises(ValueError, match="rights"):
        invoke(
            [
                "--database",
                database,
                "--apply",
                "select",
                association,
                "1",
                "--sha256",
                item.digest,
                "--expected-revision",
                "0",
                "--actor",
                "reviewer",
                "--reason",
                "fixture",
            ]
        )
    invoke(
        [
            "--database",
            database,
            "--apply",
            "select",
            association,
            "1",
            "--sha256",
            item.digest,
            "--expected-revision",
            "0",
            "--actor",
            "reviewer",
            "--reason",
            "fixture",
            "--development",
        ]
    )
    history = json.loads(invoke(["--database", database, "history", str(identifier)]))
    assert len(history["versions"]) == 1 and len(history["decisions"]) == 1
    invoke(
        [
            "--database",
            database,
            "--apply",
            "withdraw",
            association,
            "--expected-revision",
            "1",
            "--actor",
            "reviewer",
            "--reason",
            "withdraw fixture",
        ]
    )
    assert (
        len(json.loads(invoke(["--database", database, "history", str(identifier)]))["decisions"])
        == 2
    )


def test_operator_schema_27_preserves_populated_care_and_can_withdraw_publication(
    tmp_path, monkeypatch, capsys
):
    engine, boot, _, enclosures, _, enclosure, *_ = _setup(tmp_path)
    try:
        _plants(boot, enclosures, enclosure)
        identifier = boa(LocalTaxonomyCatalog(engine))
        item = version(
            identifier,
            rights_scope="production",
            rights_evidence="Synthetic rights qualification exercised only in isolated test.",
        )
        bundle = tmp_path / "source.json"
        bundle.write_text(item.payload)
        repository = NaturalHistoryRepository(engine)

        def snapshot():
            with engine.connect() as connection:
                schema = connection.exec_driver_sql(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
                ).all()
                tables = connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'natural_history_%'"
                ).scalars()
                return schema, {
                    table: sorted(
                        connection.exec_driver_sql(f'SELECT * FROM "{table}"').all(), key=repr
                    )
                    for table in tables
                }

        before = snapshot()
        assert before[1]["alembic_version"] == [("0027_bioactive_plant_care",)]
        assert before[1]["household_summaries"]
        assert before[1]["animal_current"]
        assert len(before[1]["enclosure_plant_current"]) == 2

        def no_migration(*args, **kwargs):
            pytest.fail("The Natural History operator must never migrate the database")

        monkeypatch.setattr(command, "upgrade", no_migration)
        monkeypatch.setattr(command, "downgrade", no_migration)

        def invoke(arguments):
            monkeypatch.setattr(
                "sys.argv", ["natural_history", "--database", engine.url.database, *arguments]
            )
            main()
            result = capsys.readouterr().out
            assert snapshot() == before
            return result

        assert json.loads(invoke(["history", str(identifier)])) == {
            "versions": [],
            "decisions": [],
        }
        retained = json.loads(invoke(["--apply", "retain", str(bundle)]))
        assert retained["published"] is False
        association = retained["association"]
        audit = ["--actor", "reviewer", "--reason", "Isolated operator regression"]
        invoke(
            [
                "--apply",
                "select",
                association,
                "1",
                "--sha256",
                item.digest,
                "--expected-revision",
                "0",
                *audit,
            ]
        )
        assert repository.published(identifier) == (item,)
        history = json.loads(invoke(["history", str(identifier)]))
        assert len(history["versions"]) == 1 and len(history["decisions"]) == 1
        invoke(["--apply", "withdraw", association, "--expected-revision", "1", *audit])
        assert repository.published(identifier) == ()
        assert repository.versions(identifier) == (item,)
        history = json.loads(invoke(["history", str(identifier)]))
        assert len(history["versions"]) == 1 and len(history["decisions"]) == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize("schema", ["0028_future_schema", "unknown_schema"])
def test_operator_unknown_or_newer_schema_rejected_before_writable_open(
    catalog, monkeypatch, schema
):
    with catalog.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num=?", (schema,))
    path = Path(catalog.engine.url.database)
    before = path.read_bytes()

    def no_writable_engine(*args, **kwargs):
        pytest.fail("Unsupported schema must be rejected before opening a writable engine")

    monkeypatch.setattr(
        "snaketracker.operations.natural_history.create_sqlite_engine", no_writable_engine
    )
    for action in (
        ["history", "00000000-0000-0000-0000-000000000001"],
        [
            "--apply",
            "withdraw",
            "unused",
            "--expected-revision",
            "0",
            "--actor",
            "reviewer",
            "--reason",
            "fixture",
        ],
    ):
        monkeypatch.setattr("sys.argv", ["natural_history", "--database", str(path), *action])
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
        assert path.read_bytes() == before


def test_operator_rejects_missing_database_unmigrated_and_oversized(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="missing"):
        load_version(tmp_path / "absent.json")
    large = tmp_path / "large.json"
    large.write_bytes(b"x" * (MAX_BUNDLE_BYTES + 1))
    with pytest.raises(ValueError, match="128 KiB"):
        load_version(large)
    for database in [None, "relative.db", str(tmp_path / "missing.db")]:
        args = ["natural_history", "--apply"]
        if database is not None:
            args += ["--database", database]
        monkeypatch.setattr(
            "sys.argv",
            [
                *args,
                "withdraw",
                "unused",
                "--expected-revision",
                "0",
                "--actor",
                "reviewer",
                "--reason",
                "fixture",
            ],
        )
        with pytest.raises(SystemExit):
            main()
    from alembic import command

    from tests.integration.test_taxonomy_compatibility import config_for

    path = tmp_path / "older.db"
    command.upgrade(config_for(path), "0024_local_taxonomy")
    monkeypatch.setattr(
        "sys.argv",
        [
            "natural_history",
            "--database",
            str(path),
            "history",
            "00000000-0000-0000-0000-000000000001",
        ],
    )
    with pytest.raises(SystemExit):
        main()
