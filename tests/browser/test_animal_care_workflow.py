from __future__ import annotations

import re
from base64 import b64decode
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from PIL.TiffImagePlugin import IFDRational
from sqlalchemy import text

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from tests.support.inventory import create_food_inventory, inventory_feeding_fields

ROOT = Path(__file__).parents[2]
ONE_PIXEL_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def client_for(tmp_path: Path) -> TestClient:
    database = tmp_path / "animal-care-browser.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return TestClient(
        build_application(
            Settings(
                environment=Environment.TEST,
                database_path=database,
                runtime_secret="test-browser-runtime-secret-32-bytes",
                session_cookie_secure=False,
            )
        )
    )


def csrf_from(response_text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def setup_and_sign_in(client: TestClient, *, timezone: str = "UTC") -> None:
    setup = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": csrf_from(setup.text),
            "household_name": "Rocco's Reptiles",
            "timezone": timezone,
            "display_name": "Rocco",
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "password_confirmation": "correct horse battery staple",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_authenticated_keeper_can_track_animal_care_and_enclosure_workflow(
    tmp_path: Path,
) -> None:
    occurred_at = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0)
    occurred_value = occurred_at.strftime("%Y-%m-%dT%H:%M")
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)

        animals_page = client.get("/animals")
        assert (
            '<a class="button-link collection-add" href="/animals/new">'
            '<span aria-hidden="true">+</span> Add</a>' in animals_page.text
        )
        assert 'href="/settings/backups"' in client.get("/more").text
        assert "No animals yet" in animals_page.text

        add_animal = client.get("/animals/new")
        registered = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(add_animal.text),
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
                "morph": "",
                "genetics": "",
                "birth_hatch_date": "",
                "acquisition_date": "",
                "breeder_source": "",
                "notes": "Calm and curious.",
            },
            follow_redirects=False,
        )
        assert registered.status_code == 303
        profile_url = registered.headers["location"]
        assert profile_url.startswith("/animals/")

        profile = client.get(profile_url)
        assert "Nyx" in profile.text
        assert "Record feeding" in profile.text
        create_food_inventory(client, idempotency_prefix="care-workflow-food")

        feeding = client.post(
            f"{profile_url}/feedings",
            data={
                **inventory_feeding_fields(client, profile_url),
                "occurred_at": occurred_value,
                "outcome": "accepted",
                "notes": "Fed eagerly.",
            },
            follow_redirects=False,
        )
        assert feeding.status_code == 303

        profile = client.get(profile_url)
        weight = client.post(
            f"{profile_url}/weights",
            data={
                "csrf_token": csrf_from(profile.text),
                "occurred_at": occurred_value,
                "weight_grams": "512",
                "notes": "After feeding.",
            },
            follow_redirects=False,
        )
        assert weight.status_code == 303

        profile = client.get(profile_url)
        length = client.post(
            f"{profile_url}/lengths",
            data={
                "csrf_token": csrf_from(profile.text),
                "occurred_at": occurred_value,
                "length_mm": "925",
                "notes": "Relaxed measurement.",
            },
            follow_redirects=False,
        )
        assert length.status_code == 303

        profile = client.get(profile_url)
        shed = client.post(
            f"{profile_url}/sheds",
            data={
                "csrf_token": csrf_from(profile.text),
                "occurred_at": occurred_value,
                "blue_state": "false",
                "completed": "true",
                "result": "complete",
                "notes": "One piece.",
            },
            follow_redirects=False,
        )
        assert shed.status_code == 303

        profile = client.get(profile_url)
        bath = client.post(
            f"{profile_url}/baths",
            data={
                "csrf_token": csrf_from(profile.text),
                "occurred_at": occurred_value,
                "duration_minutes": "20",
                "reason": "Hydration",
                "notes": "Calm.",
            },
            follow_redirects=False,
        )
        assert bath.status_code == 303

        enclosure_form = client.get("/enclosures/new")
        enclosure_created = client.post(
            "/enclosures",
            data={
                "csrf_token": csrf_from(enclosure_form.text),
                "name": "Rack A-03",
                "enclosure_type": "tub",
                "notes": "Warm rack.",
            },
            follow_redirects=False,
        )
        assert enclosure_created.status_code == 303
        enclosure_url = enclosure_created.headers["location"]
        enclosure_list = client.get("/enclosures")
        assert enclosure_list.status_code == 200
        assert "Rack A-03" in enclosure_list.text

        profile = client.get(profile_url)
        assigned = client.post(
            f"{profile_url}/enclosure",
            data={
                "csrf_token": csrf_from(profile.text),
                "enclosure_id": enclosure_url.rsplit("/", 1)[-1],
                "occurred_at": occurred_value,
                "notes": "Moved after cleaning.",
            },
            follow_redirects=False,
        )
        assert assigned.status_code == 303

        enclosure = client.get(enclosure_url)
        assert "Nyx" in enclosure.text
        cleaning = client.post(
            f"{enclosure_url}/cleanings",
            data={
                "csrf_token": csrf_from(enclosure.text),
                "occurred_at": occurred_value,
                "notes": "Substrate changed.",
            },
            follow_redirects=False,
        )
        assert cleaning.status_code == 303

        timeline = client.get(f"{profile_url}/timeline")
        assert timeline.status_code == 200
        for text in (
            "Animal registered",
            "Feeding recorded",
            "Weight recorded",
            "Length recorded",
            "Shed recorded",
            "Bath recorded",
            "Moved enclosure",
        ):
            assert text in timeline.text

        animal_list = client.get("/animals")
        assert animal_list.status_code == 200
        assert "Nyx" in animal_list.text
        feeding_history = client.get(f"{profile_url}/feedings")
        assert feeding_history.status_code == 200
        assert "Feeding history" in feeding_history.text
        assert "Fed eagerly." in feeding_history.text
        measurement_history = client.get(f"{profile_url}/measurements")
        assert measurement_history.status_code == 200
        assert "Measurement history" in measurement_history.text
        assert "After feeding." in measurement_history.text
        assert "Relaxed measurement." in measurement_history.text

        invalid_photo = client.post(
            f"{profile_url}/photo",
            data={
                "csrf_token": csrf_from(client.get(profile_url).text),
                "idempotency_key": "browser-invalid-photo-overview",
            },
            files={"photo": ("active.svg", b"<svg><script>1</script></svg>", "image/svg+xml")},
        )
        assert invalid_photo.status_code == 422
        assert "Rack A-03" in invalid_photo.text
        assert "925 mm" in invalid_photo.text


