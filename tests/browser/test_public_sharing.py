"""Owner photo albums connect to deliberately published, revocable visitor pages."""

import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from tests.browser.test_multispecies_workflow import PHOTO, _csrf, _register, _setup

ROOT = Path(__file__).parents[2]


def test_concurrent_edits_are_recoverable_and_invalid_public_files_are_generic(
    tmp_path, monkeypatch
):
    from snaketracker.application.attachments import AttachmentValidationError
    from snaketracker.application.sharing import SharingService
    from snaketracker.platform.events.store import (
        ExpectedVersionConflictError,
        IdempotencyConflictError,
    )

    with sharing_client(tmp_path) as client:
        _setup(client)
        animal = _register(client, "Conflict fixture", "snake", "Python regius")
        media = album_photo(client, animal)
        for conflict in [ExpectedVersionConflictError, IdempotencyConflictError]:

            def fail(*args, error_type=conflict, **kwargs):
                raise error_type("internal command information")

            operations = [
                ("configure_household", "/sharing", {}),
                ("configure_animal", animal + "/sharing", {}),
                ("update_photo", animal + "/album/" + media, {"position": "1"}),
                ("upload_photo", animal + "/album/upload", {}),
            ]
            for method, route, data in operations:
                with monkeypatch.context() as patch:
                    patch.setattr(SharingService, method, fail)
                    response = post_form(
                        client,
                        route,
                        data=data,
                        files={"photo": ("photo.png", PHOTO, "image/png")}
                        if method == "upload_photo"
                        else None,
                    )
                    assert response.status_code == 409
                    assert "reload" in response.text
                    assert "internal command" not in response.text

            with monkeypatch.context() as patch:
                patch.setattr(SharingService, "remove_photo", fail)
                edit = client.get(animal + "/album/" + media)
                response = client.post(
                    animal + "/album/" + media + "/remove",
                    data={
                        "csrf_token": _csrf(edit.text),
                        "idempotency_key": "remove-conflict",
                    },
                )
                assert response.status_code == 409

        def invalid_photo(*args, **kwargs):
            raise AttachmentValidationError("private storage location")

        monkeypatch.setattr(SharingService, "public_photo", invalid_photo)
        for method in [client.get, client.head]:
            response = method("/m/unavailable")
            assert response.status_code == 404
            assert "no-store" in response.headers["cache-control"]
            assert "private storage" not in response.text


def sharing_client(tmp_path, *, enabled=True):
    database = tmp_path / "sharing.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    return TestClient(
        build_application(
            Settings(
                environment=Environment.TEST,
                database_path=database,
                runtime_secret=SecretStr("sharing-fictional-runtime-secret-32-bytes"),
                session_cookie_secure=False,
                public_sharing_enabled=enabled,
            )
        )
    )


def post_form(client, path, *, data=None, files=None):
    page = client.get(path.rsplit("/upload", 1)[0] if path.endswith("/upload") else path)
    assert page.status_code == 200, page.text
    return client.post(
        path,
        data={
            "csrf_token": _csrf(page.text),
            "idempotency_key": re.search(r'name="idempotency_key" value="([^"]+)"', page.text)[1],
            **(data or {}),
        },
        files=files,
        follow_redirects=False,
    )


def album_photo(client, animal):
    response = post_form(
        client,
        animal + "/album/upload",
        data={"caption": "Sunlit scales"},
        files={"photo": ("photo.png", PHOTO, "image/png")},
    )
    assert response.status_code == 303, response.text
    album = client.get(animal + "/album")
    media = re.search(r'data-media-id="([^"]+)"', album.text)[1]
    return media


def publish(client, animal, media):
    assert (
        post_form(
            client,
            "/sharing",
            data={
                "title": "Forest collection",
                "description": "A deliberately public introduction.",
                "slug": "forest",
                "enabled": "true",
            },
        ).status_code
        == 303
    )
    assert (
        post_form(
            client,
            animal + "/album/" + media,
            data={
                "caption": "Sunlit scales",
                "position": "1",
                "is_public": "true",
            },
        ).status_code
        == 303
    )
    assert (
        post_form(
            client,
            animal + "/sharing",
            data={
                "title": "Ember",
                "species": "Python regius",
                "description": "A curious observer.",
                "slug": "ember",
                "is_public": "true",
                "cover_media_id": media,
            },
        ).status_code
        == 303
    )
    settings = client.get(animal + "/sharing")
    public_path = re.search(r'data-public-url="([^"]+)"', settings.text)[1]
    collection_path = re.search(r'data-public-url="([^"]+)"', client.get("/sharing").text)[1]
    return public_path, collection_path


