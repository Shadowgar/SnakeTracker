"""The Updates page is private, visual and honest about deployment status."""

from __future__ import annotations

import json
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[2]


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_updates_is_private_and_covers_earlier_history(tmp_path: Path) -> None:
    database = tmp_path / "app.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    settings = Settings(
        environment=Environment.TEST,
        database_path=database,
        runtime_secret=SecretStr("updates-test-local-secret-32-bytes"),
        session_cookie_secure=False,
    )
    app = build_application(settings)
    try:
        with TestClient(app) as client:
            denied = client.get("/updates", follow_redirects=False)
            assert denied.status_code == 303
            assert denied.headers["location"] == "/login"
            setup = client.get("/setup")
            response = client.post(
                "/setup",
                data={
                    "csrf_token": _csrf(setup.text),
                    "household_name": "Test home",
                    "timezone": "UTC",
                    "display_name": "Keeper",
                    "email": "keeper@example.test",
                    "password": "correct horse battery staple",
                    "password_confirmation": "correct horse battery staple",
                },
                follow_redirects=False,
            )
            assert response.status_code == 303

            page = client.get("/updates")
            assert page.status_code == 200
            assert "The beginning of Care Keeper" in page.text
            assert "Spiders join the collection" in page.text
            assert "Making room for more kinds of pets" in page.text
            assert "Find animals by more names" in page.text
            assert "What\u2019s new on this website" in page.text
            assert "Earlier website releases haven\u2019t been fully verified" in page.text
            assert "/static/animal-fallbacks/snake.webp" in page.text
            assert 'href="/updates"' in client.get("/more").text
            assert "Website update" not in page.text

            ledger = database.parent / "production-release-history.json"
            ledger.write_text(
                json.dumps(
                    [
                        {
                            "verified": True,
                            "version": "1.0.0",
                            "status": "deployed",
                            "deployed_at": "2026-10-17T17:30:00Z",
                            "build_sha": "c" * 40,
                            "title": "Confirmed release",
                            "description": "Keeper-facing changes.",
                            "changes": [{"kind": "New", "text": "A real, verified deployment."}],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            updated = client.get("/updates")
            assert updated.status_code == 200
            assert "Confirmed release" in updated.text
            assert "A real, verified deployment." in updated.text
            assert "'unsafe-inline'" not in updated.headers["content-security-policy"]
            assert 'style="' not in updated.text
            assert "Lennart Hudel" in page.text and "R. Bertani" in page.text
            assert "Do I need to do anything?" in page.text
            assert "not available to add yet" in page.text
            before = ledger.read_bytes()
            restarted_app = build_application(settings)
            try:
                with TestClient(restarted_app) as restarted:
                    restarted.cookies.update(client.cookies)
                    assert "Confirmed release" in restarted.get("/updates").text
                    assert ledger.read_bytes() == before
            finally:
                restarted_app.state.database_engine.dispose()
            notes = json.loads(ledger.read_text())
            notes.append(
                {
                    **notes[0],
                    "status": "rolled_back",
                    "version": "0.9",
                    "title": "Earlier version restored",
                    "deployed_at": "2026-10-17T18:00:00Z",
                }
            )
            ledger.write_text(json.dumps(notes))
            rolled_back = client.get("/updates")
            assert "restored after a rollback" in rolled_back.text
            assert rolled_back.text.index("Version 0.9") < rolled_back.text.index("Version 1.0.0")
            assert len(json.loads(ledger.read_text())) == 2
    finally:
        app.state.database_engine.dispose()
