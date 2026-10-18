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
    names="2\tCommon frog\n",
):
    path = tmp_path / "synthetic.zip"
    with ZipFile(path, "w") as handle:
        handle.writestr("meta.xml", meta)
        handle.writestr("taxa.tsv", taxa)
        handle.writestr("names.tsv", names)
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


@pytest.mark.parametrize("blank_status", [False, True])
def test_operator_validate_stage_promote_search_and_checksum_guard(
    tmp_path, monkeypatch, capsys, blank_status
):
    import hashlib
    import json
    import sys
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from snaketracker.operations.taxonomy import main

    if blank_status:
        meta = META.replace(
            "</core>",
            '<field index="4" term="http://rs.tdwg.org/dwc/terms/taxonomicStatus"/></core>',
        )
        path = archive(
            tmp_path,
            meta=meta,
            taxa=(
                "id\tname\tparent\tclass\tstatus\n1\tAnimalia\t\t\t \n"
                "2\tRana temporaria\t1\tAmphibia\t\n"
            ),
        )
    else:
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


@pytest.mark.parametrize("accepted", ["absent", "cycle", "self"])
def test_archive_validates_accepted_name_relationships_before_dry_run_success(tmp_path, accepted):
    descriptor = META.replace(
        "</core>",
        '<field index="4" term="http://rs.tdwg.org/dwc/terms/acceptedNameUsageID"/></core>',
    )
    links = {"absent": ("missing", ""), "cycle": ("2", "1"), "self": ("1", "")}[accepted]
    path = archive(
        tmp_path,
        meta=descriptor,
        taxa=(
            "id\tname\tparent\tclass\taccepted\n"
            f"1\tAnimalia\t\tAnimalia\t{links[0]}\n"
            f"2\tRana temporaria\t1\tAmphibia\t{links[1]}\n"
        ),
    )
    with pytest.raises(ValueError, match=r"absent|cycle|self"):
        tuple(read_archive(path, provider="fixture"))


def test_archive_default_values_and_field_count_are_bounded(tmp_path):
    for extra in (
        '<field default="' + "x" * 4097 + '" term="https://example.test/extra"/>',
        "".join(f'<field default="x" term="https://example.test/extra{i}"/>' for i in range(129)),
    ):
        descriptor = META.replace("</core>", extra + "</core>")
        with pytest.raises(ValueError, match=r"field|default|column"):
            tuple(read_archive(archive(tmp_path, meta=descriptor), provider="fixture"))


def test_materialized_defaults_cannot_exceed_archive_expanded_byte_budget(tmp_path):
    descriptor = META.replace(
        "</core>", '<field default="' + "x" * 256 + '" term="https://example.test/extra"/></core>'
    )
    rows = "id\tname\tparent\tclass\n" + "".join(
        f"{i}\tRana species {i}\t\tAmphibia\n" for i in range(10)
    )
    path = archive(tmp_path, meta=descriptor, taxa=rows)
    with ZipFile(path) as handle:
        expanded = sum(member.file_size for member in handle.infolist())
    with pytest.raises(ValueError, match="materialized"):
        tuple(
            read_archive(
                path,
                provider="fixture",
                limits=replace(ArchiveLimits(), max_expanded_bytes=expanded),
            )
        )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "unknown"),
        ("   ", "unknown"),
        (" ACCEPTED ", "accepted"),
        (" unknown ", "unknown"),
        (" InAcTiVe ", "inactive"),
        (" Synonym ", "synonym"),
    ],
)
def test_optional_archive_status_normalizes_blank_space_and_case(tmp_path, raw, expected):
    meta = META.replace(
        "</core>",
        '<field index="4" term="http://rs.tdwg.org/dwc/terms/taxonomicStatus"/></core>',
    )
    path = archive(
        tmp_path,
        meta=meta,
        taxa=(
            f"id\tname\tparent\tclass\tstatus\n1\tAnimalia\t\t\t{raw}\n"
            f"2\tRana temporaria\t1\tAmphibia\t{raw}\n"
        ),
    )
    assert [record.taxonomic_status for record in read_archive(path, provider="fixture")] == [
        expected,
        expected,
    ]


