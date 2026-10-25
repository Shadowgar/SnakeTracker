"""Actual provider parsers must support the autocomplete-to-link sequence locally."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from snaketracker.application.species_directory import (
    DirectoryValidationError,
    LinkAnimalTaxonCommand,
    SpeciesDirectoryService,
)
from snaketracker.infrastructure.animals.projections import SQLAlchemyAnimalCurrentProjection
from snaketracker.infrastructure.taxonomy import inaturalist
from snaketracker.infrastructure.taxonomy.inaturalist import INaturalistTaxonomyProvider
from snaketracker.infrastructure.taxonomy.repository import SQLAlchemyTaxonRepository
from tests.integration.test_multispecies_animals import _services
from tests.integration.test_x4_registration import frog_command
from tests.unit.infrastructure.test_inaturalist_taxonomy import Response


@pytest.mark.parametrize("change", [None, "rename", "rank"])
def test_actual_autocomplete_detail_link_preserves_compatible_facts_and_rejects_conflicts(
    tmp_path, monkeypatch, change
):
    animals, store, bootstrap, engine = _services(tmp_path)
    summary = {
        "id": 25591,
        "name": "Rana temporaria",
        "rank": "species",
        "preferred_common_name": "European Common Frog",
        "matched_term": "Common frog",
        "ancestor_ids": [1, 20978, 20979, 25474],
    }
    detail = {key: value for key, value in summary.items() if key != "matched_term"} | {
        "parent_id": 25474,
        "ancestors": [
            {"id": 1, "rank": "kingdom", "name": "Animalia"},
            {"id": 20978, "rank": "class", "name": "Amphibia"},
            {"id": 20979, "rank": "order", "name": "Anura"},
            {"id": 25474, "rank": "genus", "name": "Rana"},
        ],
    }
    if change == "rename":
        detail["name"] = "Rana changed"
    elif change == "rank":
        detail["rank"] = "subspecies"
    requests = []

    def transport(request, *, timeout):
        requests.append(request.full_url)
        raw = summary if "/autocomplete?" in request.full_url else detail
        return Response(json.dumps({"results": [raw]}).encode())

    monkeypatch.setattr(inaturalist, "urlopen", transport)
    provider = INaturalistTaxonomyProvider()
    repository = SQLAlchemyTaxonRepository(engine)
    directory = SpeciesDirectoryService(
        repository,
        provider,
        event_store=store,
        animal_projection=SQLAlchemyAnimalCurrentProjection(engine),
    )
    try:
        frog = animals.register(frog_command(bootstrap))
        found = directory.search("common frog", "amphibian").records[0]
        assert found.taxonomy_selection_state == "selected"
        assert found.class_name is None
        command = LinkAnimalTaxonCommand(
            bootstrap.household_id,
            bootstrap.user_id,
            frog.animal_id,
            found.taxon_id,
            uuid4(),
            "x4-live-link",
        )
        if change:
            with pytest.raises(DirectoryValidationError, match="qualified Amphibian"):
                directory.link_animal(command)
            assert directory.get(found.taxon_id).taxonomy_selection_state == "unknown_order"
            assert len(store.load_stream(frog.stream_key)) == 1
            return
        linked = directory.link_animal(command)
        assert linked.taxon.taxon_id == found.taxon_id
        assert linked.taxon.class_name == "Amphibia"
        assert linked.taxon.order_name == "Anura"
        assert "Common frog" in linked.taxon.synonyms
        assert linked.taxon.taxonomy_selection_state == "selected"
        events = store.load_stream(frog.stream_key)
        assert events[-1].event_type == "animal.taxon_linked"
        assert events[-1].schema_version == 2
        # A later partial response cannot erase locally retained detail or aliases.
        repository.upsert(
            provider.search("common frog", "amphibian", limit=1)[0],
            observed_at=linked.taxon.refreshed_at,
        )
        retained = directory.get(found.taxon_id)
        assert retained.class_name == "Amphibia" and retained.order_name == "Anura"
        assert retained.taxonomy_selection_state == "selected"
        assert "Common frog" in retained.synonyms
        with engine.connect() as connection:
            observations = [
                json.loads(row[0])["payload"]
                for row in connection.exec_driver_sql(
                    "SELECT details FROM taxonomy_changes WHERE kind='live_observation'"
                )
            ]
            assert any(row["class_name"] is None for row in observations)
            assert any(row["class_name"] == "Amphibia" for row in observations)
        # Ordinary local reference/profile reads remain usable with transport disabled.
        before = len(requests)
        monkeypatch.setattr(
            inaturalist, "urlopen", lambda *a, **kw: pytest.fail("GET used provider")
        )
        assert directory.linked_for(bootstrap.household_id, frog.animal_id).taxon == retained
        assert animals.profile_for(bootstrap.household_id, frog.animal_id) is not None
        assert len(requests) == before
    finally:
        engine.dispose()