def test_keeper_deletes_accidental_duplicate_shed_through_confirmed_effective_history(
    tmp_path: Path,
) -> None:
    occurred = (datetime.now(UTC) - timedelta(days=2)).replace(microsecond=0)
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        form = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(form.text),
                "idempotency_key": "delete-record-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
            },
            follow_redirects=False,
        )
        animal_url = created.headers["location"]
        for index, note in enumerate(("Verified shed.", "Accidental duplicate shed.")):
            page = client.get(animal_url)
            response = client.post(
                f"{animal_url}/sheds",
                data={
                    "csrf_token": csrf_from(page.text),
                    "idempotency_key": f"delete-record-shed-{index}",
                    "occurred_at": (occurred + timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M"),
                    "blue_state": "false",
                    "completed": "true",
                    "result": "complete",
                    "notes": note,
                },
                follow_redirects=False,
            )
            assert response.status_code == 303

        animal_id = animal_url.rsplit("/", 1)[-1]
        with client.app.state.database_engine.connect() as connection:
            duplicate_id = connection.execute(
                text(
                    "SELECT event_id FROM domain_events WHERE stream_id=:animal_id "
                    "AND event_type='animal.shed_recorded' AND notes=:notes"
                ),
                {"animal_id": animal_id, "notes": "Accidental duplicate shed."},
            ).scalar_one()
            event_count_before = connection.execute(
                text("SELECT count(*) FROM domain_events")
            ).scalar_one()

        timeline = client.get(f"{animal_url}/timeline")
        effective = timeline.text.split('<details class="technical-audit"', 1)[0]
        assert effective.count("Delete record") == 2
        assert "Verified shed." in effective
        assert "Accidental duplicate shed." in effective
        assert 'class="record-actions"' in effective
        delete_url = f"{animal_url}/events/{duplicate_id}/delete"
        confirmation = client.get(delete_url)
        assert confirmation.status_code == 200
        assert "Delete shed record?" in confirmation.text
        assert "Accidental duplicate shed." in confirmation.text
        assert "This record will be removed from your animal's history and calculations." in (
            confirmation.text
        )
        assert 'role="alertdialog"' in confirmation.text
        assert "autofocus" in confirmation.text
        assert f'href="{animal_url}/timeline#record-{duplicate_id}"' in confirmation.text

        with client.app.state.database_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one()
                == event_count_before
            )
        assert client.post(delete_url, data={}).status_code == 403
        deleted = client.post(
            delete_url,
            data={
                "csrf_token": csrf_from(confirmation.text),
                "idempotency_key": "delete-record-confirmed",
            },
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert deleted.headers["location"].endswith("/timeline?record_deleted=1#effective-history")
        updated = client.get(deleted.headers["location"])
        standard_history = updated.text.split('<details class="technical-audit"', 1)[0]
        assert "Record deleted. History and calculations are updated." in standard_history
        assert "Verified shed." in standard_history
        assert "Accidental duplicate shed." not in standard_history
        assert "Accidental duplicate shed." in updated.text
        assert "Care record voided" in updated.text
        assert client.get(delete_url).status_code == 404
        assert (
            client.post(
                delete_url,
                data={
                    "csrf_token": csrf_from(updated.text),
                    "idempotency_key": "delete-record-double-void",
                },
            ).status_code
            == 404
        )

        with client.app.state.database_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one()
                == event_count_before + 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM domain_events WHERE event_id=:event_id "
                        "AND event_type='animal.shed_recorded'"
                    ),
                    {"event_id": duplicate_id},
                ).scalar_one()
                == 1
            )

        assert "Accidental duplicate shed." not in client.get("/search?q=Accidental+duplicate").text
        assert "Accidental duplicate shed." not in client.get("/reports/care").text
        assert "Accidental duplicate shed." not in client.get("/reports/care.csv").text

        more = client.get("/more")
        assert (
            client.post(
                "/logout", data={"csrf_token": csrf_from(more.text)}, follow_redirects=False
            ).status_code
            == 303
        )
        registration = client.get("/register")
        assert (
            client.post(
                "/register",
                data={
                    "csrf_token": csrf_from(registration.text),
                    "idempotency_key": "delete-record-other-household",
                    "collection_name": "Other Collection",
                    "timezone": "UTC",
                    "display_name": "Other Keeper",
                    "email": "other@example.com",
                    "password": "another correct horse battery staple",
                    "password_confirmation": "another correct horse battery staple",
                },
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert client.get(delete_url).status_code == 404
        other_page = client.get("/animals")
        assert (
            client.post(
                delete_url,
                data={
                    "csrf_token": csrf_from(other_page.text),
                    "idempotency_key": "delete-record-cross-household",
                },
            ).status_code
            == 404
        )


def test_enclosure_reassignment_is_identified_and_only_current_occupancy_is_shown(
    tmp_path: Path,
) -> None:
    first_move = (datetime.now(UTC) - timedelta(hours=2)).replace(microsecond=0)
    second_move = first_move + timedelta(hours=1)
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)

        animal_form = client.get("/animals/new")
        created_animal = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(animal_form.text),
                "name": "Nyx",
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
        animal_url = created_animal.headers["location"]

        enclosure_urls: list[str] = []
        for index, name in enumerate(("55 Gallon Tank", "10 Gallon Tank"), start=1):
            enclosure_form = client.get("/enclosures/new")
            created_enclosure = client.post(
                "/enclosures",
                data={
                    "csrf_token": csrf_from(enclosure_form.text),
                    "idempotency_key": f"browser-enclosure-reassignment-create-{index}",
                    "name": name,
                    "enclosure_type": "vivarium",
                    "notes": "",
                },
                follow_redirects=False,
            )
            assert created_enclosure.status_code == 303
            enclosure_urls.append(created_enclosure.headers["location"])

        for index, (enclosure_url, occurred_at) in enumerate(
            zip(enclosure_urls, (first_move, second_move), strict=True), start=1
        ):
            profile = client.get(animal_url)
            assigned = client.post(
                f"{animal_url}/enclosure",
                data={
                    "csrf_token": csrf_from(profile.text),
                    "idempotency_key": f"browser-enclosure-reassignment-assign-{index}",
                    "enclosure_id": enclosure_url.rsplit("/", 1)[-1],
                    "occurred_at": occurred_at.strftime("%Y-%m-%dT%H:%M"),
                    "notes": "",
                },
                follow_redirects=False,
            )
            assert assigned.status_code == 303

        current_enclosure_id = enclosure_urls[1].rsplit("/", 1)[-1]
        profile = client.get(animal_url)
        assert f'<a href="/enclosures/{current_enclosure_id}">10 Gallon Tank</a>' in profile.text

        first_enclosure = client.get(enclosure_urls[0])
        second_enclosure = client.get(enclosure_urls[1])
        assert "No animals are assigned here." in first_enclosure.text
        assert "Nyx" not in first_enclosure.text
        assert "Nyx" in second_enclosure.text

        timeline = client.get(f"{animal_url}/timeline")
        assert timeline.status_code == 200
        effective_history = timeline.text.split('<details class="technical-audit"', 1)[0]
        assert "Moved to 55 Gallon Tank" in effective_history
        assert "55 Gallon Tank → 10 Gallon Tank" in effective_history

        assignment_audits = [
            item
            for item in re.findall(r'<li id="event-[^"]+">.*?</li>', timeline.text, re.DOTALL)
            if "animal.enclosure_assigned v1" in item
        ]
        assert len(assignment_audits) == 2
        for item, name, enclosure_url in zip(
            assignment_audits,
            ("55 Gallon Tank", "10 Gallon Tank"),
            enclosure_urls,
            strict=True,
        ):
            assert name in item
            assert enclosure_url.rsplit("/", 1)[-1] in item
            assert "/void" not in item


def test_authenticated_keeper_can_edit_profile_and_reactivate_an_animal(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "name": "Nyx",
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
        profile_url = created.headers["location"]

        edit = client.get(f"{profile_url}/edit")
        updated = client.post(
            f"{profile_url}/edit",
            data={
                "csrf_token": csrf_from(edit.text),
                "idempotency_key": "browser-profile-update",
                "name": "Nysa",
                "species": "Python regius",
                "sex": "female",
                "morph": "Pastel",
                "genetics": "Pastel",
                "birth_hatch_date": "2022-05-01",
                "acquisition_date": "2023-01-15",
                "breeder_source": "Northside Reptiles",
                "notes": "Updated keeper note.",
            },
            follow_redirects=False,
        )
        assert updated.status_code == 303
        assert "Nysa" in client.get(profile_url).text

        profile = client.get(profile_url)
        archived = client.post(
            f"{profile_url}/status",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "browser-status-archive",
                "status": "archived",
                "notes": "No longer in active care.",
            },
            follow_redirects=False,
        )
        assert archived.status_code == 303
        assert "Archived" in client.get(profile_url).text

        profile = client.get(profile_url)
        reactivated = client.post(
            f"{profile_url}/status",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "browser-status-reactivate",
                "status": "active",
                "notes": "Returned to active care.",
            },
            follow_redirects=False,
        )
        assert reactivated.status_code == 303
        assert "Active" in client.get(profile_url).text


