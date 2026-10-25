from __future__ import annotations

import json

import pytest

from snaketracker.operations.natural_history import MAX_BUNDLE_BYTES, load_version, main
from tests.integration import test_local_taxonomy as taxonomy
from tests.integration.test_natural_history import boa, version

catalog = taxonomy.catalog


def test_explicit_offline_dry_run_retain_select_history_and_withdraw(
    catalog, tmp_path, monkeypatch, capsys
):
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
