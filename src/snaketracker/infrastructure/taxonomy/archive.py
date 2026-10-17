"""Bounded offline Darwin Core Taxon core / VernacularName reader.

Follows https://dwc.tdwg.org/cs/text/. No downloading or extraction; the
temporary reconciliation database is private and never an application database.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import stat
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

from snaketracker.application.species_directory import ProviderTaxon
from snaketracker.infrastructure.taxonomy.catalog import validate
from snaketracker.infrastructure.taxonomy.inaturalist import ANCESTOR_BY_GROUP

NS = {"d": "http://rs.tdwg.org/dwc/text/"}


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_bytes: int = 64 * 1024 * 1024
    max_expanded_bytes: int = 512 * 1024 * 1024
    max_members: int = 16
    max_rows: int = 2_000_000
    max_seconds: float = 120


def _rows(archive: ZipFile, element: ET.Element) -> Iterator[dict[str, str]]:
    location = element.findtext("d:files/d:location", namespaces=NS)
    delimiter = element.get("fieldsTerminatedBy", "\\t").replace("\\t", "\t")
    quote_char = element.get("fieldsEnclosedBy", '"') or None
    if (
        not location
        or len(element.findall("d:files/d:location", NS)) != 1
        or len(delimiter) != 1
        or (quote_char is not None and len(quote_char) != 1)
        or element.get("encoding", "UTF-8").upper() not in {"UTF-8", "UTF8"}
    ):
        raise ValueError("Unsupported Darwin Core file schema or encoding.")
    fields = element.findall("d:field", NS)
    mapping = {field.attrib["term"].rsplit("/", 1)[-1]: field for field in fields}
    identity = (
        element.find("d:id", NS) if element.tag.endswith("core") else element.find("d:coreid", NS)
    )
    if identity is None or len(mapping) != len(fields):
        raise ValueError("Invalid Darwin Core identity/field mapping.")
    try:
        identity_index = int(identity.attrib["index"])
        indexes = {
            term: int(field.attrib["index"])
            for term, field in mapping.items()
            if "index" in field.attrib
        }
    except (KeyError, ValueError) as error:
        raise ValueError("Invalid Darwin Core column index.") from error
    # The core ID and taxonID field legitimately share one column. Field-to-field
    # mappings must be unique; defaults do not consume a column.
    if (
        not 0 <= identity_index < 128
        or any(not 0 <= index < 128 for index in indexes.values())
        or len(set(indexes.values())) != len(indexes)
    ):
        raise ValueError("Invalid or duplicate Darwin Core column index.")
    with (
        archive.open(location) as raw,
        io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as source,
    ):
        reader = csv.reader(
            source,
            delimiter=delimiter,
            quotechar=quote_char,
            quoting=csv.QUOTE_MINIMAL if quote_char else csv.QUOTE_NONE,
            strict=True,
        )
        skip = int(element.get("ignoreHeaderLines", "0"))
        if not 0 <= skip <= 10:
            raise ValueError("Invalid archive header count.")
        for number, row in enumerate(reader):
            if number < skip:
                continue
            if len(row) > 128 or any(len(value) > 4096 for value in row):
                raise ValueError("Archive row exceeds field bounds.")
            if identity_index >= len(row) or any(index >= len(row) for index in indexes.values()):
                raise ValueError("Archive row does not match its declared schema.")
            record = {
                term: row[indexes[term]] if term in indexes else field.get("default", "")
                for term, field in mapping.items()
            }
            record["_id"] = row[identity_index]
            if not record["_id"].strip() or len(record["_id"]) > 128:
                raise ValueError("Archive identity is invalid.")
            yield record


DEFAULT_LIMITS = ArchiveLimits()


def read_archive(
    path: Path,
    *,
    provider: str,
    limits: ArchiveLimits = DEFAULT_LIMITS,
    source_base_url: str | None = None,
) -> Iterator[ProviderTaxon]:
    """Validate bounded archive members/core fields before yielding staged candidates.

    Disk staging avoids keeping a broad scientific catalog/ancestry in process memory.
    Source attribution/rights must be supplied separately to generation creation.
    """
    started = time.monotonic()
    if provider not in {"fixture", "inaturalist"} and not source_base_url:
        raise ValueError(
            "An archive namespace requires an explicit qualified taxon source URL base."
        )
    if source_base_url is not None and (
        not source_base_url.startswith("https://") or len(source_base_url) > 1024
    ):
        raise ValueError("A taxon source URL base must be an explicit bounded HTTPS URL.")
    if not path.is_file() or path.stat().st_size > limits.max_bytes:
        raise ValueError("Archive exceeds the compressed byte bound or is missing.")
    rows = 0

    def check_bound() -> None:
        nonlocal rows
        rows += 1
        if rows > limits.max_rows or time.monotonic() - started > limits.max_seconds:
            raise ValueError("Archive exceeds row or execution time bounds.")

    try:
        with (
            ZipFile(path) as archive,
            tempfile.TemporaryDirectory(prefix="care-keeper-taxonomy-") as scratch,
        ):
            members = archive.infolist()
            names = [member.filename for member in members]
            if (
                len(names) > limits.max_members
                or len(set(names)) != len(names)
                or sum(member.file_size for member in members) > limits.max_expanded_bytes
                or any(
                    PurePosixPath(name).is_absolute()
                    or ".." in PurePosixPath(name).parts
                    or "\\" in name
                    or not name
                    or name.endswith("/")
                    for name in names
                )
                or any(
                    stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1
                    for member in members
                )
            ):
                raise ValueError("Unsafe, duplicate or oversized archive member.")
            if "meta.xml" not in names or archive.getinfo("meta.xml").file_size > 65536:
                raise ValueError("Archive requires a bounded meta.xml descriptor.")
            descriptor = archive.read("meta.xml").decode("utf-8-sig")
            if "<!DOCTYPE" in descriptor.upper() or "<!ENTITY" in descriptor.upper():
                raise ValueError("XML entities and document types are unsupported.")
            meta = ET.fromstring(descriptor)
            cores = meta.findall("d:core", NS)
            if len(cores) != 1 or cores[0].get("rowType") != "http://rs.tdwg.org/dwc/terms/Taxon":
                raise ValueError("Archive requires exactly one Darwin Core Taxon core.")
            extensions = meta.findall("d:extension", NS)
            if any(not node.get("rowType", "").endswith("/VernacularName") for node in extensions):
                raise ValueError(
                    "Unsupported archive extension; taxonomy imports exclude prose/media."
                )
            allowed = {"meta.xml", "eml.xml"} | {
                node.findtext("d:files/d:location", namespaces=NS) for node in [*cores, *extensions]
            }
            if any(name not in allowed for name in names):
                raise ValueError("Unsupported archive member.")
            database = sqlite3.connect(Path(scratch) / "staging.db")
            try:
                database.execute(
                    "CREATE TABLE records(id TEXT PRIMARY KEY, parent TEXT, payload TEXT)"
                )
                database.execute("CREATE TABLE names(id TEXT, name TEXT, PRIMARY KEY(id,name))")
                for record in _rows(archive, cores[0]):
                    check_bound()
                    if (
                        not record.get("scientificName")
                        or record.get("taxonID", record["_id"]) != record["_id"]
                    ):
                        raise ValueError(
                            "Taxon core requires consistent taxonID and scientificName."
                        )
                    database.execute(
                        "INSERT INTO records VALUES(?,?,?)",
                        (
                            record["_id"],
                            record.get("parentNameUsageID") or None,
                            json.dumps(record),
                        ),
                    )
                if not database.execute("SELECT 1 FROM records LIMIT 1").fetchone():
                    raise ValueError("Empty taxonomy generation.")
                for extension in extensions:
                    for record in _rows(archive, extension):
                        check_bound()
                        if not database.execute(
                            "SELECT 1 FROM records WHERE id=?", (record["_id"],)
                        ).fetchone():
                            raise ValueError("Vernacular name references an unknown taxon.")
                        if not record.get("vernacularName") or len(record["vernacularName"]) > 256:
                            raise ValueError("Invalid vernacularName.")
                        database.execute(
                            "INSERT OR IGNORE INTO names VALUES(?,?)",
                            (record["_id"], record["vernacularName"]),
                        )
                database.commit()
                # Validate ancestry before producing rows. No name-based identity inference.
                for identifier, parent, payload in database.execute(
                    "SELECT * FROM records ORDER BY id"
                ):
                    if time.monotonic() - started > limits.max_seconds:
                        raise ValueError("Archive exceeds execution time bound.")
                    ancestors = {identifier}
                    while parent and parent != identifier:
                        if parent in ancestors or len(ancestors) >= 128:
                            raise ValueError("Taxonomy ancestry cycle or depth bound.")
                        ancestors.add(parent)
                        row = database.execute(
                            "SELECT parent FROM records WHERE id=?", (parent,)
                        ).fetchone()
                        if row is None:
                            raise ValueError("Taxonomy has an absent parent.")
                        parent = row[0]
                    if parent == identifier:
                        raise ValueError("Taxonomy ancestry cycle.")
                    record = json.loads(payload)
                    common = tuple(
                        row[0]
                        for row in database.execute(
                            "SELECT name FROM names WHERE id=? ORDER BY name LIMIT 65",
                            (identifier,),
                        )
                    )
                    group = ""
                    if provider == "inaturalist":
                        groups = [
                            key
                            for key, value in ANCESTOR_BY_GROUP.items()
                            if str(value) in ancestors
                        ]
                        if len(groups) > 1:
                            raise ValueError("Conflicting qualified workflow ancestry.")
                        group = groups[0] if groups else ""
                    status = record.get("taxonomicStatus", "unknown").lower()
                    candidate = ProviderTaxon(
                        provider,
                        identifier,
                        (
                            source_base_url
                            or (
                                "https://www.inaturalist.org/taxa/"
                                if provider == "inaturalist"
                                else "https://example.test/taxa/"
                            )
                        )
                        + quote(identifier, safe=""),
                        group,
                        record["scientificName"],
                        preferred_common_name=common[0]
                        if common
                        else record.get("vernacularName") or None,
                        alternative_common_names=common[1:],
                        authorship=record.get("scientificNameAuthorship") or None,
                        taxonomic_status=status,
                        rank=record.get("taxonRank") or None,
                        kingdom=record.get("kingdom") or None,
                        phylum_division=record.get("phylum") or None,
                        class_name=record.get("class") or None,
                        order_name=record.get("order") or None,
                        family=record.get("family") or None,
                        genus=record.get("genus") or None,
                        parent_provider_id=record.get("parentNameUsageID") or None,
                        accepted_provider_id=record.get("acceptedNameUsageID") or None,
                    )
                    validate(candidate)
                    yield candidate
            finally:
                database.close()
    except (
        BadZipFile,
        UnicodeError,
        ET.ParseError,
        csv.Error,
        sqlite3.IntegrityError,
        KeyError,
        OverflowError,
    ) as error:
        raise ValueError(
            "Invalid Darwin Core archive schema, encoding, member or duplicate identity."
        ) from error