def test_authenticated_keeper_can_edit_and_archive_an_enclosure(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_enclosure = client.get("/enclosures/new")
        created = client.post(
            "/enclosures",
            data={
                "csrf_token": csrf_from(new_enclosure.text),
                "name": "Rack A-03",
                "enclosure_type": "tub",
                "notes": "Initial setup.",
            },
            follow_redirects=False,
        )
        enclosure_url = created.headers["location"]

        edit = client.get(f"{enclosure_url}/edit")
        assert edit.status_code == 200
        updated = client.post(
            f"{enclosure_url}/edit",
            data={
                "csrf_token": csrf_from(edit.text),
                "idempotency_key": "browser-enclosure-update",
                "name": "Rack A-04",
                "enclosure_type": "vivarium",
                "notes": "Upgraded habitat.",
            },
            follow_redirects=False,
        )
        assert updated.status_code == 303
        profile = client.get(enclosure_url)
        assert "Rack A-04" in profile.text
        assert "Upgraded habitat." in profile.text

        archived = client.post(
            f"{enclosure_url}/status",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "browser-enclosure-archive",
                "status": "archived",
                "notes": "Held in reserve.",
            },
            follow_redirects=False,
        )
        assert archived.status_code == 303
        assert "Archived" in client.get(enclosure_url).text


def test_authenticated_keeper_can_upload_and_view_a_processed_phone_profile_photo(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "name": "Nyx",
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
        profile_url = created.headers["location"]
        profile = client.get(profile_url)
        phone_photo = Image.effect_noise((3072, 4080), 65).convert("RGB")
        exif = Image.Exif()
        exif[274] = 6
        exif[271] = "Motorola"
        exif[272] = "Moto G 5G (2024)"
        exif[34853] = {
            1: "N",
            2: (IFDRational(40), IFDRational(0), IFDRational(0)),
            3: "W",
            4: (IFDRational(74), IFDRational(0), IFDRational(0)),
        }
        encoded = BytesIO()
        phone_photo.save(encoded, format="JPEG", quality=70, exif=exif)
        phone_photo.close()
        source_content = encoded.getvalue()
        assert len(source_content) > 5 * 1024 * 1024
        uploaded = client.post(
            f"{profile_url}/photo",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "browser-profile-photo",
            },
            files={"photo": ("nyx.jpg", source_content, "image/jpeg")},
            follow_redirects=False,
        )
        assert uploaded.status_code == 303

        profile = client.get(profile_url)
        match = re.search(r'src="(/attachments/[^"]+)"', profile.text)
        assert match is not None
        delivered = client.get(match.group(1))
        assert delivered.status_code == 200
        assert len(delivered.content) < len(source_content)
        assert delivered.headers["content-type"] == "image/jpeg"
        assert delivered.headers["content-disposition"] == 'inline; filename="profile-photo.jpg"'
        assert delivered.headers["cache-control"] == "private, immutable, max-age=31536000"
        assert delivered.headers["x-content-type-options"] == "nosniff"
        with Image.open(BytesIO(delivered.content)) as derivative:
            assert max(derivative.size) == 1600
            assert derivative.width > derivative.height
            assert not derivative.getexif()
            assert "exif" not in derivative.info
        assert client.get("/attachments/00000000-0000-0000-0000-000000000000").status_code == 404


