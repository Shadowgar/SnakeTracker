"""Actual pre-D release must refuse both startup entrypoints without writing schema 27."""

import io
import os
import subprocess
import sys
import tarfile

import pytest

from tests.integration.test_bioactive_migration_runtime import (
    PREVIOUS,
    ROOT,
    check_bioactive_upgrade,
)


@pytest.mark.timeout(120)
def test_actual_prior_binary_rejects_schema_without_mutable_startup(tmp_path):
    database = tmp_path / "older-rejection.sqlite3"
    check_bioactive_upgrade(database)
    archive = subprocess.check_output(["git", "archive", "--format=tar", PREVIOUS], cwd=ROOT)
    release_root = tmp_path / "pre-bioactive"
    release_root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as archived:
        archived.extractall(release_root, filter="data")
    probe = (ROOT / "tests/fixtures/x4/previous_release_probe.py").read_text()
    probe = probe.replace('"event_contract_unknown"', '"relational_schema_unknown"')
    probe = probe.replace('    assert "animal.registered v3" in report.operator_detail\n', "")
    (tmp_path / "probe.py").write_text(probe)
    before = database.read_bytes()
    for entrypoint in ("web", "worker"):
        result = subprocess.run(
            [
                sys.executable,
                str(tmp_path / "probe.py"),
                str(release_root),
                str(database),
                entrypoint,
            ],
            cwd=release_root,
            env=os.environ | {"PYTHONPATH": str(release_root / "src")},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"restricted_recovery": true' in result.stdout
        assert database.read_bytes() == before
