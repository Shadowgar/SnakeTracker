"""Retained compatibility declarations must identify the actual qualified build."""

import json

import pytest

from scripts.qualification import arm64_release
from snaketracker.operations.release_compatibility import export_release_compatibility

SOURCE_SHA = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


def test_retained_manifest_binds_installed_build_to_qualified_image(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAKETRACKER_BUILD_GIT_SHA", SOURCE_SHA)
    monkeypatch.setattr(arm64_release, "OUT", tmp_path)
    manifest = json.loads(export_release_compatibility(require_build_identity=True))
    arm64_release.retain_compatibility(manifest, source_sha=SOURCE_SHA, image_id=IMAGE_ID)
    retained = json.loads((tmp_path / "release-compatibility.json").read_text())
    assert retained["source_sha"] == SOURCE_SHA
    assert retained["image_id"] == IMAGE_ID
    assert retained["manifest"]["application"]["build_git_sha"] == SOURCE_SHA
    assert retained["manifest"]["relational_schema"]["mutable_versions"] == [27]
    assert retained["manifest"]["qualification"]["status"] == "not_asserted"


@pytest.mark.parametrize("build_sha", [None, "c" * 40])
def test_missing_or_different_build_never_becomes_release_evidence(
    tmp_path, monkeypatch, build_sha
):
    monkeypatch.setattr(arm64_release, "OUT", tmp_path)
    monkeypatch.delenv("SNAKETRACKER_BUILD_GIT_SHA", raising=False)
    if build_sha is not None:
        monkeypatch.setenv("SNAKETRACKER_BUILD_GIT_SHA", build_sha)
    manifest = json.loads(export_release_compatibility())
    with pytest.raises(AssertionError, match="build identity"):
        arm64_release.retain_compatibility(manifest, source_sha=SOURCE_SHA, image_id=IMAGE_ID)
    assert list(tmp_path.iterdir()) == []
