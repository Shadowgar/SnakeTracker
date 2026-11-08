"""Convert retained inventories offline and verify explicitly trusted release signatures.

This operator tool never scans, rebuilds, loads an image, opens application data,
selects a trust root or asserts release qualification. Inputs remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_JSON_BYTES = 64 * 1024 * 1024


def _json_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    with path.open("rb") as source:
        data = source.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("JSON evidence exceeds the 64 MiB input limit.")
    result = json.loads(data, object_pairs_hook=_unique_object)
    if not isinstance(result, dict):
        raise ValueError("Evidence must be a JSON object.")
    return result, data


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise ValueError(f"Invalid {label} text.")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"Control characters in {label} text.")
    return value


def _hex(value: str, length: int, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError(f"Invalid {label} digest.")
    return value


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _sbom(scan: dict[str, Any], image_id: str, source_sha: str) -> dict[str, Any]:
    _hex(source_sha, 40, "source")
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise ValueError("Invalid image identity.")
    _hex(image_id.removeprefix("sha256:"), 64, "image")
    metadata = scan.get("Metadata", {})
    if scan.get("SchemaVersion") != 2 or scan.get("ArtifactType") != "container_image":
        raise ValueError("Expected a Trivy v2 container image inventory.")
    if metadata.get("ImageID") != image_id:
        raise ValueError("Retained scan image identity does not match the pinned image.")
    labels = metadata.get("ImageConfig", {}).get("config", {}).get("Labels", {})
    if labels.get("org.opencontainers.image.revision") != source_sha:
        raise ValueError("Retained scan source identity does not match the pinned source.")
    results = scan.get("Results")
    if not isinstance(results, list) or not results:
        raise ValueError("Retained scan contains no package inventory.")
    components: dict[str, dict[str, Any]] = {}
    for result in results:
        target = _text(result.get("Target"), "inventory target")
        package_type = _text(result.get("Type"), "package ecosystem")
        packages = result.get("Packages")
        if not isinstance(packages, list) or not packages:
            raise ValueError("Every retained result must contain a package inventory.")
        for package in packages:
            name = _text(package.get("Name"), "package name")
            version = _text(package.get("Version"), "package version")
            purl = package.get("Identifier", {}).get("PURL")
            identity = {"target": target, "type": package_type, "name": name, "version": version}
            if purl is not None:
                identity["purl"] = _text(purl, "package URL")
                if not purl.startswith("pkg:"):
                    raise ValueError("Invalid package URL.")
            reference = "pkg-occurrence:" + hashlib.sha256(_json_bytes(identity)).hexdigest()
            component: dict[str, Any] = {
                "type": "library",
                "bom-ref": reference,
                "name": name,
                "version": version,
                "properties": [
                    {"name": "carekeeper:inventory:target", "value": target},
                    {"name": "carekeeper:inventory:ecosystem", "value": package_type},
                ],
            }
            if purl is not None:
                component["purl"] = purl
            licenses = package.get("Licenses", [])
            if not isinstance(licenses, list):
                raise ValueError("Invalid package licenses.")
            if licenses:
                component["licenses"] = [
                    {"license": {"name": item}}
                    for item in sorted({_text(item, "package license") for item in licenses})
                ]
            if reference in components and components[reference] != component:
                raise ValueError("Conflicting duplicate package inventory entries.")
            components[reference] = component
    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "lifecycles": [{"phase": "post-build"}],
            "component": {
                "type": "container",
                "bom-ref": image_id,
                "name": "Care Keeper",
                "version": source_sha,
                "hashes": [{"alg": "SHA-256", "content": image_id.removeprefix("sha256:")}],
                "properties": [
                    {"name": "carekeeper:image:digest-kind", "value": "Docker image configuration"},
                    {"name": "carekeeper:source:git-sha", "value": source_sha},
                ],
            },
        },
        "components": [components[key] for key in sorted(components)],
        "compositions": [{"aggregate": "unknown", "assemblies": [image_id]}],
        "properties": [
            {
                "name": "carekeeper:inventory:scope",
                "value": "Retained scanner observations only; dependency completeness and release "
                "qualification are not asserted. Licenses are unmodified scanner declarations.",
            }
        ],
    }


def export_evidence(
    *,
    scan: Path,
    scan_sha256: str,
    archive: Path,
    archive_sha256: str,
    image_id: str,
    source_sha: str,
    output: Path,
) -> dict[str, Any]:
    """Create a new evidence directory after all pinned input checks succeed."""
    if output.exists():
        raise FileExistsError(
            "Evidence output must be a new directory; existing files are preserved."
        )
    document, raw = _read_json(scan)
    if hashlib.sha256(raw).hexdigest() != _hex(scan_sha256, 64, "scan"):
        raise ValueError("Retained scan checksum does not match the trusted receipt.")
    archive_digest, archive_size = _file_digest(archive)
    if archive_digest != _hex(archive_sha256, 64, "archive"):
        raise ValueError("Retained archive checksum does not match the trusted receipt.")
    sbom = _json_bytes(_sbom(document, image_id, source_sha))
    index = {
        "format_version": 1,
        "image_id": image_id,
        "source_sha": source_sha,
        "scan": {"sha256": scan_sha256, "bytes": len(raw)},
        "archive": {"sha256": archive_digest, "bytes": archive_size},
        "sbom": {"name": "sbom.cdx.json", "sha256": hashlib.sha256(sbom).hexdigest()},
        "signature": "not_supplied",
        "qualification": "not_asserted",
    }
    output.mkdir(mode=0o700)
    (output / "sbom.cdx.json").write_bytes(sbom)
    (output / "release-evidence.json").write_bytes(_json_bytes(index))
    return index


def verify_evidence(
    *, bundle: Path, scan: Path, archive: Path, signature: Path, public_key: Path
) -> dict[str, Any]:
    """Verify an exact signed index and its inputs against a caller-chosen trust key.

    The key is never read from the bundle. This proves byte identity and signature
    validity under that supplied key, not the signer's authority or milestone approval.
    """
    index, signed = _read_json(bundle / "release-evidence.json")
    key_data = public_key.read_bytes()
    key = serialization.load_pem_public_key(key_data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("A trusted Ed25519 public key is required.")
    try:
        key.verify(signature.read_bytes(), signed)
    except InvalidSignature as error:
        raise ValueError("Release evidence signature verification failed.") from error
    if index.get("format_version") != 1 or index.get("sbom", {}).get("name") != "sbom.cdx.json":
        raise ValueError("Unsupported release evidence index.")
    document, scan_bytes = _read_json(scan)
    if {"sha256": hashlib.sha256(scan_bytes).hexdigest(), "bytes": len(scan_bytes)} != index[
        "scan"
    ]:
        raise ValueError("Retained scan differs from the signed index.")
    archive_digest, archive_size = _file_digest(archive)
    if {"sha256": archive_digest, "bytes": archive_size} != index["archive"]:
        raise ValueError("Retained archive differs from the signed index.")
    _, sbom = _read_json(bundle / "sbom.cdx.json")
    if hashlib.sha256(sbom).hexdigest() != index["sbom"]["sha256"]:
        raise ValueError("SBOM differs from the signed index.")
    if sbom != _json_bytes(_sbom(document, index["image_id"], index["source_sha"])):
        raise ValueError("SBOM is not the deterministic conversion of the signed inventory.")
    key_raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {
        "image_id": index["image_id"],
        "source_sha": index["source_sha"],
        "signature": "verified_ed25519",
        "trusted_public_key_sha256": hashlib.sha256(key_raw).hexdigest(),
        "qualification": "not_asserted",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Create an unsigned offline SBOM/evidence bundle.")
    verify = commands.add_parser("verify", help="Verify retained files and a detached signature.")
    for command in (export, verify):
        command.add_argument("--scan", type=Path, required=True)
        command.add_argument("--archive", type=Path, required=True)
    for name in ("scan-sha256", "archive-sha256", "image-id", "source-sha"):
        export.add_argument(f"--{name}", required=True)
    export.add_argument("--output", type=Path, required=True)
    for name in ("bundle", "signature", "public-key"):
        verify.add_argument(f"--{name}", type=Path, required=True)
    arguments = vars(parser.parse_args())
    operation = arguments.pop("command")
    try:
        result = (
            export_evidence(**arguments) if operation == "export" else verify_evidence(**arguments)
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.error(str(error))
    print(_json_bytes(result).decode(), end="")


if __name__ == "__main__":
    main()
