from __future__ import annotations

from dataclasses import replace
from zipfile import ZipFile

import pytest

from snaketracker.infrastructure.taxonomy.archive import ArchiveLimits, read_archive

META = """<archive xmlns="http://rs.tdwg.org/dwc/text/">
<core encoding="UTF-8" fieldsTerminatedBy="\\t" ignoreHeaderLines="1"
rowType="http://rs.tdwg.org/dwc/terms/Taxon"><files><location>taxa.tsv</location></files>
<id index="0"/>
<field index="0" term="http://rs.tdwg.org/dwc/terms/taxonID"/>
<field index="1" term="http://rs.tdwg.org/dwc/terms/scientificName"/>
<field index="2" term="http://rs.tdwg.org/dwc/terms/parentNameUsageID"/>
<field index="3" term="http://rs.tdwg.org/dwc/terms/class"/>
</core><extension encoding="UTF-8" fieldsTerminatedBy="\\t"
rowType="http://rs.gbif.org/terms/1.0/VernacularName"><files><location>names.tsv</location></files>
<coreid index="0"/><field index="1" term="http://rs.tdwg.org/dwc/terms/vernacularName"/>
</extension></archive>"""


def archive(
    tmp_path,
    *,
    meta=META,
    taxa="id\tname\tparent\tclass\n1\tAnimalia\t\t\n2\tRana temporaria\t1\tAmphibia\n",
    extra=None,
):
    path = tmp_path / "synthetic.zip"
    with ZipFile(path, "w") as handle:
        handle.writestr("meta.xml", meta)
        handle.writestr("taxa.tsv", taxa)
        handle.writestr("names.tsv", "2\tCommon frog\n")
        if extra:
            handle.writestr(*extra)
    return path


def test_meta_mapped_taxon_core_and_vernacular_extension_are_reference_only(tmp_path):
    records = tuple(read_archive(archive(tmp_path), provider="fixture"))
    assert records[1].provider_id == "2"
    assert records[1].preferred_common_name == "Common frog"
    assert records[1].class_name == "Amphibia"
    assert records[1].parent_provider_id == "1"
    assert records[1].supported_group == ""


@pytest.mark.parametrize("member", ["../escape", "/escape", "dir/../../escape", "taxa.tsv"])
def test_unsafe_or_duplicate_members_are_rejected_before_parsing(tmp_path, member):
    with pytest.raises(ValueError, match="member"):
        tuple(read_archive(archive(tmp_path, extra=(member, "bad")), provider="fixture"))


def test_size_row_deadline_and_schema_bounds(tmp_path):
    path = archive(tmp_path)
    for limits in (
        replace(ArchiveLimits(), max_bytes=1),
        replace(ArchiveLimits(), max_rows=1),
        replace(ArchiveLimits(), max_seconds=0),
    ):
        with pytest.raises(ValueError):
            tuple(read_archive(path, provider="fixture", limits=limits))
    with pytest.raises(ValueError, match="scientificName"):
        tuple(
            read_archive(
                archive(tmp_path, meta=META.replace("scientificName", "wrongTerm")),
                provider="fixture",
            )
        )
    with pytest.raises(ValueError, match="XML"):
        tuple(
            read_archive(
                archive(tmp_path, meta='<!DOCTYPE x [<!ENTITY x "bad">]>' + META),
                provider="fixture",
            )
        )


def test_qualified_ancestry_maps_current_groups_without_enabling_amphibia(tmp_path):
    path = archive(
        tmp_path,
        taxa=(
            "id\tname\tparent\tclass\n85553\tSerpentes\t\tReptilia\n"
            "9\tPython regius\t85553\tReptilia\n2\tRana temporaria\t\tAmphibia\n"
        ),
    )
    # Unknown provider namespaces never borrow iNaturalist ancestor identifiers.
    assert tuple(read_archive(path, provider="fixture"))[1].supported_group == ""
    assert tuple(read_archive(path, provider="inaturalist"))[1].supported_group == "snake"


def test_unknown_extension_and_missing_common_name_taxon_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="extension"):
        tuple(
            read_archive(
                archive(tmp_path, meta=META.replace("VernacularName", "Description")),
                provider="fixture",
            )
        )
    path = archive(tmp_path, taxa="id\tname\tparent\tclass\n1\tAnimalia\t\t\n")
    with pytest.raises(ValueError, match="unknown"):
        tuple(read_archive(path, provider="fixture"))


