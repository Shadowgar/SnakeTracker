"""Platform support is independent of household ownership and safe by default."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from tests.browser.test_account_registration import _command_id, _logout
from tests.browser.test_identity_flow import client_for, complete_setup, csrf_from
from tests.support.inventory import create_food_inventory, inventory_feeding_fields


def operator_client(tmp_path: Path) -> tuple[TestClient, str]:
    with client_for(tmp_path) as initial:
        complete_setup(initial)
        assert initial.get("/admin").status_code == 403  # Household owner.
        with initial.app.state.database_engine.connect() as connection:
            user_id = connection.execute(text("SELECT user_id FROM users LIMIT 1")).scalar_one()
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=tmp_path / "browser.sqlite3",
            runtime_secret="test-browser-runtime-secret-32-bytes",
            session_cookie_secure=False,
            platform_operator_user_ids=user_id,
        )
    )
    client = TestClient(app)
    login = client.get("/login")
    result = client.post(
        "/login",
        data={
            "csrf_token": csrf_from(login.text),
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert result.status_code == 303
    return client, user_id


def test_admin_routes_authorize_independently_and_audit(tmp_path: Path) -> None:
    client, user_id = operator_client(tmp_path)
    with client:
        with client.app.state.database_engine.connect() as connection:
            household_id = connection.execute(
                text("SELECT household_id FROM household_summaries LIMIT 1")
            ).scalar_one()
            event_id = connection.execute(
                text("SELECT event_id FROM domain_events LIMIT 1")
            ).scalar_one()
        paths = (
            "/admin",
            "/admin/accounts",
            f"/admin/accounts/{user_id}",
            "/admin/households",
            f"/admin/households/{household_id}",
            "/admin/events",
            f"/admin/events/{event_id}",
            "/admin/incidents",
            "/admin/system",
            "/admin/audit",
            "/admin/support-notes",
            f"/admin/animals/{UUID(int=1)}",
            f"/admin/enclosures/{UUID(int=1)}",
            f"/admin/inventory/{UUID(int=1)}",
        )
        for path in paths:
            response = client.get(path)
            assert response.status_code in (200, 404), (path, response.text[:200])
            assert "password_hash" not in response.text
            assert "csrf_token_hash" not in response.text
            assert "token_hash" not in response.text
        assert "Care Keeper Operations" in client.get("/admin").text
        assert "Rocco" in client.get("/admin/accounts?status=active").text
        today = datetime.now(UTC).date().isoformat()
        assert "Rocco" in client.get(f"/admin/accounts?registered_from={today}").text
        assert (
            f'href="/admin/accounts/{user_id}"'
            not in client.get(f"/admin/accounts?registered_before={today}").text
        )
        assert "Rocco" in client.get(f"/admin/accounts?household={household_id}&role=owner").text
        assert event_id in client.get(f"/admin?q={event_id}").text
        assert household_id in client.get(f"/admin/households/{household_id}").text
        with client.app.state.database_engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT action,outcome,details_json FROM security_audit "
                    "WHERE category='platform_admin'"
                )
            ).all()
        assert any(
            action == "admin.account.view" and outcome == "success" for action, outcome, _ in rows
        )
        assert all(details == "{}" for _, _, details in rows)


def test_anonymous_and_unconfigured_owner_are_denied(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        assert client.get("/admin/events?field=correlation_id").status_code == 403
        complete_setup(client)
        with client.app.state.database_engine.connect() as connection:
            household_id = connection.execute(
                text("SELECT household_id FROM household_summaries LIMIT 1")
            ).scalar_one()
            user_id = connection.execute(text("SELECT user_id FROM users LIMIT 1")).scalar_one()
            event_id = connection.execute(
                text("SELECT event_id FROM domain_events LIMIT 1")
            ).scalar_one()
        for path in (
            "/admin",
            "/admin/accounts",
            f"/admin/accounts/{user_id}",
            "/admin/households",
            f"/admin/households/{household_id}",
            "/admin/events",
            f"/admin/events/{event_id}",
            "/admin/incidents",
            "/admin/system",
            "/admin/audit",
            "/admin/support-notes",
            f"/admin/animals/{UUID(int=1)}",
            f"/admin/enclosures/{UUID(int=1)}",
            f"/admin/inventory/{UUID(int=1)}",
        ):
            assert client.get(path).status_code == 403
        with client.app.state.database_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM security_audit WHERE category='platform_admin' "
                        "AND outcome='denied'"
                    )
                ).scalar_one()
                >= 15
            )


def test_animal_feeding_inventory_provenance_and_warning(tmp_path: Path) -> None:
    client, _ = operator_client(tmp_path)
    with client:
        form = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Atlas",
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
        assert created.status_code == 303
        animal_url = created.headers["location"]
        animal_id = animal_url.split("/")[-1]
        enclosure_form = client.get("/enclosures/new")
        enclosure = client.post(
            "/enclosures",
            data={
                "csrf_token": csrf_from(enclosure_form.text),
                "name": "Rack A-03",
                "enclosure_type_choice": "Rack tub",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert enclosure.status_code == 303
        enclosure_id = enclosure.headers["location"].split("/")[-1]
        item_url = create_food_inventory(client, idempotency_prefix="admin-food")
        item_id = item_url.split("/")[-1]
        occurred = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        feeding = client.post(
            f"{animal_url}/feedings",
            data={
                **inventory_feeding_fields(client, animal_url),
                "occurred_at": occurred,
                "outcome": "accepted",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert feeding.status_code == 303
        with client.app.state.database_engine.connect() as connection:
            source_id, consumption_id = connection.execute(
                text(
                    "SELECT source_event_id,consumption_event_id "
                    "FROM inventory_consumption_links_v2 LIMIT 1"
                )
            ).one()
            household_id = connection.execute(
                text("SELECT household_id FROM animal_current WHERE animal_id=:id"),
                {"id": animal_id},
            ).scalar_one()
            correlation_id = connection.execute(
                text("SELECT correlation_id FROM domain_events WHERE event_id=:id"),
                {"id": source_id},
            ).scalar_one()
        animal_page = client.get(f"/admin/animals/{animal_id}")
        assert animal_page.status_code == 200
        assert "Keeper-visible effective history" in animal_page.text
        assert "Technical provenance" in animal_page.text
        assert source_id in animal_page.text
        assert consumption_id in animal_page.text
        item_page = client.get(f"/admin/inventory/{item_id}")
        assert item_page.status_code == 200
        assert source_id in item_page.text and consumption_id in item_page.text
        assert f"/admin/animals/{animal_id}" in item_page.text
        source_page = client.get(f"/admin/events/{source_id}")
        assert "Currently effective" in source_page.text
        assert consumption_id in source_page.text
        consumed_page = client.get(f"/admin/events/{consumption_id}")
        assert "Internal side effect" in consumed_page.text
        assert source_id in consumed_page.text
        assert source_id in client.get(f"/admin/incidents?q={animal_id}").text
        assert household_id in client.get(f"/admin?q={household_id}").text
        assert "Rack A-03" in client.get(f"/admin/enclosures/{enclosure_id}").text
        for identifier in (
            "owner@example.com",
            household_id,
            enclosure_id,
            item_id,
            source_id,
            correlation_id,
        ):
            assert client.get(f"/admin/incidents?q={identifier}").status_code == 200
        assert (
            "Feeding recorded"
            in client.get(f"/admin/events?field=correlation_id&q={correlation_id}").text
        )
        assert source_id in client.get(f"/admin/events?field=animal_id&q={animal_id}").text
        assert "Small Frozen Mouse" in client.get("/admin?q=Small").text
        assert client.get("/admin/events?field=unknown&q=Feeding").status_code == 200
        timeline = client.get(f"{animal_url}/timeline")
        voided = client.post(
            f"{animal_url}/events/{source_id}/void",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "admin-void-feeding",
                "reason": "Isolated support provenance test",
            },
            follow_redirects=False,
        )
        assert voided.status_code == 303
        assert "Voided or superseded" in client.get(f"/admin/events/{source_id}").text
        with client.app.state.database_engine.connect() as connection:
            void_id = connection.execute(
                text(
                    "SELECT event_id FROM domain_events WHERE event_type='event.voided' "
                    "ORDER BY global_position DESC LIMIT 1"
                )
            ).scalar_one()
        assert "Immutable control event" in client.get(f"/admin/events/{void_id}").text
        timeline = client.get(f"{animal_url}/timeline")
        reinstated = client.post(
            f"{animal_url}/events/{source_id}/reinstate",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "admin-reinstate-feeding",
                "reason": "Isolated support provenance test",
            },
            follow_redirects=False,
        )
        assert reinstated.status_code == 303
        assert "Currently effective" in client.get(f"/admin/events/{source_id}").text
        with client.app.state.database_engine.connect() as connection:
            reinstate_id = connection.execute(
                text(
                    "SELECT event_id FROM domain_events WHERE event_type='event.reinstated' "
                    "ORDER BY global_position DESC LIMIT 1"
                )
            ).scalar_one()
        assert "Immutable control event" in client.get(f"/admin/events/{reinstate_id}").text
        missing_id = UUID(int=3)
        for kind in ("accounts", "households", "events"):
            assert client.get(f"/admin/{kind}/{missing_id}").status_code == 404

        # Malformed relationships are confined to this isolated fixture.
        bad_source = str(UUID(int=1))
        with client.app.state.database_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO inventory_consumption_links_v2 "
                    "(household_id,source_event_id,item_id,consumption_event_id,"
                    "quantity_scaled,status) "
                    "VALUES (:household,:source,:item,:consumption,1000,'active')"
                ),
                {
                    "household": household_id,
                    "source": bad_source,
                    "item": item_id,
                    "consumption": str(UUID(int=2)),
                },
            )
        assert "Missing source Feeding / event" in client.get(f"/admin/inventory/{item_id}").text


def test_admin_escapes_names_and_never_renders_credentials(tmp_path: Path) -> None:
    client, user_id = operator_client(tmp_path)
    with client:
        with client.app.state.database_engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET display_name=:name WHERE user_id=:id"),
                {"name": "<script>alert(1)</script>", "id": user_id},
            )
            password_hash, token_hash, csrf_hash = connection.execute(
                text(
                    "SELECT u.password_hash,s.token_hash,s.csrf_token_hash FROM users u "
                    "JOIN sessions s USING(user_id) WHERE u.user_id=:id LIMIT 1"
                ),
                {"id": user_id},
            ).one()
        response = client.get(f"/admin/accounts/{user_id}")
        assert response.status_code == 200
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;" in response.text
        assert not any(secret in response.text for secret in (password_hash, token_hash, csrf_hash))


def test_signup_cannot_grant_platform_access_or_cross_tenant_access(tmp_path: Path) -> None:
    client, operator_id = operator_client(tmp_path)
    with client:
        form = client.get("/animals/new")
        animal = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Operator Animal",
                "species": "Python regius",
                "sex": "",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert animal.status_code == 303
        animal_url = animal.headers["location"]
        _logout(client)
        for index in (1, 2):
            register = client.get("/register")
            response = client.post(
                "/register",
                data={
                    "csrf_token": csrf_from(register.text),
                    "idempotency_key": _command_id(register.text),
                    "collection_name": f"Other Household {index}",
                    "timezone": "UTC",
                    "display_name": f"Other Owner {index}",
                    "email": f"other{index}@example.com",
                    "password": "another correct horse battery staple",
                    "password_confirmation": "another correct horse battery staple",
                    "platform_operator_user_ids": operator_id,
                    "role": "platform_admin",
                },
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert client.get("/admin").status_code == 403
            assert client.get(animal_url).status_code in (403, 404)
            _logout(client)
        with client.app.state.database_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM household_summaries")).scalar_one()
                == 3
            )
            assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 3
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
        assert "Other Household 1" in client.get("/admin/households").text
        assert "Other Household 2" in client.get("/admin/households").text
