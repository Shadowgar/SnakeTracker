from __future__ import annotations

import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from snaketracker.application.care_guides import GuideBundle
from snaketracker.bootstrap.application import build_application
from snaketracker.bootstrap.configuration import Environment, Settings
from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.care_guides import (
    CareGuideImportError,
    SQLAlchemyCareGuideRepository,
)
from snaketracker.operations.import_care_guides import MAX_BUNDLE_BYTES, load_bundle, main

ROOT = Path(__file__).parents[2]


def _database(tmp_path: Path) -> tuple[Path, dict[str, UUID]]:
    path = tmp_path / "guides.sqlite3"
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
    command.upgrade(config, "head")
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    engine = create_sqlite_engine(path, require_local_storage=False)
    ids: dict[str, UUID] = {}
    with engine.begin() as connection:
        for guide in bundle.guides:
            taxon_id = uuid4()
            ids[guide.scientific_name] = taxon_id
            connection.execute(
                text(
                    "INSERT INTO taxa (taxon_id,supported_group,accepted_scientific_name,"
                    "taxonomic_status,created_at,refreshed_at) "
                    "VALUES (:id,:group,:name,'accepted',:at,:at)"
                ),
                {
                    "id": str(taxon_id),
                    "group": guide.biological_group.value,
                    "name": guide.scientific_name,
                    "at": datetime.now(UTC).isoformat(),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO taxon_provider_mappings "
                    "(taxon_id,provider,provider_id,source_url,retrieved_at,refreshed_at) "
                    "VALUES (:id,'fixture',:provider_id,:url,:at,:at)"
                ),
                {
                    "id": str(taxon_id),
                    "provider_id": guide.scientific_name,
                    "url": "https://example.test/taxon",
                    "at": datetime.now(UTC).isoformat(),
                },
            )
    engine.dispose()
    return path, ids


def _bundle() -> GuideBundle:
    return GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )


def test_operator_import_command_requires_explicit_migrated_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_path = ROOT / "reference/care-guides/reviewed-v1.json"
    with pytest.raises(ValueError, match="missing"):
        load_bundle(tmp_path / "missing.json")
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (MAX_BUNDLE_BYTES + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        load_bundle(oversized)

    monkeypatch.setattr(sys, "argv", ["import_care_guides", str(bundle_path)])
    main()
    assert "Validated 5 reviewed guides and 30 sourced claims" in capsys.readouterr().out
    for database in (None, "relative.sqlite3", str(tmp_path / "missing.sqlite3")):
        arguments = ["import_care_guides", str(bundle_path), "--apply"]
        if database is not None:
            arguments.extend(("--database", database))
        monkeypatch.setattr(sys, "argv", arguments)
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2

    path, _ = _database(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["import_care_guides", str(bundle_path), "--apply", "--database", str(path)]
    )
    main()
    assert "Imported 5 guide versions" in capsys.readouterr().out
    main()
    assert "5 identical versions already present" in capsys.readouterr().out


def test_atomic_idempotent_import_and_immutable_versions(tmp_path: Path) -> None:
    path, ids = _database(tmp_path)
    engine = create_sqlite_engine(path, require_local_storage=False)
    repo = SQLAlchemyCareGuideRepository(engine)
    bundle = _bundle()
    try:
        assert repo.import_bundle(bundle) == (5, 0)
        assert repo.import_bundle(bundle) == (0, 5)
        assert repo.available(ids["Python regius"])
        assert repo.current(ids["Python regius"]) == bundle.guides[0]
        assert repo.versions(ids["Python regius"]) == (1,)
        assert repo.version(ids["Python regius"], 7) is None
        with engine.connect() as connection:
            source_count = connection.execute(text("SELECT count(*) FROM care_guide_sources"))
            claim_count = connection.execute(text("SELECT count(*) FROM care_guide_claims"))
            assert source_count.scalar_one() == 8
            assert claim_count.scalar_one() == 30
            assert connection.execute(text("SELECT count(*) FROM domain_events")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
        snake = bundle.guides[0]
        changed = snake.model_copy(
            update={
                "version": 2,
                "created_at": snake.reviewed_at + timedelta(days=1),
                "reviewed_at": snake.reviewed_at + timedelta(days=1),
            }
        )
        assert repo.import_bundle(GuideBundle(format_version=1, guides=(changed,))) == (1, 0)
        assert repo.versions(ids["Python regius"]) == (2, 1)
        assert repo.version(ids["Python regius"], 1) == snake
        assert repo.current(ids["Python regius"]) == changed
        with engine.begin() as connection, pytest.raises(Exception, match="immutable"):
            connection.execute(
                text("UPDATE care_guide_claims SET label='Changed' WHERE taxon_id=:id"),
                {"id": str(ids["Python regius"])},
            )
    finally:
        engine.dispose()


def test_unknown_taxon_and_changed_version_roll_back_entire_bundle(tmp_path: Path) -> None:
    path, ids = _database(tmp_path)
    engine = create_sqlite_engine(path, require_local_storage=False)
    repo = SQLAlchemyCareGuideRepository(engine)
    bundle = _bundle()
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM taxa WHERE taxon_id=:id"),
                {"id": str(ids["Pandinus imperator"])},
            )
        with pytest.raises(CareGuideImportError, match="exactly one cached"):
            repo.import_bundle(bundle)
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM care_guide_versions")).scalar_one()
                == 0
            )
        first_only = GuideBundle(format_version=1, guides=(bundle.guides[0],))
        assert repo.import_bundle(first_only) == (1, 0)
        altered = bundle.guides[0].model_copy(update={"scientific_name": "Python regius "})
        with pytest.raises(CareGuideImportError):
            repo.import_bundle(GuideBundle(format_version=1, guides=(altered,)))
        changed = bundle.guides[0].model_copy(update={"claims": bundle.guides[0].claims[:-1]})
        with pytest.raises(CareGuideImportError, match="changed"):
            repo.import_bundle(GuideBundle(format_version=1, guides=(changed,)))
        assert repo.versions(ids["Python regius"]) == (1,)
    finally:
        engine.dispose()