@pytest.mark.parametrize("apply", [False, True])
def test_operator_parses_the_verified_bytes_when_original_archive_is_replaced(
    tmp_path, monkeypatch, capsys, apply
):
    import hashlib
    import json
    import sys
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from snaketracker.operations import taxonomy

    original = archive(tmp_path)
    expected = hashlib.sha256(original.read_bytes()).hexdigest()
    replacement_folder = tmp_path / "replacement"
    replacement_folder.mkdir()
    replacement = archive(
        replacement_folder,
        taxa="id\tname\tparent\tclass\n1\tAnimalia\t\t\n2\tReplacement species\t1\tAmphibia\n",
    ).read_bytes()
    real_reader = taxonomy.read_archive
    parsed_checksums = []

    def replace_original_before_parsing(path, **kwargs):
        original.write_bytes(replacement)
        parsed_checksums.append(hashlib.sha256(Path(path).read_bytes()).hexdigest())
        yield from real_reader(path, **kwargs)

    monkeypatch.setattr(taxonomy, "read_archive", replace_original_before_parsing)
    prefix = []
    if apply:
        database = tmp_path / "isolated.db"
        root = Path(__file__).parents[3]
        config = Config(root / "alembic.ini")
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
        command.upgrade(config, "head")
        prefix = ["--database", str(database), "--apply"]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "taxonomy",
            *prefix,
            "stage",
            str(original),
            "--provider",
            "fixture",
            "--label",
            "Verified bytes",
            "--source-url",
            "https://example.test/archive",
            "--retrieved-at",
            "2026-10-17T00:00:00Z",
            "--rights",
            "Synthetic fixture",
            "--sha256",
            expected,
        ],
    )
    taxonomy.main()
    result = json.loads(capsys.readouterr().out)
    assert parsed_checksums == [expected]
    assert original.read_bytes() == replacement
    assert result.get("state", "ready") == "ready"
    if not apply:
        assert result["checksum"] == expected
    else:
        engine = taxonomy.create_readonly_sqlite_engine(database)
        try:
            with engine.connect() as connection:
                assert (
                    connection.exec_driver_sql(
                        "SELECT checksum FROM taxonomy_generations"
                    ).scalar_one()
                    == expected
                )
                payload = connection.exec_driver_sql(
                    "SELECT payload FROM taxonomy_facts "
                    "WHERE json_extract(payload,'$.provider_id')='2'"
                ).scalar_one()
                assert json.loads(payload)["accepted_scientific_name"] == "Rana temporaria"
        finally:
            engine.dispose()