def test_animal_list_and_profile_present_a_focused_keeper_experience(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "idempotency_key": "keeper-ux-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
                "morph": "Pastel",
            },
            follow_redirects=False,
        )
        profile_url = created.headers["location"]
        profile = client.get(profile_url)
        uploaded = client.post(
            f"{profile_url}/photo",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "keeper-ux-photo",
            },
            files={"photo": ("nyx.png", ONE_PIXEL_PNG, "image/png")},
            follow_redirects=False,
        )
        assert uploaded.status_code == 303

        animal_list = client.get("/animals")
        assert animal_list.status_code == 200
        assert "Nyx" in animal_list.text
        assert "Python regius" in animal_list.text
        assert "Pastel" in animal_list.text
        assert "Active" in animal_list.text
        assert 'alt="Profile photo of Nyx"' in animal_list.text

        profile = client.get(profile_url)
        assert "Care actions" in profile.text
        assert f'href="{profile_url}/feedings/new"' in profile.text
        assert f'href="{profile_url}/weights/new"' in profile.text
        assert f'action="{profile_url}/feedings"' not in profile.text
        assert f'action="{profile_url}/weights"' not in profile.text
        assert profile.text.index("Care actions") < profile.text.index("Recent care")
        assert profile.text.index("Recent care") < profile.text.index("Care schedule")

        care_pages = {
            "feedings/new": ("Record feeding", f"{profile_url}/feedings"),
            "weights/new": ("Record weight", f"{profile_url}/weights"),
            "lengths/new": ("Record length", f"{profile_url}/lengths"),
            "sheds/new": ("Record shed", f"{profile_url}/sheds"),
            "baths/new": ("Record bath", f"{profile_url}/baths"),
        }
        for route, (title, action) in care_pages.items():
            page = client.get(f"{profile_url}/{route}")
            assert page.status_code == 200, route
            assert title in page.text
            assert f'action="{action}"' in page.text
            assert 'href="' + profile_url + '"' in page.text
        feeding_form = client.get(f"{profile_url}/feedings/new")
        assert '<details class="form-advanced">' in feeding_form.text
        assert "Add food to Inventory first" in feeding_form.text
        assert "Prey type" not in feeding_form.text
        assert "Prey size" not in feeding_form.text
        assert "Prey weight" not in feeding_form.text
        assert "Preparation method" not in feeding_form.text
        assert "Do not deduct inventory" not in feeding_form.text


def test_keeper_histories_show_effective_values_and_hide_voided_facts(tmp_path: Path) -> None:
    occurred_value = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    older_value = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "idempotency_key": "effective-history-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
            },
            follow_redirects=False,
        )
        profile_url = created.headers["location"]
        create_food_inventory(client, idempotency_prefix="effective-history-food")
        csrf = csrf_from(client.get(profile_url).text)
        records = (
            (
                "feedings",
                occurred_value,
                {
                    "prey_type": "mouse",
                    "prey_size": "medium",
                    "prey_weight_grams": "28",
                    "preparation_method": "frozen_thawed",
                    "quantity": "2",
                    "outcome": "accepted",
                    "notes": "Original feeding.",
                },
            ),
            ("weights", older_value, {"weight_grams": "510", "notes": "Original weight."}),
            (
                "lengths",
                occurred_value,
                {"length_mm": "925", "notes": "Measured relaxed."},
            ),
        )
        for index, (route, event_time, facts) in enumerate(records):
            feeding_fields = (
                inventory_feeding_fields(client, profile_url, amount="2")
                if route == "feedings"
                else {}
            )
            response = client.post(
                f"{profile_url}/{route}",
                data={
                    "csrf_token": csrf,
                    "idempotency_key": f"effective-history-{index}",
                    "occurred_at": event_time,
                    **facts,
                    **feeding_fields,
                },
                follow_redirects=False,
            )
            assert response.status_code == 303

        profile = client.get(profile_url)
        assert "Small Frozen Mouse" in profile.text
        assert "510 g" in profile.text
        assert "925 mm" in profile.text
        assert "Animal registered" not in profile.text
        assert "Profile photo selected" not in profile.text
        assert "Inventory stock consumed" not in profile.text

        feeding_history = client.get(f"{profile_url}/feedings")
        effective_feeding = feeding_history.text.split('<details class="technical-audit"', 1)[0]
        assert "Small Frozen Mouse" in effective_feeding
        assert "2 each" in effective_feeding
        assert "Frozen / thawed" in effective_feeding
        assert "Accepted" in effective_feeding

        measurement_history = client.get(f"{profile_url}/measurements")
        effective_measurements = measurement_history.text.split(
            '<details class="technical-audit"', 1
        )[0]
        assert "510 g" in effective_measurements
        assert "925 mm" in effective_measurements
        timeline = client.get(f"{profile_url}/timeline")
        effective_timeline = timeline.text.split('<details class="technical-audit"', 1)[0]
        assert effective_timeline.index("925 mm") < effective_timeline.index("510 g")

        animal_id = profile_url.rsplit("/", 1)[-1]
        with client.app.state.database_engine.connect() as connection:
            stored_events = dict(
                connection.execute(
                    text(
                        "SELECT event_type,event_id FROM domain_events "
                        "WHERE stream_id=:animal_id AND event_type IN "
                        "('animal.feeding_recorded','animal.weight_recorded')"
                    ),
                    {"animal_id": animal_id},
                ).all()
            )

        correction_url = f"{profile_url}/events/{stored_events['animal.feeding_recorded']}/correct"
        correction_form = client.get(correction_url)
        corrected = client.post(
            correction_url,
            data={
                "csrf_token": csrf_from(correction_form.text),
                "idempotency_key": "effective-history-correction",
                "occurred_at": occurred_value,
                "prey_type": "rat",
                "prey_size": "large",
                "prey_weight_grams": "50",
                "preparation_method": "other",
                "quantity": "1",
                "outcome": "refused",
                "notes": "Corrected feeding.",
            },
            follow_redirects=False,
        )
        assert corrected.status_code == 303

        with client.app.state.database_engine.connect() as connection:
            correction_event_id = connection.execute(
                text(
                    "SELECT event_id FROM domain_events "
                    "WHERE stream_id=:animal_id AND event_type='animal.feeding_corrected'"
                ),
                {"animal_id": animal_id},
            ).scalar_one()

        timeline = client.get(f"{profile_url}/timeline")
        correction_voided = client.post(
            f"{profile_url}/events/{correction_event_id}/void",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "effective-history-correction-void",
                "reason": "Correction was wrong.",
            },
            follow_redirects=False,
        )
        assert correction_voided.status_code == 303
        effective_feeding = client.get(f"{profile_url}/feedings").text.split(
            '<details class="technical-audit"', 1
        )[0]
        assert "Small Frozen Mouse" in effective_feeding

        timeline = client.get(f"{profile_url}/timeline")
        correction_reinstated = client.post(
            f"{profile_url}/events/{correction_event_id}/reinstate",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "effective-history-correction-reinstate",
                "reason": "Correction was verified.",
            },
            follow_redirects=False,
        )
        assert correction_reinstated.status_code == 303

        timeline = client.get(f"{profile_url}/timeline")
        voided = client.post(
            f"{profile_url}/events/{stored_events['animal.weight_recorded']}/void",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "effective-history-void",
                "reason": "Wrong animal.",
            },
            follow_redirects=False,
        )
        assert voided.status_code == 303

        feeding_history = client.get(f"{profile_url}/feedings")
        effective_feeding = feeding_history.text.split('<details class="technical-audit"', 1)[0]
        assert "Small Frozen Mouse" in effective_feeding
        assert "2 each" in effective_feeding
        assert "Refused" in effective_feeding

        measurement_history = client.get(f"{profile_url}/measurements")
        effective_measurements = measurement_history.text.split(
            '<details class="technical-audit"', 1
        )[0]
        assert "510 g" not in effective_measurements
        assert "925 mm" in effective_measurements

        timeline = client.get(f"{profile_url}/timeline")
        effective_timeline = timeline.text.split('<details class="technical-audit"', 1)[0]
        assert "Small Frozen Mouse" in effective_timeline
        assert "925 mm" in effective_timeline
        assert "510 g" not in effective_timeline
        assert "Technical audit" in timeline.text
        assert "event type" in timeline.text.lower()


