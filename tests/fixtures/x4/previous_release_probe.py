"""Probe the archived release itself; never import current application modules."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from snaketracker.bootstrap import application, compatibility
from snaketracker.bootstrap.configuration import load_settings
from snaketracker.worker import main as worker

source_root, database, entrypoint = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
for module in (application, compatibility, worker):
    assert Path(module.__file__).is_relative_to(source_root), module.__file__

# Instrument the actual release's startup boundaries, not its compatibility decision.
# A regression must fail before it can open mutable storage or start replay/work duties.
mutable_calls = []


def forbidden_mutable_startup(*args, **kwargs):
    mutable_calls.append(True)
    raise AssertionError("Prior release attempted mutable application startup")


application.create_sqlite_engine = forbidden_mutable_startup
worker.create_sqlite_engine = forbidden_mutable_startup
application.ensure_product_projection_generations = forbidden_mutable_startup
worker.ensure_product_projection_generations = forbidden_mutable_startup
statements = []


@event.listens_for(Engine, "before_cursor_execute")
def audit_statement(connection, cursor, statement, parameters, context, executemany):
    statements.append(statement)
    first = statement.lstrip().split(None, 1)[0].upper()
    assert first in {"SELECT", "PRAGMA", "BEGIN"}, statement
    if first == "BEGIN":
        assert statement.strip().upper() == "BEGIN", statement
    if first == "PRAGMA":
        assert "=" not in statement, statement


settings = load_settings(
    {
        "SNAKETRACKER_ENVIRONMENT": "test",
        "SNAKETRACKER_DATABASE_PATH": str(database),
        "SNAKETRACKER_RUNTIME_SECRET": "x4-disposable-old-release-probe-secret-32",
        "SNAKETRACKER_ATTACHMENT_STORAGE_PATH": str(database.parent / "attachments"),
        "SNAKETRACKER_BACKUP_STORAGE_PATH": str(database.parent / "backups"),
    }
)
if entrypoint == "web":
    app = application.build_application(settings)
    report = app.state.compatibility
    assert not report.normal_readiness
    assert report.reason_code == "event_contract_unknown", report
    assert "animal.registered v3" in report.operator_detail
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json() == {"status": "unavailable", "reason": "event_contract_unknown"}
        for path in ("/animals", "/today", "/calendar", "/admin"):
            assert client.get(path).status_code == 404, path
        assert client.post("/animals", data={"name": "Forbidden write"}).status_code == 404
else:
    worker.configure_logging(settings.log_level)
    assert worker.run_worker(settings, threading.Event(), poll_interval=0.001) == 2
assert statements
assert not mutable_calls
print(json.dumps({"entrypoint": entrypoint, "restricted_recovery": True, "writes": 0}))
