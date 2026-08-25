from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import (
    Environment,
    PasswordResetDeliveryMode,
    Settings,
)

ROOT = Path(__file__).parents[2]
OLD_PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery staple"
GENERIC_CONFIRMATION = (
    "If an account exists for that email, password reset instructions have been sent."
)


def csrf_from(text_value: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text_value)
    assert match is not None
    return match.group(1)


def recovery_app(tmp_path: Path) -> tuple[FastAPI, Path]:
    database = tmp_path / "password-recovery-browser.sqlite3"
    delivery = tmp_path / "identity-messages"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=database,
            external_origin="https://tracker.theroccos.us",
            runtime_secret="password-recovery-browser-secret-32b",
            session_cookie_secure=False,
            password_reset_delivery=PasswordResetDeliveryMode.LOCAL_FILE,
            password_reset_delivery_path=delivery,
        )
    )
    return app, delivery


def setup_owner(client: TestClient) -> None:
    page = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": csrf_from(page.text),
            "household_name": "Owner Home",
            "timezone": "UTC",
            "display_name": "Owner",
            "email": "owner@example.com",
            "password": OLD_PASSWORD,
            "password_confirmation": OLD_PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def login(client: TestClient, password: str) -> int:
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "csrf_token": csrf_from(page.text),
            "email": "owner@example.com",
            "password": password,
        },
        follow_redirects=False,
    ).status_code


def reset_token(delivery: Path, *, position: int = -1) -> str:
    artifacts = sorted(delivery.glob("password-reset-*.json"))
    payload = json.loads(artifacts[position].read_text(encoding="utf-8"))
    return parse_qs(urlsplit(payload["reset_url"]).fragment)["token"][0]


def test_complete_browser_recovery_revokes_old_session_and_requires_fresh_login(
    tmp_path: Path,
) -> None:
    app, delivery = recovery_app(tmp_path)
    with TestClient(app) as primary, TestClient(app) as old_session:
        setup_owner(primary)
        assert login(old_session, OLD_PASSWORD) == 303
        more = primary.get("/more")
        primary.post("/logout", data={"csrf_token": csrf_from(more.text)})

        login_page = primary.get("/login")
        assert 'href="/forgot-password"' in login_page.text
        request_page = primary.get("/forgot-password")
        assert primary.post("/forgot-password", data={}).status_code == 403
        known = primary.post(
            "/forgot-password",
            data={"csrf_token": csrf_from(request_page.text), "email": " OWNER@example.com "},
            follow_redirects=False,
        )
        unknown_page = primary.get("/forgot-password")
        unknown = primary.post(
            "/forgot-password",
            data={"csrf_token": csrf_from(unknown_page.text), "email": "missing@example.com"},
            follow_redirects=False,
        )
        assert (known.status_code, known.headers["location"], known.text) == (
            unknown.status_code,
            unknown.headers["location"],
            unknown.text,
        )
        confirmation = primary.get(known.headers["location"])
        assert confirmation.status_code == 200
        assert GENERIC_CONFIRMATION in confirmation.text
        assert len(list(delivery.glob("password-reset-*.json"))) == 1

        token = reset_token(delivery)
        reset_page = primary.get("/reset-password")
        assert token not in reset_page.text
        assert "/static/password-reset.js" in reset_page.text
        assert "Request a new reset link" in reset_page.text
        assert primary.post("/reset-password", data={}).status_code == 403
        mismatch = primary.post(
            "/reset-password",
            data={
                "csrf_token": csrf_from(reset_page.text),
                "reset_token": token,
                "password": NEW_PASSWORD,
                "password_confirmation": "does not match the password",
            },
        )
        assert mismatch.status_code == 422
        assert "Passwords do not match" in mismatch.text
        completed = primary.post(
            "/reset-password",
            data={
                "csrf_token": csrf_from(mismatch.text),
                "reset_token": token,
                "password": NEW_PASSWORD,
                "password_confirmation": NEW_PASSWORD,
            },
            follow_redirects=False,
        )
        assert completed.status_code == 303
        assert completed.headers["location"] == "/login?reset=complete"
        assert old_session.get("/home", follow_redirects=False).headers["location"] == "/login"
        assert login(primary, OLD_PASSWORD) == 401
        assert login(primary, NEW_PASSWORD) == 303

        used_page = primary.get("/reset-password")
        used = primary.post(
            "/reset-password",
            data={
                "csrf_token": csrf_from(used_page.text),
                "reset_token": token,
                "password": NEW_PASSWORD,
                "password_confirmation": NEW_PASSWORD,
            },
        )
        assert used.status_code == 400
        assert "invalid or has expired" in used.text


def test_expired_link_and_request_throttle_keep_safe_public_responses(tmp_path: Path) -> None:
    app, delivery = recovery_app(tmp_path)
    with TestClient(app) as client:
        setup_owner(client)
        more = client.get("/more")
        client.post("/logout", data={"csrf_token": csrf_from(more.text)})
        responses: list[tuple[int, str, str]] = []
        for _ in range(6):
            page = client.get("/forgot-password")
            response = client.post(
                "/forgot-password",
                data={"csrf_token": csrf_from(page.text), "email": "owner@example.com"},
                follow_redirects=False,
            )
            responses.append((response.status_code, response.headers["location"], response.text))
        assert len(set(responses)) == 1
        assert len(list(delivery.glob("password-reset-*.json"))) == 5

        token = reset_token(delivery)
        with app.state.database_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE password_reset_credentials "
                    "SET expires_at='2020-01-01T00:00:00.000000+00:00' "
                    "WHERE invalidated_at IS NULL"
                )
            )
        page = client.get("/reset-password")
        expired = client.post(
            "/reset-password",
            data={
                "csrf_token": csrf_from(page.text),
                "reset_token": token,
                "password": NEW_PASSWORD,
                "password_confirmation": NEW_PASSWORD,
            },
        )
        assert expired.status_code == 400
        assert "Request a new one" in expired.text
