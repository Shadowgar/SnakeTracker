"""Retained compatibility declarations must identify the actual qualified build."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from snaketracker.operations.release_compatibility import export_release_compatibility

ROOT = Path(__file__).parents[3]
MODULE_PATH = ROOT / "scripts/qualification/arm64_release.py"
SPEC = importlib.util.spec_from_file_location("arm64_release", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
arm64_release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = arm64_release
SPEC.loader.exec_module(arm64_release)

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
