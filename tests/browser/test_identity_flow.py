from __future__ import annotations

import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings

ROOT = Path(__file__).parents[2]


def client_for(tmp_path: Path) -> TestClient:
    database = tmp_path / "browser.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            runtime_secret="test-browser-runtime-secret-32-bytes",
            session_cookie_secure=False,
        )
    )
    return TestClient(app)


def csrf_from(response_text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def complete_setup(client: TestClient) -> None:
    setup = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": csrf_from(setup.text),
            "household_name": "Rocco's Reptiles",
            "timezone": "America/New_York",
            "display_name": "Rocco",
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "password_confirmation": "correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/home"


def test_first_run_login_home_logout_and_login_again(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        first = client.get("/", follow_redirects=False)
        assert first.status_code == 303
        assert first.headers["location"] == "/setup"

        setup = client.get("/setup")
        assert "Create your SnakeTracker home" in setup.text
        complete_setup(client)

        home = client.get("/home")
        assert home.status_code == 200
        assert "Welcome home, Rocco" in home.text
        assert "Rocco&#39;s Reptiles" in home.text
        assert "viewport" in home.text

        logout = client.post(
            "/logout",
            data={"csrf_token": csrf_from(home.text)},
            follow_redirects=False,
        )
        assert logout.status_code == 303
        assert logout.headers["location"] == "/login"
        assert client.get("/home", follow_redirects=False).headers["location"] == "/login"

        login_page = client.get("/login")
        login = client.post(
            "/login",
            data={
                "csrf_token": csrf_from(login_page.text),
                "email": "owner@example.com",
                "password": "correct horse battery staple",
            },
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == "/home"
        assert client.get("/home").status_code == 200


def test_csrf_and_validation_errors_are_usable_and_security_headers_are_strict(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        rejected = client.post(
            "/setup",
            data={"household_name": "No token"},
        )
        assert rejected.status_code == 403
        assert "could not be verified" in rejected.text.lower()

        page = client.get("/setup")
        invalid = client.post(
            "/setup",
            data={
                "csrf_token": csrf_from(page.text),
                "household_name": "",
                "timezone": "America/New_York",
                "display_name": "",
                "email": "bad",
                "password": "short",
                "password_confirmation": "different",
            },
        )
        assert invalid.status_code == 422
        assert "Please correct the highlighted fields" in invalid.text
        assert "default-src 'self'" in invalid.headers["content-security-policy"]
        assert invalid.headers["x-content-type-options"] == "nosniff"
        assert "unsafe-inline" not in invalid.headers["content-security-policy"]
        assert client.get("/static/favicon.svg").headers["content-type"] == "image/svg+xml"


def test_cross_origin_form_submission_is_rejected_even_with_a_valid_token(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        page = client.get("/setup")
        response = client.post(
            "/setup",
            headers={"Origin": "https://attacker.example"},
            data={
                "csrf_token": csrf_from(page.text),
                "household_name": "Unsafe",
                "timezone": "UTC",
                "display_name": "Owner",
                "email": "owner@example.com",
                "password": "correct horse battery staple",
                "password_confirmation": "correct horse battery staple",
            },
        )

        assert response.status_code == 403
        assert client.get("/setup").status_code == 200


def test_login_failure_rate_limit_and_unauthenticated_redirect(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        home = client.get("/home")
        client.post("/logout", data={"csrf_token": csrf_from(home.text)})
        for _ in range(6):
            page = client.get("/login")
            failed = client.post(
                "/login",
                data={
                    "csrf_token": csrf_from(page.text),
                    "email": "owner@example.com",
                    "password": "wrong password value",
                },
            )
        assert failed.status_code == 429
        assert "Too many attempts" in failed.text
        assert client.get("/home", follow_redirects=False).headers["location"] == "/login"
        with client.app.state.database_engine.connect() as connection:
            denied = connection.execute(
                text(
                    "SELECT count(*) FROM security_audit "
                    "WHERE action='protected_request' AND outcome='denied'"
                )
            ).scalar_one()
        assert denied == 1


def test_completed_setup_and_authenticated_login_pages_redirect_safely(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)

        assert client.get("/", follow_redirects=False).headers["location"] == "/home"
        assert client.get("/setup", follow_redirects=False).headers["location"] == "/home"
        assert client.get("/login", follow_redirects=False).headers["location"] == "/home"


def test_setup_domain_validation_and_logout_csrf_failure_are_rendered(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        page = client.get("/setup")
        invalid = client.post(
            "/setup",
            data={
                "csrf_token": csrf_from(page.text),
                "household_name": "",
                "timezone": "America/New_York",
                "display_name": "",
                "email": "bad",
                "password": "same",
                "password_confirmation": "same",
            },
        )
        assert invalid.status_code == 422
        assert "household name is required" in invalid.text

        complete_setup(client)
        rejected = client.post("/logout", data={"csrf_token": "incorrect"})
        assert rejected.status_code == 403
        assert "Return home and try again" in rejected.text