def test_native_textarea_line_endings_are_normalized_for_every_sharing_form(tmp_path):
    with sharing_client(tmp_path) as client:
        _setup(client)
        animal = _register(client, "Multiline fixture", "snake", "Python regius")
        introduction = "First line\r\nSecond line"
        response = post_form(
            client,
            "/sharing",
            data={"title": "Collection", "slug": "collection", "description": introduction},
        )
        assert response.status_code == 303, response.text
        response = post_form(
            client,
            animal + "/sharing",
            data={"title": "Ember", "slug": "ember", "description": introduction},
        )
        assert response.status_code == 303, response.text
        response = post_form(
            client,
            animal + "/album/upload",
            data={"caption": introduction},
            files={"photo": ("photo.png", PHOTO, "image/png")},
        )
        assert response.status_code == 303, response.text
        media = re.search(r'data-media-id="([^"]+)"', client.get(animal + "/album").text)[1]
        response = post_form(
            client,
            animal + "/album/" + media,
            data={"caption": "Updated\r\ncaption", "position": "1"},
        )
        assert response.status_code == 303, response.text
        # Native CRLF encoding must not consume extra characters from the text limit.
        bounded = "a" * 1998 + "\r\nb"
        response = post_form(
            client,
            "/sharing",
            data={"title": "Collection", "slug": "collection", "description": bounded},
        )
        assert response.status_code == 303, response.text
        with client.app.state.database_engine.connect() as connection:
            assert connection.execute(
                text("SELECT description FROM sharing_household_current")
            ).scalar_one() == bounded.replace("\r\n", "\n")
            assert connection.execute(
                text("SELECT description FROM sharing_animal_current")
            ).scalar_one() == introduction.replace("\r\n", "\n")
            assert (
                connection.execute(text("SELECT caption FROM animal_album_current")).scalar_one()
                == "Updated\ncaption"
            )
        # Other embedded controls remain invalid and cannot replace accepted content.
        for invalid in ("lone\rcarriage return", "embedded\x00control"):
            response = post_form(
                client,
                "/sharing",
                data={"title": "Collection", "slug": "collection", "description": invalid},
            )
            assert response.status_code == 422
            assert "unsupported control" in response.text
        with client.app.state.database_engine.connect() as connection:
            assert connection.execute(
                text("SELECT description FROM sharing_household_current")
            ).scalar_one() == bounded.replace("\r\n", "\n")


def test_private_album_and_publication_are_deliberate_and_revocable(tmp_path):
    with sharing_client(tmp_path) as client:
        _setup(client)
        animal = _register(client, "Secret Keeper Name", "snake", "Private species label")
        assert client.get(animal + "/album").status_code == 200
        media = album_photo(client, animal)
        with client.app.state.database_engine.connect() as c:
            primary = c.execute(
                text("SELECT photo_attachment_version_id FROM animal_current")
            ).scalar_one()
            assert c.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one() == 2
        public_path, collection_path = publish(client, animal, media)
        with TestClient(client.app) as visitor:
            page = visitor.get(public_path)
            assert page.status_code == 200
            assert "Ember" in page.text and "Sunlit scales" in page.text
            for private in [
                animal.rsplit("/", 1)[1],
                str(primary),
                "Secret Keeper Name",
                "Mixed Household",
                "Keeper notes",
                "/attachments/",
                "/animals/",
                "/logout",
            ]:
                assert private not in page.text
            assert "no-store" in page.headers["cache-control"]
            assert not page.headers.get("set-cookie")
            image = re.search(r'src="(/m/[^"]+)"', page.text)[1]
            assert visitor.get(image).status_code == 200
            assert visitor.get(collection_path).status_code == 200
            assert public_path in visitor.get(collection_path).text
            assert (
                post_form(
                    client,
                    animal + "/album/" + media,
                    data={
                        "caption": "Now private",
                        "position": "1",
                    },
                ).status_code
                == 303
            )
            assert visitor.get(image).status_code == 404
            assert visitor.head(image).status_code == 404
            assert "Sunlit scales" not in visitor.get(public_path).text
        with client.app.state.database_engine.connect() as c:
            assert (
                c.execute(
                    text("SELECT photo_attachment_version_id FROM animal_current")
                ).scalar_one()
                == primary
            )