def test_authenticated_keeper_can_correct_void_and_reinstate_a_care_entry(tmp_path: Path) -> None:
    occurred_at = (datetime.now(UTC) - timedelta(days=1)).replace(microsecond=0)
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "name": "Nyx",
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
        profile_url = created.headers["location"]
        profile = client.get(profile_url)
        weight = client.post(
            f"{profile_url}/weights",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "browser-record-weight",
                "occurred_at": occurred_at.strftime("%Y-%m-%dT%H:%M"),
                "weight_grams": "510",
                "notes": "Initial scale reading.",
            },
            follow_redirects=False,
        )
        assert weight.status_code == 303

        timeline_url = f"{profile_url}/timeline"
        timeline = client.get(timeline_url)
        correction_match = re.search(
            r'href="([^"]+/events/([0-9a-f-]{36})/correct)"', timeline.text
        )
        assert correction_match is not None
        correction_url, target_event_id = correction_match.groups()
        correction_form = client.get(correction_url)
        corrected = client.post(
            correction_url,
            data={
                "csrf_token": csrf_from(correction_form.text),
                "idempotency_key": "browser-correct-weight",
                "occurred_at": occurred_at.strftime("%Y-%m-%dT%H:%M"),
                "weight_grams": "530",
                "notes": "Corrected scale reading.",
            },
            follow_redirects=False,
        )
        assert corrected.status_code == 303
        timeline = client.get(timeline_url)
        assert "Weight corrected" in timeline.text
        assert "Corrected scale reading." in timeline.text
        assert "Weight recorded" in timeline.text

        voided = client.post(
            f"{profile_url}/events/{target_event_id}/void",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "browser-void-weight",
                "reason": "Duplicate measurement.",
            },
            follow_redirects=False,
        )
        assert voided.status_code == 303
        timeline = client.get(timeline_url)
        assert "Care record voided" in timeline.text

        reinstated = client.post(
            f"{profile_url}/events/{target_event_id}/reinstate",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "browser-reinstate-weight",
                "reason": "Duplicate review corrected.",
            },
            follow_redirects=False,
        )
        assert reinstated.status_code == 303
        timeline = client.get(timeline_url)
        assert "Care record reinstated" in timeline.text
        assert "Weight corrected" in timeline.text


def test_decimal_weight_survives_forms_history_analytics_and_effective_state(
    tmp_path: Path,
) -> None:
    occurred_at = (datetime.now(UTC) - timedelta(days=2)).replace(microsecond=0)
    occurred_value = occurred_at.strftime("%Y-%m-%dT%H:%M")
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "idempotency_key": "decimal-weight-animal",
                "name": "Onyx",
                "species": "Pandinus imperator",
                "sex": "unknown",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        profile_url = created.headers["location"]

        weight_form = client.get(f"{profile_url}/weights/new")
        assert 'name="weight_grams" type="number" inputmode="decimal"' in weight_form.text
        assert 'min="0.001" step="0.001"' in weight_form.text
        csrf = csrf_from(weight_form.text)
        weight_data = {
            "csrf_token": csrf,
            "idempotency_key": "record-decimal-weight",
            "occurred_at": occurred_value,
            "weight_grams": "42.5",
            "notes": "Exact decimal reading.",
        }
        first = client.post(f"{profile_url}/weights", data=weight_data, follow_redirects=False)
        retry = client.post(f"{profile_url}/weights", data=weight_data, follow_redirects=False)
        assert first.status_code == retry.status_code == 303

        timeline_url = f"{profile_url}/timeline"
        timeline = client.get(timeline_url)
        effective = timeline.text.split('<details class="technical-audit"', 1)[0]
        assert "Recorded weight" in effective
        assert "42.5 g" in effective
        correction_match = re.search(
            r'href="([^"]+/events/([0-9a-f-]{36})/correct)"', timeline.text
        )
        assert correction_match is not None
        correction_url, target_event_id = correction_match.groups()
        correction_form = client.get(correction_url)
        assert 'value="42.5"' in correction_form.text
        assert 'inputmode="decimal"' in correction_form.text
        corrected = client.post(
            correction_url,
            data={
                "csrf_token": csrf_from(correction_form.text),
                "idempotency_key": "correct-decimal-weight",
                "occurred_at": occurred_value,
                "weight_grams": "8.175",
                "notes": "Corrected exact reading.",
            },
            follow_redirects=False,
        )
        assert corrected.status_code == 303

        excess_precision_form = client.get(f"{profile_url}/weights/new")
        rejected = client.post(
            f"{profile_url}/weights",
            data={
                "csrf_token": csrf_from(excess_precision_form.text),
                "idempotency_key": "reject-overprecise-weight",
                "occurred_at": occurred_value,
                "weight_grams": "8.2579",
            },
        )
        assert rejected.status_code == 422
        assert "no more than 3 decimal places" in rejected.text

        second_form = client.get(f"{profile_url}/weights/new")
        second = client.post(
            f"{profile_url}/weights",
            data={
                "csrf_token": csrf_from(second_form.text),
                "idempotency_key": "record-subgram-weight",
                "occurred_at": (occurred_at + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "weight_grams": "0.875",
            },
            follow_redirects=False,
        )
        assert second.status_code == 303

        timeline = client.get(timeline_url)
        effective = timeline.text.split('<details class="technical-audit"', 1)[0]
        assert "8.175 g" in effective
        assert "0.875 g" in effective
        measurements = client.get(
            f"/api/v1/animals/{profile_url.rsplit('/', 1)[-1]}/analytics/measurements"
        )
        assert measurements.status_code == 200
        assert [point["value"] for point in measurements.json()["points"]] == [8.175, 0.875]

        voided = client.post(
            f"{profile_url}/events/{target_event_id}/void",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "void-decimal-weight",
                "reason": "Temporarily exclude measurement.",
            },
            follow_redirects=False,
        )
        assert voided.status_code == 303
        assert [
            point["value"]
            for point in client.get(
                f"/api/v1/animals/{profile_url.rsplit('/', 1)[-1]}/analytics/measurements"
            ).json()["points"]
        ] == [0.875]

        timeline = client.get(timeline_url)
        reinstated = client.post(
            f"{profile_url}/events/{target_event_id}/reinstate",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "reinstate-decimal-weight",
                "reason": "Measurement verified.",
            },
            follow_redirects=False,
        )
        assert reinstated.status_code == 303
        assert [
            point["value"]
            for point in client.get(
                f"/api/v1/animals/{profile_url.rsplit('/', 1)[-1]}/analytics/measurements"
            ).json()["points"]
        ] == [8.175, 0.875]