def test_authenticated_offline_guide_escapes_source_text_and_keeps_csp(tmp_path: Path) -> None:
    path, ids = _database(tmp_path)
    engine = create_sqlite_engine(path, require_local_storage=False)
    guide = _bundle().guides[0]
    claim = guide.claims[0].model_copy(update={"label": "<script>alert(1)</script>"})
    source = guide.sources[0].model_copy(update={"title": "<img src=x onerror=alert(1)>"})
    guide = guide.model_copy(
        update={"claims": (claim, *guide.claims[1:]), "sources": (source, *guide.sources[1:])}
    )
    SQLAlchemyCareGuideRepository(engine).import_bundle(
        GuideBundle(format_version=1, guides=(guide,))
    )
    engine.dispose()
    app = build_application(
        Settings(
            environment=Environment.TEST,
            database_path=path,
            runtime_secret=SecretStr("care-guide-runtime-secret-at-least-32-bytes"),
            session_cookie_secure=False,
        )
    )
    with TestClient(app) as client:
        unauthenticated = client.get(
            f"/directory/{ids['Python regius']}/care-guide", follow_redirects=False
        )
        assert unauthenticated.status_code == 303
        setup = client.get("/setup")
        match = re.search(r'name="csrf_token" value="([^"]+)"', setup.text)
        assert match is not None
        created = client.post(
            "/setup",
            data={
                "csrf_token": match.group(1),
                "household_name": "Guide Test",
                "timezone": "UTC",
                "display_name": "Keeper",
                "email": "guide@example.test",
                "password": "correct horse battery staple",
                "password_confirmation": "correct horse battery staple",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        with create_sqlite_engine(path, require_local_storage=False).connect() as connection:
            event_rows = connection.execute(text("SELECT count(*) FROM domain_events"))
            event_count = event_rows.scalar_one()
        response = client.get(f"/directory/{ids['Python regius']}/care-guide")
        assert response.status_code == 200
        assert "Reference guidance" in response.text
        assert "&lt;script&gt;" in response.text
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;img src=x onerror=alert(1)&gt;" in response.text
        assert 'rel="noopener noreferrer"' in response.text
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert "30\u201332°C" in response.text
        assert 'class="care-guide-page"' in response.text
        assert 'class="guide-glance-item"' in response.text
        assert f'href="#fact-{claim.claim_id}"' in response.text
        assert 'class="guide-state guide-state-single"' in response.text
        assert "<summary>Sources and review dates</summary>" in response.text
        assert 'class="guide-source-card"' in response.text
        assert (
            "No reviewed guidance available"
            in client.get(f"/directory/{ids['Monstera deliciosa']}/care-guide").text
        )
        assert client.get(f"/directory/{ids['Python regius']}").status_code == 200
    with create_sqlite_engine(path, require_local_storage=False).connect() as connection:
        event_rows = connection.execute(text("SELECT count(*) FROM domain_events"))
        assert event_rows.scalar_one() == event_count