def test_operator_validate_stage_promote_search_and_checksum_guard(tmp_path, monkeypatch, capsys):
    import hashlib
    import json
    import sys
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from snaketracker.operations.taxonomy import main

    path = archive(tmp_path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    args = [
        "stage",
        str(path),
        "--provider",
        "fixture",
        "--label",
        "A",
        "--source-url",
        "https://example.test/archive",
        "--retrieved-at",
        "2026-10-17T00:00:00Z",
        "--snapshot-at",
        "2026-10-16T00:00:00Z",
        "--rights",
        "Synthetic fixture",
        "--sha256",
        checksum,
    ]

    def invoke(arguments):
        capsys.readouterr()
        monkeypatch.setattr(sys, "argv", ["taxonomy", *arguments])
        main()
        return json.loads(capsys.readouterr().out)

    assert invoke(args)["applied"] is False
    assert not (tmp_path / "app.db").exists()
    with pytest.raises(SystemExit):
        invoke([*args[:-1], "0" * 64])
    with pytest.raises(SystemExit):
        invoke(["--apply", *args])
    root = Path(__file__).parents[3]
    database = tmp_path / "app.db"
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    common = ["--database", str(database)]
    generation = invoke([*common, "--apply", *args])["generation"]
    with pytest.raises(SystemExit):
        invoke([*common, "promote", generation])
    assert invoke([*common, "--apply", "promote", generation])["active_generation"] == generation
    result = invoke([*common, "search", "Common frog"])[0]
    assert result["workflow_group"] is None
    assert invoke([*common, "resolve", result["taxon_id"]])["scientific_name"] == "Rana temporaria"
    assert invoke([*common, "conflicts"]) == []
    assert invoke([*common, "--apply", "rollback", generation])["active_generation"] == generation
    with pytest.raises(ValueError, match=r"retained|Active"):
        invoke([*common, "--apply", "cleanup", generation, "--keep", generation])


def test_archive_rejects_direct_parent_self_cycle(tmp_path):
    with pytest.raises(ValueError, match="cycle"):
        tuple(
            read_archive(
                archive(tmp_path, taxa="id\tname\tparent\tclass\n2\tRana\t2\tAmphibia\n"),
                provider="fixture",
            )
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("--label", " "),
        ("--rights", " "),
        ("--source-url", "http://example.test/archive"),
        ("--retrieved-at", "2026-10-17T00:00:00"),
        ("--snapshot-at", "2026-10-16T00:00:00"),
    ],
)
def test_dry_run_and_apply_share_source_metadata_validation(tmp_path, monkeypatch, field, value):
    import hashlib
    import sys

    from snaketracker.operations.taxonomy import main

    path = archive(tmp_path)
    args = [
        "stage",
        str(path),
        "--provider",
        "fixture",
        "--label",
        "A",
        "--source-url",
        "https://example.test/archive",
        "--retrieved-at",
        "2026-10-17T00:00:00Z",
        "--snapshot-at",
        "2026-10-16T00:00:00Z",
        "--rights",
        "Synthetic",
        "--sha256",
        hashlib.sha256(path.read_bytes()).hexdigest(),
    ]
    args[args.index(field) + 1] = value
    before = path.read_bytes()
    for prefix in ([], ["--apply"]):
        monkeypatch.setattr(sys, "argv", ["taxonomy", *prefix, *args])
        with pytest.raises(ValueError):
            main()
    assert path.read_bytes() == before
    assert not (tmp_path / "app.db").exists()


@pytest.mark.parametrize("index", ["-1", "0", "2", "4", "128", "invalid"])
def test_archive_rejects_invalid_or_duplicate_field_column_indexes(tmp_path, index):
    descriptor = META.replace('<field index="1"', f'<field index="{index}"', 1)
    with pytest.raises(ValueError):
        tuple(
            read_archive(
                archive(
                    tmp_path,
                    meta=descriptor,
                    taxa=(
                        "id\tname\tparent\tclass\n1\tAnimalia\t\tAnimalia\n"
                        "2\tRana temporaria\t1\tAmphibia\n"
                    ),
                ),
                provider="fixture",
            )
        )


@pytest.mark.parametrize("index", ["-1", "4", "128", "invalid"])
def test_archive_rejects_invalid_identity_column_indexes(tmp_path, index):
    descriptor = META.replace('<id index="0"', f'<id index="{index}"', 1)
    with pytest.raises(ValueError):
        tuple(
            read_archive(
                archive(
                    tmp_path,
                    meta=descriptor,
                    taxa=(
                        "id\tname\tparent\tclass\n1\tAnimalia\t\tAnimalia\n"
                        "2\tRana temporaria\t1\tAmphibia\n"
                    ),
                ),
                provider="fixture",
            )
        )


def test_empty_archive_is_rejected_by_reader_and_dry_run(tmp_path, monkeypatch):
    import hashlib
    import sys

    from snaketracker.operations.taxonomy import main

    path = archive(
        tmp_path,
        meta=META.split("<extension")[0] + "</archive>",
        taxa="id\tname\tparent\tclass\n",
    )
    # Empty extension is absent from the schema and archive.
    with ZipFile(path, "r") as original:
        members = {name: original.read(name) for name in ("meta.xml", "taxa.tsv")}
    with ZipFile(path, "w") as rewritten:
        for name, content in members.items():
            rewritten.writestr(name, content)
    with pytest.raises(ValueError, match="Empty"):
        tuple(read_archive(path, provider="fixture"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "taxonomy",
            "stage",
            str(path),
            "--provider",
            "fixture",
            "--label",
            "Empty",
            "--source-url",
            "https://example.test/archive",
            "--retrieved-at",
            "2026-10-17T00:00:00Z",
            "--rights",
            "Synthetic",
            "--sha256",
            hashlib.sha256(path.read_bytes()).hexdigest(),
        ],
    )
    with pytest.raises(ValueError, match="Empty"):
        main()
    assert not (tmp_path / "app.db").exists()
