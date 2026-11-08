"""Offline inventory conversion and signed artifact verification fail closed."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from snaketracker.operations import release_evidence
from snaketracker.operations.release_evidence import export_evidence, verify_evidence

SOURCE = "a" * 40
IMAGE = "sha256:" + "b" * 64


@pytest.fixture
def inputs(tmp_path):
    scan = tmp_path / "scan.json"
    scan.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "ArtifactType": "container_image",
                "Metadata": {
                    "ImageID": IMAGE,
                    "ImageConfig": {
                        "config": {"Labels": {"org.opencontainers.image.revision": SOURCE}}
                    },
                },
                "Results": [
                    {
                        "Target": "Python",
                        "Type": "python-pkg",
                        "Packages": [
                            {
                                "Name": "demo",
                                "Version": "1.2.3",
                                "Identifier": {"PURL": "pkg:pypi/demo@1.2.3"},
                                "Licenses": ["MIT"],
                            }
                        ],
                    },
                    {
                        "Target": "usr/bin/tool",
                        "Type": "rustbinary",
                        "Packages": [{"Name": "demo", "Version": "1.2.3"}],
                    },
                ],
            }
        )
    )
    archive = tmp_path / "image.tar.gz"
    archive.write_bytes(b"fictional image archive; no Docker access")
    return scan, archive


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(inputs, output, **overrides):
    scan, archive = inputs
    arguments = {
        "scan": scan,
        "scan_sha256": digest(scan),
        "archive": archive,
        "archive_sha256": digest(archive),
        "image_id": IMAGE,
        "source_sha": SOURCE,
        "output": output,
    }
    arguments.update(overrides)
    return export_evidence(**arguments)


def sign(bundle, tmp_path, key=None):
    key = key or Ed25519PrivateKey.generate()
    signature = tmp_path / "signature.ed25519"
    signature.write_bytes(key.sign((bundle / "release-evidence.json").read_bytes()))
    public_key = tmp_path / "trusted-public.pem"
    public_key.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return signature, public_key


def verify(inputs, bundle, signature, public_key):
    return verify_evidence(
        bundle=bundle,
        scan=inputs[0],
        archive=inputs[1],
        signature=signature,
        public_key=public_key,
    )


def test_export_is_deterministic_and_keeps_package_occurrences_without_claiming_qualification(
    inputs, tmp_path
):
    first, second = tmp_path / "one", tmp_path / "two"
    original = [p.read_bytes() for p in inputs]
    export(inputs, first)
    export(inputs, second)
    assert sorted(p.name for p in first.iterdir()) == ["release-evidence.json", "sbom.cdx.json"]
    assert (first / "sbom.cdx.json").read_bytes() == (second / "sbom.cdx.json").read_bytes()
    assert (first / "release-evidence.json").read_bytes() == (
        second / "release-evidence.json"
    ).read_bytes()
    sbom = json.loads((first / "sbom.cdx.json").read_text())
    assert sbom["bomFormat"] == "CycloneDX" and sbom["specVersion"] == "1.6"
    assert len(sbom["components"]) == 2
    assert len({item["bom-ref"] for item in sbom["components"]}) == 2
    assert sbom["compositions"][0]["aggregate"] == "unknown"
    assert "dependencies" not in sbom
    index = json.loads((first / "release-evidence.json").read_text())
    assert index["qualification"] == "not_asserted"
    assert index["signature"] == "not_supplied"
    assert index["archive"]["sha256"] == digest(inputs[1])
    assert original == [p.read_bytes() for p in inputs]


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"image_id": "sha256:" + "c" * 64}, "image"),
        ({"source_sha": "c" * 40}, "source"),
        ({"scan_sha256": "0" * 64}, "scan"),
        ({"archive_sha256": "0" * 64}, "archive"),
    ],
)
def test_mismatched_pinned_inputs_create_no_output(inputs, tmp_path, overrides, match):
    output = tmp_path / "output"
    with pytest.raises(ValueError, match=match):
        export(inputs, output, **overrides)
    assert not output.exists()


def test_export_refuses_existing_output_and_incomplete_package_inventory(inputs, tmp_path):
    output = tmp_path / "keep"
    output.mkdir()
    marker = output / "keeper.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        export(inputs, output)
    assert marker.read_text() == "preserve"
    scan = json.loads(inputs[0].read_text())
    scan["Results"][0]["Packages"][0].pop("Version")
    inputs[0].write_text(json.dumps(scan))
    with pytest.raises(ValueError, match="package"):
        export(inputs, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_signature_verifies_exact_index_sbom_scan_and_archive(inputs, tmp_path):
    bundle = tmp_path / "bundle"
    export(inputs, bundle)
    signature, key = sign(bundle, tmp_path)
    result = verify(inputs, bundle, signature, key)
    assert result["signature"] == "verified_ed25519"
    assert result["qualification"] == "not_asserted"
    assert result["image_id"] == IMAGE
    assert result["source_sha"] == SOURCE


@pytest.mark.parametrize("target", ["index", "sbom", "scan", "archive", "key", "signature"])
def test_tampering_and_wrong_trusted_key_are_rejected(inputs, tmp_path, target):
    bundle = tmp_path / "bundle"
    export(inputs, bundle)
    signature, key = sign(bundle, tmp_path)
    if target == "key":
        key.write_bytes(
            Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
    else:
        paths = {
            "index": bundle / "release-evidence.json",
            "sbom": bundle / "sbom.cdx.json",
            "scan": inputs[0],
            "archive": inputs[1],
            "signature": signature,
        }
        path = paths[target]
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        verify(inputs, bundle, signature, key)


def test_unsigned_bundle_cannot_be_reported_verified(inputs, tmp_path):
    bundle = tmp_path / "bundle"
    export(inputs, bundle)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "snaketracker.operations.release_evidence",
            "verify",
            "--bundle",
            str(bundle),
            "--scan",
            str(inputs[0]),
            "--archive",
            str(inputs[1]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "--signature" in result.stderr and "--public-key" in result.stderr
    assert not result.stdout


def test_an_unapproved_signature_algorithm_is_rejected(inputs, tmp_path):
    bundle = tmp_path / "bundle"
    export(inputs, bundle)
    signature, key = sign(bundle, tmp_path)
    key.write_bytes(
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    with pytest.raises(ValueError, match="Ed25519"):
        verify(inputs, bundle, signature, key)


@pytest.mark.parametrize(
    "change",
    [
        lambda scan: scan.update(SchemaVersion=1),
        lambda scan: scan.update(Results=[]),
        lambda scan: scan["Results"][0].update(Packages=[]),
        lambda scan: scan["Results"][0].update(Target="unsafe\nname"),
        lambda scan: scan["Results"][0]["Packages"][0].update(Name=""),
        lambda scan: scan["Results"][0]["Packages"][0].update(Licenses="not a list"),
        lambda scan: scan["Results"][0]["Packages"][0].update(Identifier={"PURL": "bad"}),
    ],
)
def test_malformed_inventory_is_not_silently_converted(inputs, tmp_path, change):
    document = json.loads(inputs[0].read_text())
    change(document)
    inputs[0].write_text(json.dumps(document))
    with pytest.raises(ValueError):
        export(inputs, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("document", ['{"Results":[],"Results":[]}', "[]"])
def test_ambiguous_or_nonobject_json_is_rejected(inputs, tmp_path, document):
    inputs[0].write_text(document)
    with pytest.raises(ValueError):
        export(inputs, tmp_path / "output")


def test_bounded_json_read_and_strict_digest_syntax(inputs, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="digest"):
        export(inputs, tmp_path / "output", source_sha="HEAD")
    with pytest.raises(ValueError, match="image"):
        export(inputs, tmp_path / "output", image_id="latest")
    monkeypatch.setattr(release_evidence, "MAX_JSON_BYTES", 16)
    with pytest.raises(ValueError, match="input limit"):
        export(inputs, tmp_path / "output")


def test_expanded_sbom_is_rejected_before_creating_output(inputs, tmp_path, monkeypatch):
    document = json.loads(inputs[0].read_text())
    document["Results"] = [
        {
            "Target": "é" * 600,
            "Type": "python-pkg",
            "Packages": [{"Name": f"package-{n}", "Version": "1"} for n in range(8)],
        }
    ]
    inputs[0].write_text(json.dumps(document, ensure_ascii=False))
    originals = [path.read_bytes() for path in inputs]
    assert len(originals[0]) < 4096
    monkeypatch.setattr(release_evidence, "MAX_JSON_BYTES", 4096)

    output = tmp_path / "output"
    with pytest.raises(ValueError, match="JSON evidence exceeds"):
        export(inputs, output)

    assert not output.exists()
    assert originals == [path.read_bytes() for path in inputs]


def test_export_at_json_size_limit_remains_verifiable(inputs, tmp_path, monkeypatch):
    reference = tmp_path / "reference"
    export(inputs, reference)
    byte_limit = max(
        inputs[0].stat().st_size,
        (reference / "sbom.cdx.json").stat().st_size,
        (reference / "release-evidence.json").stat().st_size,
    )
    monkeypatch.setattr(release_evidence, "MAX_JSON_BYTES", byte_limit)

    bundle = tmp_path / "bundle"
    export(inputs, bundle)
    signature, key = sign(bundle, tmp_path)
    assert verify(inputs, bundle, signature, key)["signature"] == "verified_ed25519"


def test_conflicting_duplicate_package_metadata_is_rejected(inputs, tmp_path):
    document = json.loads(inputs[0].read_text())
    package = document["Results"][0]["Packages"][0]
    document["Results"][0]["Packages"].append({**package, "Licenses": ["different"]})
    inputs[0].write_text(json.dumps(document))
    with pytest.raises(ValueError, match="Conflicting"):
        export(inputs, tmp_path / "output")


def test_signed_but_inconsistent_sbom_is_rejected(inputs, tmp_path):
    bundle = tmp_path / "bundle"
    export(inputs, bundle)
    sbom_path = bundle / "sbom.cdx.json"
    sbom = json.loads(sbom_path.read_text())
    sbom["components"][0]["name"] = "unobserved-package"
    sbom_path.write_text(json.dumps(sbom))
    index_path = bundle / "release-evidence.json"
    index = json.loads(index_path.read_text())
    index["sbom"]["sha256"] = digest(sbom_path)
    index_path.write_text(json.dumps(index))
    signature, key = sign(bundle, tmp_path)
    with pytest.raises(ValueError, match="conversion"):
        verify(inputs, bundle, signature, key)
    index["sbom"]["name"] = "../outside.json"
    index_path.write_text(json.dumps(index))
    signature, key = sign(bundle, tmp_path)
    with pytest.raises(ValueError, match="index"):
        verify(inputs, bundle, signature, key)


def test_cli_exports_and_verifies_without_mutating_source_files(
    inputs, tmp_path, monkeypatch, capsys
):
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_evidence",
            "export",
            "--scan",
            str(inputs[0]),
            "--scan-sha256",
            digest(inputs[0]),
            "--archive",
            str(inputs[1]),
            "--archive-sha256",
            digest(inputs[1]),
            "--image-id",
            IMAGE,
            "--source-sha",
            SOURCE,
            "--output",
            str(bundle),
        ],
    )
    release_evidence.main()
    assert json.loads(capsys.readouterr().out)["signature"] == "not_supplied"
    signature, key = sign(bundle, tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_evidence",
            "verify",
            "--scan",
            str(inputs[0]),
            "--archive",
            str(inputs[1]),
            "--bundle",
            str(bundle),
            "--signature",
            str(signature),
            "--public-key",
            str(key),
        ],
    )
    release_evidence.main()
    assert json.loads(capsys.readouterr().out)["signature"] == "verified_ed25519"
    inputs[1].write_bytes(b"tampered")
    with pytest.raises(SystemExit) as result:
        release_evidence.main()
    assert result.value.code == 2
    assert "archive differs" in capsys.readouterr().err
