"""Invalid reference metadata never grants the initial Animal workflow a species link."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from snaketracker.application.species_directory import (
    DirectoryValidationError,
    LinkAnimalTaxonCommand,
    ProviderUnavailableError,
    SpeciesDirectoryService,
    TaxonRecord,
)


@pytest.mark.parametrize(
    "group,rank,status,selection",
    [
        ("amphibian", "class", "accepted", "selected"),
        ("amphibian", "order", "accepted", "selected"),
        ("amphibian", "species", "inactive", "selected"),
        ("amphibian", "species", "accepted", "unknown_order"),
        ("", "species", "accepted", "selected"),
    ],
)
def test_reference_only_or_unqualified_taxa_cannot_be_linked_as_frog_species(
    group, rank, status, selection
):
    now = datetime.now(UTC)
    identifier = uuid4()
    record = TaxonRecord(
        taxon_id=identifier,
        supported_group=group,
        accepted_scientific_name="Rana temporaria",
        preferred_common_name="European Common Frog",
        authorship=None,
        alternative_common_names=(),
        synonyms=(),
        taxonomic_status=status,
        rank=rank,
        kingdom="Animalia",
        phylum_division="Chordata",
        class_name="Amphibia",
        order_name="Anura",
        family="Ranidae",
        genus="Rana",
        species="Rana temporaria",
        infra_rank=None,
        provider="inaturalist",
        provider_id="25591",
        source_url="https://www.inaturalist.org/taxa/25591",
        retrieved_at=now,
        refreshed_at=now,
        stale=False,
        taxonomy_selection_state=selection,
    )
    repository = Mock()
    repository.get.return_value = record
    provider = Mock(provider_name="inaturalist")
    provider.detail.side_effect = ProviderUnavailableError("Fixture provider offline")
    projection = Mock()
    projection.profile_for.return_value = SimpleNamespace(animal_type="amphibian", stream_version=1)
    store = Mock()
    directory = SpeciesDirectoryService(
        repository, provider, event_store=store, animal_projection=projection
    )
    with pytest.raises(DirectoryValidationError, match=r"qualified Amphibian|does not match"):
        directory.link_animal(
            LinkAnimalTaxonCommand(
                household_id=uuid4(),
                actor_user_id=uuid4(),
                animal_id=uuid4(),
                taxon_id=identifier,
                correlation_id=uuid4(),
                idempotency_key="invalid-amphibian-link",
            )
        )
    store.append_many.assert_not_called()
