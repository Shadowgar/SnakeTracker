from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def _command_id(text_value: str) -> str:
    match = re.search(r'name="idempotency_key" value="([^"]+)"', text_value)
    assert match is not None
    return match.group(1)


def _logout(client: TestClient) -> None:
    page = client.get("/more")
    response = client.post(
        "/logout",
        data={"csrf_token": csrf_from(page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _register(client: TestClient, *, email: str = "new@example.com") -> None:
    page = client.get("/register")
    response = client.post(
        "/register",
        data={
            "csrf_token": csrf_from(page.text),
            "idempotency_key": _command_id(page.text),
            "collection_name": "New Keeper Collection",
            "timezone": "UTC",
            "display_name": "New Keeper",
            "email": email,
            "password": "another correct horse battery staple",
            "password_confirmation": "another correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/home"


def test_existing_installation_supports_registration_session_and_normal_login(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        _logout(client)
        login = client.get("/login")
        assert 'href="/register"' in login.text

        _register(client)
        home = client.get("/home")
        assert "Welcome back, New Keeper" in home.text
        assert "New Keeper Collection" in home.text
        assert "Rocco" not in home.text
        assert "No animals yet" in client.get("/animals").text

        with client.app.state.database_engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 2
            assert (
                connection.execute(text("SELECT count(*) FROM household_summaries")).scalar_one()
                == 2
            )
            assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 4
            assert (
                connection.execute(
                    text("SELECT count(*) FROM authorization_memberships WHERE role='owner'")
                ).scalar_one()
                == 2
            )

        _logout(client)
        login_page = client.get("/login")
        response = client.post(
            "/login",
            data={
                "csrf_token": csrf_from(login_page.text),
                "email": "owner@example.com",
                "password": "correct horse battery staple",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "Rocco&#39;s Reptiles" in client.get("/home").text


def test_registration_validation_csrf_uniqueness_and_throttle_fail_closed(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        complete_setup(client)
        _logout(client)
        assert client.post("/register", data={}).status_code == 403

        page = client.get("/register")
        mismatch = client.post(
            "/register",
            data={
                "csrf_token": csrf_from(page.text),
                "idempotency_key": _command_id(page.text),
                "collection_name": "Safe Collection",
                "timezone": "UTC",
                "display_name": "Keeper",
                "email": "keeper@example.com",
                "password": "another correct horse battery staple",
                "password_confirmation": "does not match",
            },
        )
        assert mismatch.status_code == 422
        assert "Passwords do not match" in mismatch.text
        assert "keeper@example.com" in mismatch.text
        assert "another correct horse battery staple" not in mismatch.text

        invalid_timezone_page = client.get("/register")
        invalid_timezone = client.post(
            "/register",
            data={
                "csrf_token": csrf_from(invalid_timezone_page.text),
                "idempotency_key": _command_id(invalid_timezone_page.text),
                "collection_name": "Safe Collection",
                "timezone": "Not/A_Real_Zone",
                "display_name": "Keeper",
                "email": "zone@example.com",
                "password": "another correct horse battery staple",
                "password_confirmation": "another correct horse battery staple",
            },
        )
        assert invalid_timezone.status_code == 422
        assert "valid IANA timezone" in invalid_timezone.text

        cross_origin_page = client.get("/register")
        cross_origin = client.post(
            "/register",
            headers={"Origin": "https://attacker.example"},
            data={"csrf_token": csrf_from(cross_origin_page.text)},
        )
        assert cross_origin.status_code == 403

        statuses: list[int] = []
        for _ in range(6):
            attempt = client.get("/register")
            response = client.post(
                "/register",
                data={
                    "csrf_token": csrf_from(attempt.text),
                    "idempotency_key": _command_id(attempt.text),
                    "collection_name": "Duplicate Collection",
                    "timezone": "UTC",
                    "display_name": "Duplicate",
                    "email": "owner@example.com",
                    "password": "another correct horse battery staple",
                    "password_confirmation": "another correct horse battery staple",
                },
            )
            statuses.append(response.status_code)
        assert statuses == [422, 422, 422, 422, 422, 429]
        assert "email already exists" not in response.text.lower()
        assert "Too many attempts" in response.text
        with client.app.state.database_engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
            assert (
                connection.execute(text("SELECT count(*) FROM household_summaries")).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM security_audit WHERE action='account.register'")
                ).scalar_one()
                == 7
            )