def test_browser_corrections_cover_each_supported_care_contract(tmp_path: Path) -> None:
    occurred_value = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "idempotency_key": "browser-correction-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
            },
            follow_redirects=False,
        )
        profile_url = created.headers["location"]
        create_food_inventory(client, idempotency_prefix="browser-correction-food")
        profile = client.get(profile_url)
        csrf = csrf_from(profile.text)
        records = (
            (
                "animal.feeding_recorded",
                "feedings",
                {
                    "prey_type": "rat",
                    "prey_size": "small",
                    "prey_weight_grams": "42",
                    "preparation_method": "frozen_thawed",
                    "quantity": "1",
                    "outcome": "accepted",
                },
            ),
            ("animal.length_recorded", "lengths", {"length_mm": "900"}),
            (
                "animal.shed_recorded",
                "sheds",
                {"blue_state": "false", "completed": "true", "result": "complete"},
            ),
        )
        for index, (_, route, values) in enumerate(records):
            feeding_fields = (
                inventory_feeding_fields(client, profile_url) if route == "feedings" else {}
            )
            response = client.post(
                f"{profile_url}/{route}",
                data={
                    "csrf_token": csrf,
                    "idempotency_key": f"browser-care-record-{index}",
                    "occurred_at": occurred_value,
                    "notes": "Original keeper entry.",
                    **values,
                    **feeding_fields,
                },
                follow_redirects=False,
            )
            assert response.status_code == 303

        animal_id = profile_url.rsplit("/", 1)[-1]
        with client.app.state.database_engine.connect() as connection:
            stored_events = dict(
                connection.execute(
                    text(
                        "SELECT event_type,event_id FROM domain_events WHERE stream_id=:animal_id"
                    ),
                    {"animal_id": animal_id},
                ).all()
            )

        correction_values = {
            "animal.feeding_recorded": {
                "prey_type": "mouse",
                "prey_size": "medium",
                "prey_weight_grams": "",
                "preparation_method": "other",
                "quantity": "2",
                "outcome": "refused",
            },
            "animal.length_recorded": {"length_mm": "915"},
            "animal.shed_recorded": {
                "blue_state": "true",
                "completed": "false",
                "result": "",
            },
        }
        for index, event_type in enumerate(correction_values):
            correction_url = f"{profile_url}/events/{stored_events[event_type]}/correct"
            form = client.get(correction_url)
            assert form.status_code == 200
            corrected = client.post(
                correction_url,
                data={
                    "csrf_token": csrf_from(form.text),
                    "idempotency_key": f"browser-care-correction-{index}",
                    "occurred_at": occurred_value,
                    "notes": "Corrected keeper entry.",
                    **correction_values[event_type],
                },
                follow_redirects=False,
            )
            assert corrected.status_code == 303

        with client.app.state.database_engine.connect() as connection:
            corrected_types = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT event_type FROM domain_events "
                        "WHERE stream_id=:animal_id AND event_type LIKE 'animal.%_corrected'"
                    ),
                    {"animal_id": animal_id},
                )
            }
        assert corrected_types == {
            "animal.feeding_corrected",
            "animal.length_corrected",
            "animal.shed_corrected",
        }

        registration_correction = client.get(
            f"{profile_url}/events/{stored_events['animal.registered']}/correct"
        )
        assert registration_correction.status_code == 422
        assert "cannot be corrected" in registration_correction.text


def test_owner_can_request_and_schedule_basic_local_backups(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)

        settings = client.get("/settings/backups")
        assert settings.status_code == 200
        assert "Backup and restore" in settings.text

        requested = client.post(
            "/settings/backups/run",
            data={
                "csrf_token": csrf_from(settings.text),
                "idempotency_key": "browser-backup-now",
            },
            follow_redirects=False,
        )
        assert requested.status_code == 303
        assert requested.headers["location"] == "/settings/backups"

        settings = client.get("/settings/backups")
        assert "Queued" in settings.text
        assert "Manual" in settings.text
        scheduled = client.post(
            "/settings/backups/schedule",
            data={
                "csrf_token": csrf_from(settings.text),
                "enabled": "false",
                "interval_seconds": "43200",
            },
            follow_redirects=False,
        )
        assert scheduled.status_code == 303
        settings = client.get("/settings/backups")
        assert "Schedule disabled" in settings.text
        assert "Every 12 hours" in settings.text
        assert '<option value="false" selected>Disabled</option>' in settings.text
        assert '<option value="43200" selected>Every 12 hours</option>' in settings.text
        with client.app.state.database_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM backup_requests")).scalar_one() == 1
            )
            assert connection.execute(
                text("SELECT enabled,interval_seconds FROM backup_schedules")
            ).one() == (0, 43200)