def test_archive_parse_deadline_excludes_consumer_staging_pauses(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from snaketracker.infrastructure.taxonomy import archive as module

    clock = [0.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    rows = read_archive(
        archive(tmp_path), provider="fixture", limits=replace(ArchiveLimits(), max_seconds=1)
    )
    assert next(rows).provider_id == "1"
    clock[0] += 500  # Simulate database staging while the generator is suspended.
    assert next(rows).provider_id == "2"
    clock[0] += 500
    with pytest.raises(StopIteration):
        next(rows)


def test_archive_active_parse_work_still_obeys_deadline(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from snaketracker.infrastructure.taxonomy import archive as module

    clock = [0.0]
    real_rows = module._rows

    def slow_rows(*args):
        for row in real_rows(*args):
            clock[0] += 2
            yield row

    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(module, "_rows", slow_rows)
    with pytest.raises(ValueError, match="execution time"):
        tuple(
            read_archive(
                archive(tmp_path),
                provider="fixture",
                limits=replace(ArchiveLimits(), max_seconds=1),
            )
        )


@pytest.mark.parametrize("count", [65, 66, 100])
def test_vernacular_alias_bound_rejects_excess_instead_of_truncating(tmp_path, count):
    path = archive(
        tmp_path, names="".join(f"2\tVernacular {index:03d}\n" for index in range(count))
    )
    if count > 65:
        with pytest.raises(ValueError, match="vernacular"):
            tuple(read_archive(path, provider="fixture"))
    else:
        records = tuple(read_archive(path, provider="fixture"))
        assert len(records[1].alternative_common_names) == 64
        assert records[1].preferred_common_name == "Vernacular 000"
        assert records[1].alternative_common_names[-1] == "Vernacular 064"


@pytest.mark.parametrize("marker", ["true", " TRUE ", "1"])
@pytest.mark.parametrize("reverse", [False, True])
def test_vernacular_preferred_marker_survives_duplicate_rows_and_order(tmp_path, marker, reverse):
    meta = META.replace(
        "</extension>",
        '<field index="2" term="http://rs.gbif.org/terms/1.0/isPreferredName"/></extension>',
    )
    names = [
        "2\tA regional frog\tfalse\n",
        "2\tZ preferred frog\tfalse\n",
        f"2\tZ preferred frog\t{marker}\n",
    ]
    if reverse:
        names.reverse()
    records = tuple(
        read_archive(archive(tmp_path, meta=meta, names="".join(names)), provider="fixture")
    )
    assert records[1].preferred_common_name == "Z preferred frog"
    assert records[1].alternative_common_names == ("A regional frog",)


@pytest.mark.parametrize("marker", ["sometimes", "2"])
def test_malformed_vernacular_preference_requires_reconciliation(tmp_path, marker):
    meta = META.replace(
        "</extension>",
        '<field index="2" term="http://rs.gbif.org/terms/1.0/isPreferredName"/></extension>',
    )
    with pytest.raises(ValueError, match="isPreferredName"):
        tuple(
            read_archive(
                archive(tmp_path, meta=meta, names=f"2\tCommon frog\t{marker}\n"),
                provider="fixture",
            )
        )


def test_multiple_preferred_names_use_stable_order_and_retain_alternatives(tmp_path):
    meta = META.replace(
        "</extension>",
        '<field index="2" term="http://rs.gbif.org/terms/1.0/isPreferredName"/></extension>',
    )
    records = tuple(
        read_archive(
            archive(
                tmp_path,
                meta=meta,
                names="2\tZ preferred frog\ttrue\n2\tA preferred frog\ttrue\n2\tEarlier alias\t0\n",
            ),
            provider="fixture",
        )
    )
    assert records[1].preferred_common_name == "A preferred frog"
    assert records[1].alternative_common_names == ("Z preferred frog", "Earlier alias")


def synonym_archive(tmp_path, *, synonym_parent=""):
    meta = META.replace(
        "</core>",
        '<field index="4" term="http://rs.tdwg.org/dwc/terms/acceptedNameUsageID"/>'
        '<field index="5" term="http://rs.tdwg.org/dwc/terms/taxonomicStatus"/></core>',
    )
    return archive(
        tmp_path,
        meta=meta,
        names="",
        taxa=(
            "id\tname\tparent\tclass\taccepted\tstatus\n"
            "85553\tSerpentes\t\tReptilia\t\taccepted\n"
            "47126\tPlantae\t\t\t\taccepted\n"
            "9\tPython regius\t85553\tReptilia\t\taccepted\n"
            f"10\tColuber regius\t{synonym_parent}\tReptilia\t9\tsynonym\n"
            "11\tHistorical regius\t\tReptilia\t10\tsynonym\n"
        ),
    )


@pytest.mark.parametrize("provider", ["fixture", "inaturalist"])
def test_synonym_group_follows_accepted_name_ancestry_for_local_search(tmp_path, provider):
    from datetime import UTC, datetime
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from snaketracker.application.local_taxonomy import GenerationSource
    from snaketracker.infrastructure.database.engine import create_sqlite_engine
    from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog

    records = tuple(read_archive(synonym_archive(tmp_path), provider=provider))
    by_id = {record.provider_id: record for record in records}
    expected = "snake" if provider == "inaturalist" else ""
    assert all(by_id[identifier].supported_group == expected for identifier in ("9", "10", "11"))
    root = Path(__file__).parents[3]
    database = tmp_path / "synonyms.db"
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database, require_local_storage=False)
    try:
        catalog = LocalTaxonomyCatalog(engine)
        now = datetime.now(UTC)
        generation = catalog.begin_generation(
            GenerationSource(
                label="Synthetic accepted ancestry",
                provider=provider,
                source_url="https://example.test/archive",
                retrieved_at=now,
                snapshot_at=now,
                checksum="f" * 64,
                rights="Synthetic fixture",
            ),
            imported_at=now,
        )
        catalog.stage(generation, records)
        catalog.validate_generation(generation)
        for conflict in catalog.conflicts():
            catalog.resolve_conflict(
                conflict.conflict_id,
                decided_by="Owner",
                reason="Retain synthetic synonym identities without merging",
            )
        catalog.promote(generation)
        matches = catalog.search("Coluber regius", group="snake" if expected else None)
        assert len(matches) == 1
        assert matches[0].provider_id == "10"
        assert matches[0].taxonomic_status == "synonym"
        assert catalog.search("Historical regius", group="snake" if expected else None)
        if not expected:
            assert not catalog.search("Coluber regius", group="snake")
    finally:
        engine.dispose()


def test_synonym_parent_and_accepted_name_conflicting_groups_require_reconciliation(tmp_path):
    with pytest.raises(ValueError, match="Conflicting qualified workflow ancestry"):
        tuple(
            read_archive(synonym_archive(tmp_path, synonym_parent="47126"), provider="inaturalist")
        )


@pytest.mark.parametrize("core_common", ["Core common frog", "Z preferred frog", "Another alias"])
def test_core_vernacular_name_is_retained_with_preferred_extension_names(tmp_path, core_common):
    meta = META.replace(
        "</core>", '<field index="4" term="http://rs.tdwg.org/dwc/terms/vernacularName"/></core>'
    )
    meta = meta.replace(
        "</extension>",
        '<field index="2" term="http://rs.gbif.org/terms/1.0/isPreferredName"/></extension>',
    )
    records = tuple(
        read_archive(
            archive(
                tmp_path,
                meta=meta,
                taxa=(
                    "id\tname\tparent\tclass\tcommon\n1\tAnimalia\t\t\t\n"
                    f"2\tRana temporaria\t1\tAmphibia\t{core_common}\n"
                ),
                names="2\tZ preferred frog\ttrue\n2\tAnother alias\tfalse\n",
            ),
            provider="fixture",
        )
    )
    selected = records[1]
    assert selected.preferred_common_name == "Z preferred frog"
    assert set(selected.alternative_common_names) == {core_common, "Another alias"} - {
        "Z preferred frog"
    }
    assert len(selected.alternative_common_names) == len(set(selected.alternative_common_names))


@pytest.mark.parametrize("count", [64, 65])
@pytest.mark.parametrize("duplicate", [False, True])
def test_combined_core_and_extension_names_share_one_unique_alias_bound(tmp_path, count, duplicate):
    meta = META.replace(
        "</core>", '<field index="4" term="http://rs.tdwg.org/dwc/terms/vernacularName"/></core>'
    )
    common = "Vernacular 000" if duplicate else "Core common frog"
    path = archive(
        tmp_path,
        meta=meta,
        taxa=(
            "id\tname\tparent\tclass\tcommon\n1\tAnimalia\t\t\t\n"
            f"2\tRana temporaria\t1\tAmphibia\t{common}\n"
        ),
        names="".join(f"2\tVernacular {i:03d}\n" for i in range(count)),
    )
    if count == 65 and not duplicate:
        with pytest.raises(ValueError, match="vernacular"):
            tuple(read_archive(path, provider="fixture"))
    else:
        selected = tuple(read_archive(path, provider="fixture"))[1]
        retained = {selected.preferred_common_name, *selected.alternative_common_names}
        assert common in retained
        assert len(retained) == count + int(not duplicate)
