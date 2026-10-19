import json
import logging
import sqlite3
import threading

import pytest

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import load_settings
from snaketracker.infrastructure.observability.logging import configure_logging
from snaketracker.worker.main import EXIT_RECOVERY_REQUIRED, run_worker


@pytest.fixture(autouse=True)
def isolate_startup_logging(monkeypatch):
    # Migration fixtures disable existing loggers; real startup uses a fresh process.
    for name in ("snaketracker.bootstrap.application", "snaketracker.worker.main"):
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        yield
    finally:
        # Startup configuration installs a handler bound to this test's captured stderr.
        root.handlers[:] = handlers
        root.setLevel(level)


@pytest.mark.parametrize("entrypoint", ["web", "worker"])
@pytest.mark.parametrize(
    "payload",
    [
        '{"animal_type":"snake","capability_profile_version":99}',
        '{"animal_type":"amphibian","capability_profile_version":1}',
        '{"animal_type":"snake","capability_profile_version":true}',
        "[]",
        "{broken",
    ],
)
def test_incompatible_identity_is_rejected_before_sqlite_profile_mutation(
    tmp_path, entrypoint, payload, capsys
):
    try:
        identity = json.loads(payload)
    except ValueError:
        identity = None
    if isinstance(identity, dict):
        payload = json.dumps(
            {
                "animal_id": "11111111-1111-4111-8111-111111111111",
                "name": "Private fixture name",
                "species": "Private fixture species",
                "morph": None,
                "genetics": None,
                "sex": None,
                "birth_hatch_date": None,
                "acquisition_date": None,
                "breeder_source": None,
                "status": "active",
                "notes": None,
                **identity,
            }
        )
    database = tmp_path / "incompatible.sqlite3"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT);"
            "INSERT INTO alembic_version VALUES('0025_natural_history');"
            "CREATE TABLE domain_events(event_type TEXT,schema_version INTEGER,payload_json TEXT);"
            "CREATE TABLE projection_definitions(projection_name TEXT,"
            "projection_schema_version INTEGER,handler_version INTEGER);"
        )
        db.execute("INSERT INTO domain_events VALUES('animal.registered',2,?)", (payload,))
    before = database.read_bytes()
    settings = load_settings(
        {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(database)}
    )
    if entrypoint == "web":
        app = build_application(settings)
        try:
            assert not app.state.compatibility.normal_readiness
            assert not any(getattr(route, "path", "") == "/animals" for route in app.routes)
            assert app.state.compatibility.operator_detail is not None
        finally:
            app.state.database_engine.dispose()
    else:
        configure_logging("INFO")
        assert (
            run_worker(settings, threading.Event(), poll_interval=0.001) == EXIT_RECOVERY_REQUIRED
        )
    diagnostic = capsys.readouterr().err
    expected = (
        "unsupported identity"
        if isinstance(identity, dict) and type(identity.get("capability_profile_version")) is int
        else "invalid event payload"
    )
    assert expected in diagnostic
    assert "animal.registered v2" in diagnostic
    assert "Private fixture name" not in diagnostic
    assert "Private fixture species" not in diagnostic
    assert str(database) not in diagnostic
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert database.read_bytes() == before
    assert not database.with_name(database.name + "-wal").exists()


@pytest.mark.parametrize("entrypoint", ["web", "worker"])
def test_unavailable_storage_is_not_created_by_existing_storage_startup(tmp_path, entrypoint):
    database = tmp_path / "missing" / "absent.sqlite3"
    settings = load_settings(
        {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(database)}
    )
    if entrypoint == "web":
        app = build_application(settings)
        assert not app.state.compatibility.normal_readiness
        app.state.database_engine.dispose()
    else:
        assert run_worker(settings, threading.Event()) == EXIT_RECOVERY_REQUIRED
    assert not database.parent.exists()


def test_readonly_connection_rejects_writes_and_failed_extension_closes_startup(tmp_path):
    from sqlalchemy.exc import OperationalError

    from snaketracker.bootstrap.compatibility import inspect_startup_compatibility
    from snaketracker.infrastructure.database.engine import create_readonly_sqlite_engine

    database = tmp_path / "readonly.sqlite3"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT);"
            "INSERT INTO alembic_version VALUES('0025_natural_history');"
            "CREATE TABLE domain_events(event_type TEXT,schema_version INTEGER,payload_json TEXT);"
            "CREATE TABLE projection_definitions(projection_name TEXT,"
            "projection_schema_version INTEGER,handler_version INTEGER);"
        )
    before = database.read_bytes()
    engine = create_readonly_sqlite_engine(database)
    try:
        with engine.connect() as connection, pytest.raises(OperationalError, match="readonly"):
            connection.exec_driver_sql("CREATE TABLE forbidden(id INTEGER)")

        def failed_inspection(connection):
            raise RuntimeError("Fixture inspection failed")

        report = inspect_startup_compatibility(engine, reference_inspections=(failed_inspection,))
        assert not report.normal_readiness
        assert report.reason_code == "compatibility_inspection_failed"
        assert report.operator_detail is not None
        assert "inspection incomplete" in report.operator_detail.lower()
        assert "Fixture inspection failed" not in report.operator_detail
        assert database.read_bytes() == before
    finally:
        engine.dispose()


@pytest.mark.parametrize("entrypoint", ["web", "worker"])
def test_unknown_contract_diagnostic_is_private_at_actual_startup(
    tmp_path, entrypoint, capsys, monkeypatch
):
    from fastapi.testclient import TestClient

    from snaketracker.bootstrap import application
    from snaketracker.worker import main as worker

    database = tmp_path / "private-fixture.sqlite3"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT);"
            "INSERT INTO alembic_version VALUES('0025_natural_history');"
            "CREATE TABLE domain_events(event_type TEXT,schema_version INTEGER,payload_json TEXT);"
        )
        db.execute(
            "INSERT INTO domain_events VALUES('future.contract',99,?)",
            ('{"notes":"private-payload-secret","household":"private-household"}',),
        )
    before = database.read_bytes()
    settings = load_settings(
        {"SNAKETRACKER_ENVIRONMENT": "test", "SNAKETRACKER_DATABASE_PATH": str(database)}
    )

    def forbidden_mutable_engine(*args, **kwargs):
        pytest.fail("Incompatible startup reached the mutable-engine factory")

    monkeypatch.setattr(application, "create_sqlite_engine", forbidden_mutable_engine)
    monkeypatch.setattr(worker, "create_sqlite_engine", forbidden_mutable_engine)
    if entrypoint == "web":
        app = build_application(settings)
        with TestClient(app) as client:
            response = client.get("/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable", "reason": "event_contract_unknown"}
            assert "future.contract" not in response.text
            assert "v99" not in response.text
            assert client.get("/animals").status_code == 404
    else:
        configure_logging("INFO")
        assert run_worker(settings, threading.Event()) == EXIT_RECOVERY_REQUIRED
    diagnostic = capsys.readouterr().err
    assert "future.contract v99" in diagnostic
    for secret in ("private-payload-secret", "private-household", str(database)):
        assert secret not in diagnostic
    assert database.read_bytes() == before