def test_phase4_pages_and_commands_require_a_current_session(tmp_path: Path) -> None:
    resource_id = "00000000-0000-0000-0000-000000000001"
    event_id = "00000000-0000-0000-0000-000000000002"
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        client.cookies.clear()

        for path in (
            "/home",
            "/animals",
            "/animals/new",
            f"/animals/{resource_id}",
            f"/animals/{resource_id}/edit",
            f"/animals/{resource_id}/feedings/new",
            f"/animals/{resource_id}/weights/new",
            f"/animals/{resource_id}/lengths/new",
            f"/animals/{resource_id}/sheds/new",
            f"/animals/{resource_id}/baths/new",
            f"/animals/{resource_id}/timeline",
            f"/animals/{resource_id}/feedings",
            f"/animals/{resource_id}/measurements",
            f"/animals/{resource_id}/events/{event_id}/correct",
            "/enclosures",
            "/enclosures/new",
            f"/enclosures/{resource_id}",
            f"/enclosures/{resource_id}/edit",
            "/settings/backups",
            f"/attachments/{resource_id}",
        ):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303, path
            assert response.headers["location"] == "/login"

        for path in (
            "/animals",
            f"/animals/{resource_id}/edit",
            f"/animals/{resource_id}/status",
            f"/animals/{resource_id}/enclosure",
            f"/animals/{resource_id}/feedings",
            f"/animals/{resource_id}/weights",
            f"/animals/{resource_id}/lengths",
            f"/animals/{resource_id}/sheds",
            f"/animals/{resource_id}/baths",
            f"/animals/{resource_id}/photo",
            f"/animals/{resource_id}/events/{event_id}/correct",
            f"/animals/{resource_id}/events/{event_id}/void",
            f"/animals/{resource_id}/events/{event_id}/reinstate",
            "/enclosures",
            f"/enclosures/{resource_id}/edit",
            f"/enclosures/{resource_id}/status",
            f"/enclosures/{resource_id}/cleanings",
            f"/enclosures/{resource_id}/water-changes",
            "/settings/backups/run",
            "/settings/backups/schedule",
        ):
            response = client.post(
                path,
                data={"csrf_token": "missing-session"},
                follow_redirects=False,
            )
            assert response.status_code == 303, path
            assert response.headers["location"] == "/login"


def test_phase4_missing_resources_fail_closed_without_tenant_disclosure(tmp_path: Path) -> None:
    missing_id = "00000000-0000-0000-0000-000000000001"
    missing_event = "00000000-0000-0000-0000-000000000002"
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)

        for path in (
            f"/animals/{missing_id}",
            "/animals/not-a-uuid",
            f"/animals/{missing_id}/edit",
            f"/animals/{missing_id}/timeline",
            f"/animals/{missing_id}/feedings",
            f"/animals/{missing_id}/measurements",
            f"/animals/{missing_id}/events/{missing_event}/correct",
            f"/enclosures/{missing_id}",
            "/enclosures/not-a-uuid",
            f"/enclosures/{missing_id}/edit",
            f"/attachments/{missing_id}",
            "/attachments/not-a-uuid",
        ):
            assert client.get(path).status_code == 404, path

        csrf = csrf_from(client.get("/more").text)
        for index, path in enumerate(
            (
                f"/animals/{missing_id}/edit",
                f"/animals/{missing_id}/status",
                f"/animals/{missing_id}/enclosure",
                f"/animals/{missing_id}/feedings",
                f"/animals/{missing_id}/weights",
                f"/animals/{missing_id}/lengths",
                f"/animals/{missing_id}/sheds",
                f"/animals/{missing_id}/baths",
                f"/animals/{missing_id}/photo",
                f"/animals/{missing_id}/events/{missing_event}/correct",
                f"/animals/{missing_id}/events/{missing_event}/void",
                f"/animals/{missing_id}/events/{missing_event}/reinstate",
                f"/enclosures/{missing_id}/edit",
                f"/enclosures/{missing_id}/status",
                f"/enclosures/{missing_id}/cleanings",
                f"/enclosures/{missing_id}/water-changes",
            )
        ):
            response = client.post(
                path,
                data={
                    "csrf_token": csrf,
                    "idempotency_key": f"missing-resource-{index}",
                    "occurred_at": "2026-08-07T12:00",
                },
            )
            assert response.status_code == 404, path


def test_backup_controls_require_household_management_capability(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        with client.app.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE authorization_memberships SET role='viewer'"))

        settings = client.get("/settings/backups")
        assert settings.status_code == 403
        csrf = client.cookies.get("snaketracker_csrf")
        assert csrf is not None
        for path in ("/settings/backups/run", "/settings/backups/schedule"):
            response = client.post(
                path,
                data={
                    "csrf_token": csrf,
                    "idempotency_key": "viewer-backup",
                    "enabled": "true",
                    "interval_seconds": "21600",
                },
            )
            assert response.status_code == 403


def test_phase4_invalid_session_cookie_is_rejected_and_audited(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        client.cookies.set("snaketracker_session", "invalid-session-token")

        response = client.get("/animals", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        with client.app.state.database_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM security_audit "
                        "WHERE action='protected_request' AND outcome='denied'"
                    )
                ).scalar_one()
                >= 1
            )


