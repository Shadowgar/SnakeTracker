"""X4 visual policies: distinct group art and honest future-profile placeholders."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from snaketracker.presentation import animal_visuals

STATIC = Path(animal_visuals.__file__).parent / "static"


def _animal(animal_type: str, version: int = 1, photo: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        animal_id=uuid4(),
        name="Fern",
        animal_type=animal_type,
        capability_profile_version=version,
        type_label=animal_type.title(),
        species="Manually entered species",
        breeder_source="",
        photo_attachment_version_id=photo,
    )


def test_amphibian_fallback_is_a_distinct_decodable_group_asset() -> None:
    visual = animal_visuals.AnimalVisualResolver(None).resolve(uuid4(), _animal("amphibian"))

    assert visual.kind == "group_fallback"
    assert visual.url.split("?")[0] == "/static/animal-fallbacks/amphibian.webp"
    assert visual.alt == "Amphibian group illustration for Fern"
    path = STATIC / "animal-fallbacks" / "amphibian.webp"
    with Image.open(path) as artwork:
        artwork.load()
        assert artwork.size == (1200, 800)
    assert path.read_bytes() not in {
        (STATIC / "animal-fallbacks" / f"{group}.webp").read_bytes()
        for group in ("snake", "spider", "lizard", "scorpion")
    }


@pytest.mark.parametrize("animal_type", ["snake", "future_group"])
def test_unknown_profile_uses_neutral_visual_across_resolver_and_admin(
    animal_type: str,
) -> None:
    animal = _animal(animal_type, version=99)
    visual = animal_visuals.AnimalVisualResolver(None).resolve(uuid4(), animal)

    assert visual.kind == "animal_fallback"
    assert visual.url.split("?")[0] == "/static/animal-fallbacks/unknown.svg"
    assert visual.alt == "Animal illustration for Fern"
    admin_visual = animal_visuals.profile_fallback_visual(animal_type, 99)
    assert admin_visual.kind == visual.kind
    assert admin_visual.url == visual.url
    assert admin_visual.alt == "Animal illustration"


def test_amphibian_personal_photo_keeps_priority_over_group_art() -> None:
    photo_id = uuid4()
    visual = animal_visuals.AnimalVisualResolver(None).resolve(
        uuid4(), _animal("amphibian", photo=photo_id)
    )

    assert visual.kind == "personal_photo"
    assert visual.url == f"/attachments/{photo_id}"


@pytest.mark.parametrize("animal_type,version", [("snake", 99), ("future_group", 1)])
def test_rendered_list_profile_and_admin_share_neutral_unknown_fallback(
    animal_type: str, version: int
) -> None:
    from jinja2 import Environment, FileSystemLoader

    animal = _animal(animal_type, version)
    animal.household_id = uuid4()
    visual = animal_visuals.AnimalVisualResolver(None).resolve(uuid4(), animal)
    templates = Environment(loader=FileSystemLoader(STATIC.parent / "templates"), autoescape=True)
    templates.globals["profile_fallback_visual"] = animal_visuals.profile_fallback_visual
    templates.globals["admin_short_id"] = str
    common = {
        "animal": animal,
        "animal_visual": visual,
        "request": SimpleNamespace(url=SimpleNamespace(path="/admin/animals/example")),
        "operator": SimpleNamespace(display_name="Operator"),
        "record": animal,
        "events": (),
        "financial": SimpleNamespace(),
    }
    rendered = [
        templates.get_template("animal_list.html").render(
            **common,
            animal_rows=[{"animal": animal, "visual": visual}],
            selected_kind="all",
        ),
        templates.get_template("animal_profile_header.html").render(**common),
        templates.get_template("admin.html").render(**common, kind="animal"),
        templates.get_template("admin.html").render(
            **common,
            kind="household",
            bundle=SimpleNamespace(animals=(animal,), members=(), enclosures=(), inventory=()),
        ),
    ]

    for html in rendered:
        assert "/static/animal-fallbacks/unknown.svg?" in html
        assert 'alt="Animal illustration' in html
        assert "group illustration" not in html
        assert "reference illustration" not in html.lower()
    assert "Animal illustration · add your animal" in rendered[1]
