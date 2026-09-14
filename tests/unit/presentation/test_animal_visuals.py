from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from snaketracker.presentation import animal_visuals


def _animal(*, photo: object | None = None, animal_type: str = "snake") -> SimpleNamespace:
    return SimpleNamespace(
        animal_id=uuid4(),
        photo_attachment_version_id=photo,
        name="Atlas",
        animal_type=animal_type,
        type_label=animal_type.title(),
    )


def test_visual_resolver_prioritizes_personal_photo_and_resolves_all() -> None:
    household_id = uuid4()
    photo_id = uuid4()
    with_photo = _animal(photo=photo_id)
    fallback = _animal(animal_type="lizard")
    resolver = animal_visuals.AnimalVisualResolver(None)

    visuals = resolver.resolve_all(household_id, (with_photo, fallback))

    assert visuals[with_photo.animal_id].kind == "personal_photo"
    assert visuals[with_photo.animal_id].url == f"/attachments/{photo_id}"
    assert visuals[fallback.animal_id].kind == "group_fallback"
    assert visuals[fallback.animal_id].url.endswith("/lizard.webp")


def test_visual_resolver_uses_reference_photo_metadata() -> None:
    taxon_id = uuid4()
    taxon = SimpleNamespace(
        taxon_id=taxon_id,
        display_name="Boa Constrictor",
        accepted_scientific_name="Boa constrictor",
    )
    reference = SimpleNamespace(
        kind="photograph",
        creator="Jane Keeper",
        license_code="cc-by-nc",
        license_url="https://creativecommons.org/licenses/by-nc/4.0/",
        source_page_url="https://example.test/photo",
        provider="inaturalist",
    )
    directory = SimpleNamespace(
        linked_for=lambda *_args: SimpleNamespace(taxon=taxon),
        reference_image=lambda *_args: reference,
    )

    visual = animal_visuals.AnimalVisualResolver(directory).resolve(uuid4(), _animal())

    assert visual.kind == "species_photo"
    assert visual.is_species_reference
    assert visual.creator == "Jane Keeper"
    assert visual.license_code == "cc-by-nc"


def test_visual_resolver_uses_species_illustration_then_safe_group_fallback(
    monkeypatch,
) -> None:
    taxon_id = uuid4()
    taxon = SimpleNamespace(
        taxon_id=taxon_id,
        display_name="Boa Constrictor",
        accepted_scientific_name="Boa constrictor",
    )
    directory = SimpleNamespace(
        linked_for=lambda *_args: SimpleNamespace(taxon=taxon),
        reference_image=lambda *_args: None,
    )
    monkeypatch.setattr(
        animal_visuals, "_load_species_illustrations", lambda: {"boa constrictor": "boa.webp"}
    )
    illustrated = animal_visuals.AnimalVisualResolver(directory).resolve(uuid4(), _animal())
    assert illustrated.kind == "species_illustration"
    assert illustrated.url.endswith("/boa.webp")

    unlinked = SimpleNamespace(linked_for=lambda *_args: None)
    unknown = animal_visuals.AnimalVisualResolver(unlinked).resolve(
        uuid4(), _animal(animal_type="unknown")
    )
    assert unknown.kind == "group_fallback"
    assert unknown.url.endswith("/snake.webp")


def test_species_illustration_manifest_rejects_non_mapping(monkeypatch) -> None:
    monkeypatch.setattr(animal_visuals.json, "loads", lambda _raw: [])
    assert animal_visuals._load_species_illustrations() == {}