def test_phase4_rejects_non_form_commands_and_normalizes_aware_timestamps(
    tmp_path: Path,
) -> None:
    with client_for(tmp_path) as client:
        login = client.get("/login", follow_redirects=False)
        assert login.status_code == 303
        assert login.headers["location"] == "/setup"
        setup_and_sign_in(client)

        invalid_command = client.post(
            "/animals",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        assert invalid_command.status_code == 403
        invalid_logout = client.post(
            "/logout",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        assert invalid_logout.status_code == 403

        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "idempotency_key": "aware-timestamp-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
            },
            follow_redirects=False,
        )
        profile_url = created.headers["location"]
        profile = client.get(profile_url)
        recorded = client.post(
            f"{profile_url}/weights",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "aware-timestamp-weight",
                "occurred_at": "2026-08-07T14:00:00+02:00",
                "weight_grams": "500",
            },
            follow_redirects=False,
        )
        assert recorded.status_code == 303
        animal_id = profile_url.rsplit("/", 1)[-1]
        with client.app.state.database_engine.connect() as connection:
            occurred_at = connection.execute(
                text(
                    "SELECT occurred_at FROM domain_events "
                    "WHERE stream_id=:animal_id AND event_type='animal.weight_recorded'"
                ),
                {"animal_id": animal_id},
            ).scalar_one()
        assert occurred_at.startswith("2026-08-07T12:00:00")


def test_care_times_use_household_timezone_for_entry_and_display(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        setup_and_sign_in(client, timezone="America/New_York")
        new_animal = client.get("/animals/new")
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf_from(new_animal.text),
                "idempotency_key": "household-time-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
            },
            follow_redirects=False,
        )
        profile_url = created.headers["location"]
        profile = client.get(profile_url)
        assert "When (America/New_York)" in profile.text
        recorded = client.post(
            f"{profile_url}/weights",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "household-time-weight",
                "occurred_at": "2026-08-07T14:00",
                "weight_grams": "500",
            },
            follow_redirects=False,
        )
        assert recorded.status_code == 303

        timeline = client.get(f"{profile_url}/timeline")
        assert "2026-08-07 14:00 America/New_York" in timeline.text
        animal_id = profile_url.rsplit("/", 1)[-1]
        with client.app.state.database_engine.connect() as connection:
            occurred_at = connection.execute(
                text(
                    "SELECT occurred_at FROM domain_events "
                    "WHERE stream_id=:animal_id AND event_type='animal.weight_recorded'"
                ),
                {"animal_id": animal_id},
            ).scalar_one()
        assert occurred_at.startswith("2026-08-07T18:00:00")


def test_phase4_forms_return_accessible_validation_errors(tmp_path: Path) -> None:
    occurred_value = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    with client_for(tmp_path) as client:
        setup_and_sign_in(client)
        animal_form = client.get("/animals/new")
        csrf = csrf_from(animal_form.text)
        invalid_animal = client.post(
            "/animals",
            data={"csrf_token": csrf, "name": "", "species": ""},
        )
        assert invalid_animal.status_code == 422
        assert 'role="alert"' in invalid_animal.text
        created = client.post(
            "/animals",
            data={
                "csrf_token": csrf,
                "idempotency_key": "validation-animal",
                "name": "Nyx",
                "species": "Python regius",
                "sex": "female",
            },
            follow_redirects=False,
        )
        animal_url = created.headers["location"]
        animal_id = animal_url.rsplit("/", 1)[-1]

        enclosure_form = client.get("/enclosures/new")
        invalid_enclosure = client.post(
            "/enclosures",
            data={"csrf_token": csrf_from(enclosure_form.text), "name": "", "enclosure_type": ""},
        )
        assert invalid_enclosure.status_code == 422
        created_enclosure = client.post(
            "/enclosures",
            data={
                "csrf_token": csrf_from(enclosure_form.text),
                "idempotency_key": "validation-enclosure",
                "name": "Rack A-03",
                "enclosure_type": "tub",
            },
            follow_redirects=False,
        )
        enclosure_url = created_enclosure.headers["location"]
        enclosure_id = enclosure_url.rsplit("/", 1)[-1]

        invalid_posts = (
            (f"{animal_url}/edit", {"name": "", "species": "Python regius"}),
            (f"{animal_url}/status", {"status": "unknown"}),
            (f"{animal_url}/enclosure", {"enclosure_id": "not-a-uuid"}),
            (f"{animal_url}/feedings", {"occurred_at": "bad", "quantity": "x"}),
            (f"{animal_url}/weights", {"occurred_at": occurred_value, "weight_grams": "x"}),
            (f"{animal_url}/lengths", {"occurred_at": occurred_value, "length_mm": "x"}),
            (
                f"{animal_url}/sheds",
                {"occurred_at": occurred_value, "blue_state": "maybe", "completed": "true"},
            ),
            (f"{animal_url}/baths", {"occurred_at": occurred_value, "duration_minutes": "x"}),
            (f"{enclosure_url}/edit", {"name": "", "enclosure_type": "tub"}),
            (f"{enclosure_url}/status", {"status": "unknown"}),
            (f"{enclosure_url}/cleanings", {"occurred_at": "bad"}),
            (f"{enclosure_url}/water-changes", {"occurred_at": "bad"}),
            (
                "/settings/backups/schedule",
                {"enabled": "true", "interval_seconds": "60"},
            ),
        )
        for index, (path, values) in enumerate(invalid_posts):
            response = client.post(
                path,
                data={
                    "csrf_token": csrf,
                    "idempotency_key": f"invalid-form-{index}",
                    **values,
                },
            )
            assert response.status_code == 422, path
            assert 'role="alert"' in response.text, path

        invalid_photo = client.post(
            f"{animal_url}/photo",
            data={"csrf_token": csrf, "idempotency_key": "invalid-svg-photo"},
            files={"photo": ("active.svg", b"<svg><script>1</script></svg>", "image/svg+xml")},
        )
        assert invalid_photo.status_code == 422
        assert 'role="alert"' in invalid_photo.text

        profile = client.get(animal_url)
        weight = client.post(
            f"{animal_url}/weights",
            data={
                "csrf_token": csrf_from(profile.text),
                "idempotency_key": "validation-weight",
                "occurred_at": occurred_value,
                "weight_grams": "500",
            },
            follow_redirects=False,
        )
        assert weight.status_code == 303
        timeline = client.get(f"{animal_url}/timeline")
        weight_event = re.search(
            rf"/animals/{animal_id}/events/([0-9a-f-]{{36}})/correct", timeline.text
        )
        assert weight_event is not None
        invalid_correction = client.post(
            f"{animal_url}/events/{weight_event.group(1)}/correct",
            data={
                "csrf_token": csrf_from(timeline.text),
                "idempotency_key": "invalid-weight-correction",
                "occurred_at": occurred_value,
                "weight_grams": "not-a-number",
            },
        )
        assert invalid_correction.status_code == 422
        assert 'role="alert"' in invalid_correction.text

        assert animal_id
        assert enclosure_id
