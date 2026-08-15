from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from

ROOT = Path(__file__).parents[2]


def development_client_for(tmp_path: Path) -> TestClient:
    database = tmp_path / "development-browser.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return TestClient(
        build_application(
            Settings(
                environment=Environment.DEVELOPMENT,
                database_path=database,
                runtime_secret="development-browser-runtime-secret",
                session_cookie_secure=False,
            )
        )
    )


def test_today_reports_search_and_read_only_pwa_shell_are_browser_visible(tmp_path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        home = client.get("/home")
        assert "Today" in home.text
        assert 'href="/reports"' in home.text
        assert 'rel="manifest"' in home.text
        assert "unsafe-inline" not in home.headers["content-security-policy"]
        assert client.get("/reports").status_code == 200
        assert client.get("/reports/collection").status_code == 200
        assert client.get("/reports/collection.csv").headers["content-type"].startswith("text/csv")
        assert client.get("/reports/care").status_code == 200
        assert client.get("/reports/care.csv").status_code == 200
        assert client.get("/reports/expenses").status_code == 200
        assert client.get("/reports/expenses.csv").status_code == 200
        assert client.get("/search").status_code == 200
        assert client.get(f"/animals/{uuid4()}/analytics").status_code == 404
        assert client.get(f"/api/v1/animals/{uuid4()}/analytics/measurements").status_code == 404

        form = client.get("/animals/new")
        registered = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "Analytics fixture",
            },
            follow_redirects=False,
        )
        animal_url = registered.headers["location"]
        analytics = client.get(f"{animal_url}/analytics")
        assert analytics.status_code == 200
        assert "Nyx trends" in analytics.text
        assert "No measurements recorded yet." in analytics.text
        assert "No feedings recorded yet." in analytics.text
        data = client.get(f"/api/v1{animal_url}/analytics/measurements")
        assert data.status_code == 200
        assert data.json()["schema_version"] == 1
        assert (
            client.get(
                f"/api/v1{animal_url}/analytics/measurements",
                headers={"If-None-Match": data.headers["etag"]},
            ).status_code
            == 304
        )
        worker = client.get("/service-worker.js")
        assert worker.status_code == 200
        assert worker.headers["service-worker-allowed"] == "/"
        assert worker.headers["cache-control"] == "no-cache"
        assert 'method !== "GET"' in worker.text
        assert "caches.keys()" in worker.text
        pwa = client.get("/static/pwa.js")
        assert 'form[action="/logout"]' in pwa.text
        assert "caches.delete" in pwa.text
        assert "indexedDB" not in worker.text
        assert "indexedDB" not in pwa.text


def test_development_requests_do_not_run_async_projections_inline(tmp_path) -> None:
    with development_client_for(tmp_path) as client:
        complete_setup(client)

        home = client.get("/home")
        assert home.status_code == 200
        assert "Collection statistics are catching up." in home.text
        assert "Search is catching up" in client.get("/search?q=Nyx").text
        assert client.get("/reports").status_code == 200
        care = client.get("/reports/care")
        assert care.status_code == 503
        assert "report projection is rebuilding" in care.text
        assert client.get("/reports/care.csv").status_code == 503