def test_disabled_delivery_still_allows_authenticated_preview(tmp_path):
    with sharing_client(tmp_path, enabled=False) as client:
        _setup(client)
        animal = _register(client, "Private Name", "snake", "Private species")
        media = album_photo(client, animal)
        public_path, collection_path = publish(client, animal, media)
        for path in [public_path, collection_path]:
            assert client.get(path).status_code == 404
        preview = client.get(animal + "/sharing/preview")
        assert preview.status_code == 200 and "Private preview" in preview.text
        assert "Ember" in preview.text
        with TestClient(client.app) as anonymous:
            assert (
                anonymous.get(animal + "/sharing/preview", follow_redirects=False).status_code
                == 303
            )


def test_anonymous_csrf_and_oversized_requests_cannot_mutate_album(tmp_path):
    with sharing_client(tmp_path) as client:
        _setup(client)
        animal = _register(client, "Ember", "snake", "Python regius")
        with TestClient(client.app) as anonymous:
            assert anonymous.get(animal + "/album", follow_redirects=False).status_code == 303
            assert (
                anonymous.post(animal + "/album/upload", follow_redirects=False).status_code == 303
            )
        assert (
            client.post(
                animal + "/album/upload",
                data={"caption": "No CSRF"},
                files={"photo": ("x.png", PHOTO, "image/png")},
            ).status_code
            == 403
        )

        assert (
            client.post(
                animal + "/album/upload",
                headers={
                    "content-length": str(22 * 1024 * 1024),
                    "content-type": "multipart/form-data; boundary=x",
                },
                content=b"",
            ).status_code
            == 413
        )
        assert (
            client.post(
                animal + "/sharing",
                data={"csrf_token": _csrf(client.get(animal + "/sharing").text)},
                headers={"origin": "https://attacker.invalid"},
            ).status_code
            == 403
        )


def test_every_owner_media_operation_rejects_cross_household_and_read_only_roles(tmp_path):
    from tests.browser.test_account_registration import _register as register_account

    with sharing_client(tmp_path) as owner:
        _setup(owner)
        animal = _register(owner, "Owner Secret", "snake", "Private species")
        media = album_photo(owner, animal)
        with TestClient(owner.app) as other:
            register_account(other, email="other@example.test")
            other_animal = _register(other, "Other Animal", "snake", "Other species")
            csrf = _csrf(other.get("/more").text)
            for suffix in [
                "/album",
                "/sharing",
                "/sharing/preview",
                f"/album/{media}",
                f"/album/{media}/photo",
            ]:
                response = other.get(animal + suffix)
                assert response.status_code == 404
                assert "Owner Secret" not in response.text
            with owner.app.state.database_engine.connect() as c:
                events = c.execute(text("SELECT count(*) FROM domain_events")).scalar_one()
                versions = c.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one()
            for suffix, fields in [
                ("/sharing", {"title": "Stolen", "slug": "stolen", "is_public": "true"}),
                (f"/album/{media}", {"caption": "Stolen", "position": "1", "is_public": "true"}),
                (f"/album/{media}/remove", {}),
            ]:
                denied = other.post(
                    animal + suffix, data={"csrf_token": csrf, "idempotency_key": suffix, **fields}
                )
                assert denied.status_code == 404, denied.text
            denied = other.post(
                animal + "/album/upload",
                data={"csrf_token": csrf, "idempotency_key": "foreign-upload"},
                files={"photo": ("x.png", PHOTO, "image/png")},
            )
            assert denied.status_code == 404
            assert other.get(other_animal + f"/album/{media}/photo").status_code == 404
            with owner.app.state.database_engine.connect() as c:
                assert c.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == events
                assert (
                    c.execute(text("SELECT count(*) FROM attachment_versions")).scalar_one()
                    == versions
                )
        with owner.app.state.database_engine.begin() as c:
            c.execute(
                text(
                    "UPDATE authorization_memberships SET role='viewer' "
                    "WHERE user_id=(SELECT user_id FROM users "
                    "WHERE email_normalized='owner@example.com')"
                )
            )
        assert owner.get(animal + "/album").status_code == 200
        for path in [
            "/sharing",
            animal + "/sharing",
            animal + "/album/upload",
            animal + f"/album/{media}",
            animal + f"/album/{media}/remove",
        ]:
            assert owner.post(path, data={}, follow_redirects=False).status_code == 403


