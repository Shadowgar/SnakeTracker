"""Partial provider facts may add detail, never silently replace known authority."""

import json
from dataclasses import asdict, replace

import pytest

from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.taxonomy.catalog import FACT_FIELDS, _unordered_live_enrichment


def fact(**changes):
    candidate = replace(
        ProviderTaxon(
            "inaturalist",
            "25591",
            "https://www.inaturalist.org/taxa/25591",
            "amphibian",
            "Rana temporaria",
            rank="species",
        ),
        **changes,
    )
    return {key: value for key, value in asdict(candidate).items() if key in FACT_FIELDS}


def test_unordered_partial_enrichment_is_monotonic_in_either_response_order():
    partial = fact(synonyms=("Common frog",))
    detailed = fact(class_name="Amphibia", order_name="Anura", parent_provider_id="25474")
    for old, new in ((partial, detailed), (detailed, partial)):
        result = json.loads(_unordered_live_enrichment(json.dumps(new), None, old, None))
        assert result["class_name"] == "Amphibia"
        assert result["order_name"] == "Anura"
        assert result["parent_provider_id"] == "25474"
        assert result["synonyms"] == ["Common frog"]


@pytest.mark.parametrize(
    "old,new,old_clock,new_clock",
    [
        (fact(), fact(class_name="Amphibia"), "2026-10-01", None),
        (fact(), fact(class_name="Amphibia"), None, "2026-10-01"),
        (fact(), fact(class_name="Amphibia"), "2026-10-01", "2026-10-01"),
        (fact(provider="fixture"), fact(provider="fixture", class_name="Amphibia"), None, None),
        (fact(), fact(provider_id="different"), None, None),
        (fact(), fact(accepted_scientific_name="Rana changed"), None, None),
        (fact(), fact(supported_group="snake"), None, None),
        (fact(), fact(rank="subspecies"), None, None),
        (fact(), fact(taxonomic_status="inactive"), None, None),
        (fact(), fact(accepted_provider_id="replacement"), None, None),
        (fact(class_name="Amphibia"), fact(class_name="Reptilia"), None, None),
        (fact(parent_provider_id="25474"), fact(parent_provider_id="different"), None, None),
        (fact(synonyms=tuple(f"old-{i}" for i in range(64))), fact(synonyms=("new",)), None, None),
    ],
)
def test_enrichment_does_not_replace_source_ordering_or_contradictory_facts(
    old, new, old_clock, new_clock
):
    assert _unordered_live_enrichment(json.dumps(new), new_clock, old, old_clock) is None
