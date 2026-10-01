from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from snaketracker.presentation import animal_visuals


def _animal(
    *,
    photo: object | None = None,
    animal_type: str = "snake",
    species: str = "Unknown species",
    breeder_source: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        animal_id=uuid4(),
        photo_attachment_version_id=photo,
        name="Atlas",
        animal_type=animal_type,
        type_label=animal_type.title(),
        species=species,
        breeder_source=breeder_source,
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
    assert "/lizard.webp?v=m66-a-phase2-visual-rebuild" in visuals[fallback.animal_id].url


def test_visual_resolver_does_not_mistake_seeded_demo_art_for_keeper_photo() -> None:
    animal = _animal(
        photo=uuid4(),
        species="Python regius",
        breeder_source=animal_visuals.SEEDED_DEMO_SOURCE,
    )

    visual = animal_visuals.AnimalVisualResolver(None).resolve(uuid4(), animal)

    assert visual.kind == "species_photo"
    assert visual.url.startswith("/static/species-references/python-regius.webp")
    assert visual.creator
    assert visual.license_code in {"cc-by", "cc-by-sa", "cc-by-nc"}


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
        cached_reference_image=lambda *_args: reference,
    )

    visual = animal_visuals.AnimalVisualResolver(directory).resolve(uuid4(), _animal())

    assert visual.kind == "species_photo"
    assert visual.is_species_reference
    assert visual.creator == "Jane Keeper"
    assert visual.license_code == "cc-by-nc"


def test_visual_resolver_preserves_cached_reference_illustration_kind() -> None:
    taxon_id = uuid4()
    taxon = SimpleNamespace(
        taxon_id=taxon_id,
        display_name="Unphotographed Species",
        accepted_scientific_name="Example species",
    )
    reference = SimpleNamespace(
        kind="illustration",
        creator="Care Keeper",
        license_code="cc-by",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        source_page_url="https://www.inaturalist.org/taxa/1",
        provider="care_keeper",
    )
    directory = SimpleNamespace(
        linked_for=lambda *_args: SimpleNamespace(taxon=taxon),
        cached_reference_image=lambda *_args: reference,
    )

    visual = animal_visuals.AnimalVisualResolver(directory).resolve(uuid4(), _animal())

    assert visual.kind == "species_illustration"
    assert visual.taxon_id == taxon_id


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
        cached_reference_image=lambda *_args: None,
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
    assert unknown.url == ("/static/animal-fallbacks/snake.webp?v=m66-a-phase2-visual-rebuild")


def test_species_illustration_manifest_rejects_non_mapping(monkeypatch) -> None:
    monkeypatch.setattr(animal_visuals.json, "loads", lambda _raw: [])
    assert animal_visuals._load_species_illustrations() == {}


def test_species_reference_manifest_rejects_non_mapping(monkeypatch) -> None:
    monkeypatch.setattr(animal_visuals.json, "loads", lambda _raw: [])
    assert animal_visuals._load_species_references() == {}


def test_attribution_urls_require_safe_https_origins() -> None:
    hosts = {"creativecommons.org"}

    assert animal_visuals._is_attribution_url("https://creativecommons.org/licenses/by/4.0/", hosts)
    assert not animal_visuals._is_attribution_url(None, hosts)
    assert not animal_visuals._is_attribution_url("x" * 2_049, hosts)
    assert not animal_visuals._is_attribution_url("http://creativecommons.org", hosts)
    assert not animal_visuals._is_attribution_url("https://example.org", hosts)
    assert not animal_visuals._is_attribution_url(
        "https://user@creativecommons.org/licenses/by/4.0/", hosts
    )
    assert not animal_visuals._is_attribution_url(
        "https://creativecommons.org:444/licenses/by/4.0/", hosts
    )
