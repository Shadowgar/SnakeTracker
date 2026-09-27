from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from snaketracker.application.care_guides import (
    GuideBundle,
    GuideClaim,
    format_claim_value,
    grouped_claims,
)

ROOT = Path(__file__).parents[3]


def test_reviewed_bundle_has_five_groups_and_every_claim_has_provenance() -> None:
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    assert {guide.biological_group for guide in bundle.guides} == {
        "snake",
        "lizard",
        "spider",
        "scorpion",
        "plant",
    }
    for guide in bundle.guides:
        sources = {source.source_id for source in guide.sources}
        assert all(claim.source_id in sources for claim in guide.claims)
        assert grouped_claims(guide)


def test_range_units_scope_and_source_validation() -> None:
    base = {
        "claim_id": "claim-one",
        "source_id": "source-one",
        "section": "temperature_humidity",
        "fact_key": "ambient_humidity",
        "label": "Humidity",
        "minimum": 50,
        "maximum": 60,
        "unit": "percent",
    }
    claim = GuideClaim.model_validate(base)
    assert format_claim_value(claim) == "50\u201360%"
    for replacement in (
        {"minimum": 75, "maximum": 65},
        {"unit": "mystery"},
        {"minimum": -1},
        {"maximum": 101},
        {"value_text": "unstructured duplicate"},
    ):
        with pytest.raises(ValidationError):
            GuideClaim.model_validate({**base, **replacement})
    with pytest.raises(ValidationError, match="scope"):
        GuideClaim.model_validate({**base, "fact_key": "toxicity_cats_dogs"})
    temperature = GuideClaim.model_validate({**base, "minimum": 30, "maximum": 32, "unit": "c"})
    assert format_claim_value(temperature) == "30\u201332°C (86\u201389.6°F)"


def test_reviewed_bundle_rejects_malformed_source_url_and_unknown_source() -> None:
    path = ROOT / "reference/care-guides/reviewed-v1.json"
    data = json.loads(path.read_text())
    data["guides"][0]["sources"][0]["url"] = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        GuideBundle.model_validate(data)
    data = json.loads(path.read_text())
    data["guides"][0]["claims"][0]["source_id"] = "missing-source"
    with pytest.raises(ValidationError, match="unknown source"):
        GuideBundle.model_validate(data)


def test_reviewed_bundle_rejects_invalid_review_history_and_duplicate_evidence() -> None:
    """A reviewed update cannot conceal stale timestamps or duplicate source positions."""
    original = json.loads((ROOT / "reference/care-guides/reviewed-v1.json").read_text())
    cases = (
        (
            "source review must be after retrieval",
            lambda data: data["guides"][0]["sources"][0].update(
                reviewed_at="2020-01-01T00:00:00+00:00"
            ),
        ),
        (
            "source timestamps must include a timezone",
            lambda data: data["guides"][0]["sources"][0].update(retrieved_at="2026-09-27T00:00:00"),
        ),
        (
            "guide timestamps must include a timezone",
            lambda data: data["guides"][0].update(created_at="2026-09-27T00:00:00"),
        ),
        (
            "guide review precedes creation",
            lambda data: data["guides"][0].update(created_at="2027-01-01T00:00:00+00:00"),
        ),
        (
            "duplicate source ID",
            lambda data: data["guides"][0]["sources"].append(
                copy.deepcopy(data["guides"][0]["sources"][0])
            ),
        ),
        (
            "duplicate claim ID",
            lambda data: data["guides"][0]["claims"].append(
                copy.deepcopy(data["guides"][0]["claims"][0])
            ),
        ),
        (
            "source review follows guide review",
            lambda data: data["guides"][0]["sources"][0].update(
                reviewed_at="2027-01-01T00:00:00+00:00"
            ),
        ),
        (
            "duplicate positions",
            lambda data: data["guides"][0]["claims"].append(
                {**data["guides"][0]["claims"][0], "claim_id": "duplicate-position"}
            ),
        ),
        (
            "plant claims cannot",
            lambda data: data["guides"][0]["claims"][0].update(fact_key="plant_water"),
        ),
        (
            "duplicate guide version",
            lambda data: data["guides"].append(copy.deepcopy(data["guides"][0])),
        ),
    )
    for expected, mutate in cases:
        data = copy.deepcopy(original)
        mutate(data)
        with pytest.raises(ValidationError, match=expected):
            GuideBundle.model_validate(data)


def test_claim_requires_complete_range_and_text_without_numeric_unit() -> None:
    original = GuideClaim.model_validate(
        {
            "claim_id": "test-range",
            "source_id": "test-source",
            "section": "temperature_humidity",
            "fact_key": "humidity",
            "label": "Humidity",
            "minimum": 50,
            "maximum": 60,
            "unit": "percent",
        }
    )
    with pytest.raises(ValidationError, match="range requires both bounds"):
        GuideClaim.model_validate(original.model_dump(exclude={"maximum"}))
    with pytest.raises(ValidationError, match="text claim cannot have a numeric unit"):
        GuideClaim.model_validate(
            {**original.model_dump(), "minimum": None, "maximum": None, "value_text": "Moist"}
        )


def test_conflicting_claims_keep_separate_source_positions() -> None:
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    snake = bundle.guides[0]
    original = next(claim for claim in snake.claims if claim.fact_key == "ambient_humidity")
    disagreeing = original.model_copy(
        update={
            "claim_id": "test-disagreement",
            "source_id": "rvc-royal-python",
            "minimum": 65,
            "maximum": 75,
        }
    )
    guide = snake.model_copy(update={"claims": (*snake.claims, disagreeing)})
    sections = grouped_claims(guide)
    facts = [fact for _, items in sections for fact in items]
    humidity = next(item for item in facts if item[0] == "Cool-end humidity")
    assert humidity[2] == "Sources differ"
    assert [format_claim_value(claim) for claim in humidity[1]] == ["50\u201360%", "65\u201375%"]


def test_reviewed_lizard_guide_displays_real_disagreement_and_corroboration() -> None:
    bundle = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    )
    lizard = next(guide for guide in bundle.guides if guide.biological_group == "lizard")
    facts = [fact for _, section in grouped_claims(lizard) for fact in section]
    basking = next(fact for fact in facts if fact[0] == "Basking area")
    assert basking[2] == "Sources differ"
    assert [format_claim_value(claim) for claim in basking[1]] == [
        "35\u201340°C (95\u2013104°F)",
        "38\u201342°C (100.4\u2013107.6°F)",
    ]
    uvb = next(fact for fact in facts if fact[0] == "UVB")
    assert uvb[2] == "Corroborated"
