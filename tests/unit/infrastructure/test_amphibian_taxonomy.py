from __future__ import annotations

import json

from snaketracker.infrastructure.taxonomy import inaturalist
from snaketracker.infrastructure.taxonomy.archive import read_archive
from snaketracker.infrastructure.taxonomy.inaturalist import INaturalistTaxonomyProvider
from tests.unit.infrastructure.test_inaturalist_taxonomy import Response
from tests.unit.infrastructure.test_taxonomy_archive import META, archive


def test_live_amphibian_mapping_uses_provider_ancestry_not_common_names(monkeypatch):
    frog = {
        "id": 25591,
        "name": "Rana temporaria",
        "rank": "species",
        "preferred_common_name": "European Common Frog",
        "ancestor_ids": [48460, 1, 2, 355675, 20978, 20979, 25474],
    }
    records = [
        frog,
        {**frog, "id": 9001, "name": "Misleading name", "ancestor_ids": [85553]},
        {**frog, "id": 9002, "ancestor_ids": [20978, 85553]},
        {**frog, "id": 9003, "ancestor_ids": ["20978", 20979]},
        {**frog, "id": 9004, "ancestor_ids": [20978.0, 20979]},
    ]
    seen = []

    def transport(request, *, timeout):
        seen.append(request.full_url)
        return Response(json.dumps({"results": records}).encode())

    monkeypatch.setattr(inaturalist, "urlopen", transport)
    results = INaturalistTaxonomyProvider().search("common frog", "amphibian", limit=10)
    assert [row.provider_id for row in results] == ["25591"]
    assert results[0].supported_group == "amphibian"
    assert results[0].source_url == "https://www.inaturalist.org/taxa/25591"
    assert all("household" not in url and "animal_id" not in url for url in seen)


def test_live_detail_retains_qualified_classification_and_parent(monkeypatch):
    record = {
        "id": 25591,
        "name": "Rana temporaria",
        "rank": "species",
        "parent_id": 25474,
        "ancestor_ids": [1, 20978, 20979, 25474],
        "ancestors": [
            {"id": 1, "rank": "kingdom", "name": "Animalia"},
            {"id": 20978, "rank": "class", "name": "Amphibia"},
            {"id": 20979, "rank": "order", "name": "Anura"},
            {"id": 25474, "rank": "genus", "name": "Rana"},
        ],
    }
    monkeypatch.setattr(
        inaturalist,
        "urlopen",
        lambda *args, **kwargs: Response(json.dumps({"results": [record]}).encode()),
    )
    selected = INaturalistTaxonomyProvider().detail("25591", "amphibian")
    assert selected.class_name == "Amphibia" and selected.order_name == "Anura"
    assert selected.parent_provider_id == "25474"


def test_archive_amphibian_mapping_requires_namespaced_ancestry_and_species_rank(tmp_path):
    meta = META.replace(
        "</core>", '<field index="4" term="http://rs.tdwg.org/dwc/terms/taxonRank"/></core>'
    )
    path = archive(
        tmp_path,
        meta=meta,
        names="25591\tEuropean Common Frog\n",
        taxa=(
            "id\tname\tparent\tclass\trank\n"
            "20978\tAmphibia\t\tAmphibia\tclass\n"
            "20979\tAnura\t20978\tAmphibia\torder\n"
            "25591\tRana temporaria\t20979\tAmphibia\tspecies\n"
            "9000\tFrog by name only\t\tAmphibia\tspecies\n"
        ),
    )
    qualified = {row.provider_id: row for row in read_archive(path, provider="inaturalist")}
    assert qualified["25591"].supported_group == "amphibian"
    assert qualified["20978"].supported_group == ""
    assert qualified["20979"].supported_group == ""
    assert qualified["9000"].supported_group == ""
    unqualified = tuple(read_archive(path, provider="fixture"))
    assert all(row.supported_group == "" for row in unqualified)