def test_household_animal_removal_and_archive_revoke_public_access(tmp_path):
    with sharing_client(tmp_path) as owner:
        _setup(owner)
        animal = _register(owner, "Private Ember", "snake", "Private species")
        media = album_photo(owner, animal)
        public_path, collection_path = publish(owner, animal, media)
        with TestClient(owner.app) as visitor:
            public_photo = re.search(r'src="(/m/[^\"]+)"', visitor.get(public_path).text)[1]
            assert (
                post_form(
                    owner,
                    "/sharing",
                    data={
                        "title": "Forest collection",
                        "slug": collection_path.split("/")[-1],
                        "description": "Public introduction",
                    },
                ).status_code
                == 303
            )
            for path in [public_path, collection_path, public_photo]:
                assert visitor.get(path).status_code == 404
            assert (
                post_form(
                    owner,
                    "/sharing",
                    data={
                        "title": "Forest collection",
                        "slug": collection_path.split("/")[-1],
                        "description": "Public introduction",
                        "enabled": "true",
                    },
                ).status_code
                == 303
            )
            assert visitor.get(public_path).status_code == 200
            assert (
                post_form(
                    owner,
                    animal + "/sharing",
                    data={
                        "title": "Ember",
                        "slug": public_path.split("/")[-1],
                    },
                ).status_code
                == 303
            )
            assert visitor.get(public_path).status_code == 404
            assert visitor.get(public_photo).status_code == 404
            empty = visitor.get(collection_path)
            assert empty.status_code == 200 and "No Animals shared yet" in empty.text
            assert "Private Ember" not in empty.text
            publish(owner, animal, media)
            public_path = re.search(
                r'data-public-url="([^\"]+)"', owner.get(animal + "/sharing").text
            )[1]
            public_photo = re.search(r'src="(/m/[^\"]+)"', visitor.get(public_path).text)[1]
            edit = owner.get(animal + f"/album/{media}")
            removed = owner.post(
                animal + f"/album/{media}/remove",
                data={
                    "csrf_token": _csrf(edit.text),
                    "idempotency_key": "remove-public-photo",
                },
                follow_redirects=False,
            )
            assert removed.status_code == 303
            assert visitor.get(public_photo).status_code == 404
            retained_media = album_photo(owner, animal)
            status_form = owner.get(animal + "/status")
            assert (
                owner.post(
                    animal + "/status",
                    data={
                        "csrf_token": _csrf(status_form.text),
                        "idempotency_key": "archive-public-animal",
                        "status": "archived",
                        "notes": "Fictional archive check",
                    },
                    follow_redirects=False,
                ).status_code
                == 303
            )
            assert visitor.get(public_path).status_code == 404
            for path in [
                animal + "/album",
                animal + f"/album/{retained_media}",
                animal + "/sharing",
                animal + "/sharing/preview",
            ]:
                archived = owner.get(path)
                assert archived.status_code == 200
                assert 'name="is_public"' not in archived.text
                assert 'type="file"' not in archived.text
                assert "Save photo choices" not in archived.text
            assert owner.get(animal + f"/album/{retained_media}/photo").status_code == 200
            archived_form = owner.get(animal + "/sharing")
            assert "This Animal is archived" in archived_form.text
            denied = owner.post(
                animal + "/sharing",
                data={
                    "csrf_token": _csrf(archived_form.text),
                    "idempotency_key": "archived-publication-denied",
                    "title": "Must remain private",
                    "slug": "archived",
                    "is_public": "true",
                },
            )
            assert denied.status_code == 422
            assert visitor.get(public_path).status_code == 404


def test_public_fields_escape_html_and_upload_validation_preserves_form(tmp_path):
    with sharing_client(tmp_path) as owner:
        _setup(owner)
        animal = _register(owner, "Private", "snake", "Private species")
        rejected = post_form(
            owner,
            animal + "/album/upload",
            data={"caption": "Keep my draft"},
            files={"photo": ("active.svg", b'<svg onload="alert(1)"/>', "image/svg+xml")},
        )
        assert rejected.status_code == 422 and "Keep my draft" in rejected.text
        assert 'role="alert"' in rejected.text
        media = album_photo(owner, animal)
        public_path, _ = publish(owner, animal, media)
        assert (
            post_form(
                owner,
                animal + "/sharing",
                data={
                    "title": "<script>alert(1)</script>",
                    "species": "<b>Species</b>",
                    "description": '<img src=x onerror="alert(1)">',
                    "slug": public_path.split("/")[-1],
                    "is_public": "true",
                },
            ).status_code
            == 303
        )
        with TestClient(owner.app) as visitor:
            page = visitor.get(public_path)
            assert page.status_code == 200
            assert "<script>" not in page.text and "<img src=x" not in page.text
            assert "&lt;script&gt;" in page.text
