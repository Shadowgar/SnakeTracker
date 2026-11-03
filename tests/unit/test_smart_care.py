"""Reviewed source positions must not become an implicit scheduling decision."""

from pathlib import Path

import pytest

from snaketracker.application.smart_care import feeding_options
from snaketracker.operations.import_care_guides import load_bundle

ROOT = Path(__file__).parents[2]


def test_conflicting_text_positions_remain_visible_without_a_default():
    guide = load_bundle(ROOT / "reference/care-guides/reviewed-amphibians-v1.json").guides[0]
    options = feeding_options(
        guide, animal_group="amphibian", scientific_name=guide.scientific_name
    )
    adults = [option for option in options if option.claim.life_stage == "Adult"]
    assert len(adults) == 2
    assert all(option.support == "Sources differ" for option in adults)
    assert {option.interval_days for option in adults} == {2, None}
    assert any(option.claim.value_text == "2\u20133 times weekly." for option in adults)
    juveniles = [option for option in options if option.claim.life_stage == "Juvenile"]
    assert all(option.support == "Corroborated" for option in juveniles)


def test_ranges_and_unknown_species_require_keeper_entry():
    guide = load_bundle(ROOT / "reference/care-guides/reviewed-boa-constrictor-v1.json").guides[0]
    options = feeding_options(guide, animal_group="snake", scientific_name="Boa constrictor")
    assert len(options) == 2
    assert all(option.interval_days is None for option in options)
    assert options[0].claim.minimum == 10
    assert feeding_options(guide, animal_group="snake", scientific_name="Boa imperator") == ()
    assert feeding_options(guide, animal_group="amphibian", scientific_name="Boa constrictor") == ()
    assert feeding_options(None, animal_group="snake", scientific_name=None) == ()


@pytest.mark.parametrize("value", [0, 0.5, 1.5])
def test_non_whole_day_values_are_never_rounded(value):
    guide = load_bundle(ROOT / "reference/care-guides/reviewed-amphibians-v1.json").guides[0]
    claim = next(
        c for c in guide.claims if c.value_number == 1 and c.fact_key == "feeding_interval"
    )
    claim = claim.model_copy(update={"value_number": value})
    guide = guide.model_copy(update={"claims": (claim,)})
    options = feeding_options(
        guide, animal_group="amphibian", scientific_name=guide.scientific_name
    )
    assert len(options) == 1
    assert options[0].interval_days is None


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "Frogs"},
        {"context": "Wild feeding"},
        {"life_stage": None},
        {"fact_key": "post_meal_handling"},
    ],
)
def test_insufficient_applicability_is_manual_only(changes):
    guide = load_bundle(ROOT / "reference/care-guides/reviewed-amphibians-v1.json").guides[0]
    claim = next(c for c in guide.claims if c.fact_key == "feeding_interval")
    guide = guide.model_copy(update={"claims": (claim.model_copy(update=changes),)})
    assert (
        feeding_options(guide, animal_group="amphibian", scientific_name=guide.scientific_name)
        == ()
    )
