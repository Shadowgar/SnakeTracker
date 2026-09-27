"""Production-mode startup and read-only operator qualification on disposable storage."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.worker.main import run_worker
from tests.browser.test_account_registration import _command_id
from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from


def production_settings(database: Path, operator_id: str) -> Settings:
    root = database.parent
    return Settings(
        environment=Environment.PRODUCTION,
        database_path=database,
        attachment_storage_path=root / "attachments",
        reference_image_storage_path=root / "reference-images",
        backup_storage_path=root / "backups",
        external_origin="https://care.example.test",
        runtime_secret="isolated-production-mode-secret-32-bytes",
        backup_encryption_key="a1" * 32,
        session_cookie_secure=True,
        password_reset_delivery="disabled",
        platform_operator_user_ids=operator_id,
        build_git_sha="a" * 40,
    )


def test_production_web_worker_keeper_and_admin_on_isolated_data(tmp_path: Path) -> None:
    with client_for(tmp_path) as initial:
        complete_setup(initial)
        with initial.app.state.database_engine.connect() as connection:
            user_id = connection.execute(text("SELECT user_id FROM users LIMIT 1")).scalar_one()
    settings = production_settings(tmp_path / "browser.sqlite3", user_id)
    stop = threading.Event()
    stop.set()
    assert run_worker(settings, stop, poll_interval=0.001) == 0
    with TestClient(build_application(settings), base_url="https://care.example.test") as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/login").status_code == 200
        assert client.get("/admin").status_code == 403
        login = client.get("/login")
        signed_in = client.post(
            "/login",
            data={
                "csrf_token": csrf_from(login.text),
                "email": "owner@example.com",
                "password": "correct horse battery staple",
            },
            follow_redirects=False,
        )
        assert signed_in.status_code == 303
        assert "secure" in signed_in.headers["set-cookie"].lower()
        for path in ("/home", "/animals", "/calendar", "/quick-log", "/enclosures"):
            assert client.get(path).status_code == 200, path
        admin = client.get("/admin/system")
        assert admin.status_code == 200
        assert "production" in admin.text
        assert "a" * 40 in admin.text
        assert client.get(f"/admin/accounts/{user_id}").status_code == 200
        client.cookies.clear()
        register = client.get("/register")
        signup = client.post(
            "/register",
            data={
                "csrf_token": csrf_from(register.text),
                "idempotency_key": _command_id(register.text),
                "collection_name": "Separate Household",
                "timezone": "UTC",
                "display_name": "Separate Owner",
                "email": "separate@example.com",
                "password": "another correct horse battery staple",
                "password_confirmation": "another correct horse battery staple",
            },
            follow_redirects=False,
        )
        assert signup.status_code == 303
        assert client.get("/home").status_code == 200
        assert client.get("/admin").status_code == 403


def test_production_rejects_insecure_settings(tmp_path: Path) -> None:
    database = tmp_path / "isolated.sqlite3"
    for change in (
        {"external_origin": "http://care.example.test"},
        {"session_cookie_secure": False},
        {
            "password_reset_delivery": "local_file",
            "password_reset_delivery_path": tmp_path / "messages",
        },
        {"runtime_secret": None},
    ):
        with pytest.raises(ValidationError):
            Settings(**(production_settings(database, "").model_dump() | change))
