from __future__ import annotations

from uuid import uuid4

from snaketracker.application.care_guides import GuideBundle
from snaketracker.application.natural_history import (
    BiologicalFact,
    GuideBiologyBinding,
    biological_groups,
    guide_digest,
)
from tests.integration.test_care_guides import ROOT
from tests.integration.test_natural_history import version

CONTEXT = {
    "kind": "habitat",
    "life_stage": "all stages",
    "geography": "species range",
    "sex": "all sexes",
    "qualifiers": "Range-wide description",
}


def test_contextual_positions_deduplicate_actual_origins_and_preserve_disagreement():
    a = version(
        uuid4(),
        claims=[dict(**CONTEXT, value="Forest", qualification="Qualified structured fixture")],
    )
    mediated = a.model_copy(
        update={"revision": "mediated", "revision_url": "https://example.test/intermediary"}
    )
    groups = biological_groups((a, mediated), None)
    assert len(groups) == 1 and groups[0].state == "Single source"
    assert len(groups[0].positions[0].references) == 2
    other = a.model_copy(update={"origin": "https://example.test/independent"})
    assert biological_groups((a, other), None)[0].state == "Multiple sources"
    differs = a.model_copy(
        update={
            "claims": (
                BiologicalFact(
                    **CONTEXT, value="Dry woodland", qualification="Independent qualified position"
                ),
            )
        }
    )
    assert biological_groups((a, differs), None)[0].state == "Sources differ"
    contextual = a.model_copy(
        update={
            "claims": (
                BiologicalFact(
                    **(CONTEXT | {"geography": "one island"}),
                    value="Forest",
                    qualification="Local qualified position",
                ),
            )
        }
    )
    assert len(biological_groups((a, contextual), None)) == 2


def test_only_exact_qualified_wild_guide_claims_join_natural_history():
    guide = GuideBundle.model_validate_json(
        (ROOT / "reference/care-guides/reviewed-v1.json").read_bytes()
    ).guides[0]
    original = guide.claims[0]
    wild = original.model_copy(
        update={
            "fact_key": "natural_habitat",
            "value_text": "Forest",
            "value_number": None,
            "minimum": None,
            "maximum": None,
            "unit": None,
            "context": "wild",
        }
    )
    guide = guide.model_copy(update={"claims": (wild,)})
    binding = GuideBiologyBinding(
        **CONTEXT,
        guide_version=guide.version,
        guide_sha256=guide_digest(guide),
        claim_id=wild.claim_id,
        origin="https://example.test/original",
        qualification="Explicit reviewed biological classification",
    )
    item = version(uuid4(), sections=[], guide_bindings=[binding.model_dump()])
    groups = biological_groups((item,), guide)
    assert len(groups) == 1
    assert groups[0].positions[0].guide_claim_ids == (wild.claim_id,)
    assert biological_groups((item,), guide.model_copy(update={"version": guide.version + 1})) == ()
    for context in ["captive", None, "legacy unknown"]:
        changed = guide.model_copy(
            update={"claims": (wild.model_copy(update={"context": context}),)}
        )
        bound = binding.model_copy(update={"guide_sha256": guide_digest(changed)})
        assert (
            biological_groups((item.model_copy(update={"guide_bindings": (bound,)}),), changed)
            == ()
        )
    assert original.model_dump() != wild.model_dump()


def test_equivalent_positions_retain_each_source_qualification():
    first = version(
        uuid4(),
        claims=[
            dict(**CONTEXT, value="Forest", qualification="First source field study qualification")
        ],
    )
    second = first.model_copy(
        update={
            "origin": "https://example.test/second",
            "revision_url": "https://example.test/second/revision",
            "claims": (
                first.claims[0].model_copy(
                    update={"qualification": "Second source regional survey qualification"}
                ),
            ),
        }
    )
    group = biological_groups((first, second), None)[0]
    assert group.state == "Multiple sources"
    assert len(group.positions) == 1
    assert {(e.origin, e.reference, e.qualification) for e in group.positions[0].evidence} == {
        (first.origin, first.revision_url, first.claims[0].qualification),
        (second.origin, second.revision_url, second.claims[0].qualification),
    }
