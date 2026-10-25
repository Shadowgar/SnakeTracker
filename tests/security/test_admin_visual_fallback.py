"""Read-only admin imagery must respect the stored profile version."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from snaketracker.infrastructure.admin.read_repository import AdminReadRepository
from tests.browser.test_identity_flow import csrf_from
from tests.security.test_admin_console import operator_client


def test_admin_household_uses_neutral_art_for_unknown_stored_profile(tmp_path: Path) -> None:
    client, _ = operator_client(tmp_path)
    with client:
        form = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "name": "Future animal",
                "species": "Manually entered species",
                "animal_type": "snake",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        animal_id = created.headers["location"].rsplit("/", 1)[-1]
        engine = client.app.state.database_engine
        # Only this disposable projection is changed to model a future profile;
        # immutable registration events and the trusted registry stay untouched.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE animal_current SET capability_profile_version=99 "
                    "WHERE animal_id=:animal_id"
                ),
                {"animal_id": animal_id},
            )
            household_id = connection.execute(
                text("SELECT household_id FROM animal_current WHERE animal_id=:animal_id"),
                {"animal_id": animal_id},
            ).scalar_one()

        bundle = AdminReadRepository(engine).household_bundle(household_id)
        assert bundle["animals"][0].get("capability_profile_version") == 99
        response = client.get(f"/admin/households/{household_id}")

        assert response.status_code == 200
        assert "/static/animal-fallbacks/unknown.svg?" in response.text
        assert 'alt="Animal illustration"' in response.text
        assert "/static/animal-fallbacks/snake.webp" not in response.text
