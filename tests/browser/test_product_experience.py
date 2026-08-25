from __future__ import annotations

from datetime import date, timedelta
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
        assert 'href="/reports"' in client.get("/more").text
        assert 'rel="manifest"' in home.text
        assert "unsafe-inline" not in home.headers["content-security-policy"]
        assert client.get("/reports").status_code == 200
        collection_report = client.get("/reports/collection")
        assert collection_report.status_code == 200
        assert "No report records yet." in collection_report.text
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
        assert "Not enough history yet" in analytics.text
        assert "0 of 6 accepted feedings recorded" in analytics.text
        assert "0 of 5 completed sheds recorded" in analytics.text
        assert "completed molts" not in analytics.text
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


def test_analytics_explains_estimates_and_passed_windows_in_plain_language(tmp_path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        form = client.get("/animals/new")
        registered = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Ember",
                "species": "Python regius",
                "sex": "female",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        animal_url = registered.headers["location"]
        first_day = date(2025, 1, 1)
        for index in range(6):
            feeding_form = client.get(f"{animal_url}/feedings/new")
            response = client.post(
                f"{animal_url}/feedings",
                data={
                    "csrf_token": csrf_from(feeding_form.text),
                    "idempotency_key": f"plain-estimate-{index}",
                    "occurred_at": (first_day + timedelta(days=index * 10)).isoformat() + "T12:00",
                    "prey_type": "Mouse",
                    "prey_size": "Small",
                    "preparation_method": "frozen_thawed",
                    "quantity": "1",
                    "outcome": "accepted",
                    "notes": "",
                    "return_to": "animal",
                },
                follow_redirects=False,
            )
            assert response.status_code == 303

        analytics = client.get(f"{animal_url}/analytics")
        assert "Feeding estimate" in analytics.text
        assert "Estimate window has passed" in analytics.text
        assert "This is an estimate, not a reminder schedule." in analytics.text
        assert "<summary>Why?</summary>" in analytics.text
        assert "5 effective intervals" in analytics.text
        assert "10% interval uncertainty floor" in analytics.text
        assert "Owner reminder schedules remain authoritative." in analytics.text


def test_care_keeper_shell_uses_distinct_mobile_and_desktop_navigation(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        home = client.get("/home")
        assert "Care Keeper" in home.text
        assert 'aria-label="Care Keeper home"' in home.text
        assert 'class="desktop-sidebar"' in home.text
        assert 'class="mobile-nav primary-nav"' in home.text
        for label, path in (
            ("Today", "/home"),
            ("Animals", "/animals"),
            ("Calendar", "/calendar"),
            ("Enclosures", "/enclosures"),
            ("More", "/more"),
        ):
            assert f'href="{path}"' in home.text
            assert f"<span>{label}</span>" in home.text
        mobile_navigation = home.text.split('class="mobile-nav primary-nav"', maxsplit=1)[1].split(
            "</nav>", maxsplit=1
        )[0]
        assert 'href="/inventory"' not in mobile_navigation
        assert 'href="/inventory"' in home.text
        assert "search-trigger" in home.text
        assert 'class="icon-button header-quick-log" href="/quick-log"' in home.text
        more = client.get("/more")
        assert more.status_code == 200
        for label in (
            "Inventory",
            "Reports",
            "Expenses",
            "Reminders",
            "Backups",
            "System operations",
            "Log out",
        ):
            assert label in more.text
        assert "Advanced" in more.text
        calendar = client.get("/calendar")
        assert calendar.status_code == 200
        assert "Month and agenda views arrive in Pass 2" in calendar.text
        quick_log = client.get("/quick-log")
        assert quick_log.status_code == 200
        assert "Add care" in quick_log.text
        assert "No animals available" in quick_log.text
        stylesheet = client.get("/static/app.css").text
        assert "env(safe-area-inset-bottom)" in stylesheet
        assert "min-height: 2.75rem" in stylesheet
        assert "--color-primary: #a78bfa" in stylesheet
        assert "@media (min-width: 64rem)" in stylesheet


def test_today_and_animals_are_separate_keeper_workspaces(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        today = client.get("/home")
        animals = client.get("/animals")

        assert '<h1 id="page-title">Today</h1>' in today.text
        assert "Your animals" not in today.text
        assert 'href="/animals"' in today.text
        assert '<h1 id="page-title">Animals</h1>' in animals.text
        assert "No animals yet" in animals.text
        assert "Add your first animal" in animals.text
        assert "Household access active" not in today.text


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
