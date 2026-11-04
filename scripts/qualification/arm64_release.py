#!/usr/bin/env python3
"""Qualify and retain one exact ARM64 release on an isolated GitHub-hosted runner.

The container probes use installed application code and image-owned migrations.
All database writes stay in disposable tmpfs; no production mounts are accepted.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import platform
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

OUT = Path("output/arm64-release")
FROG_SHA = "441e3d03e41072a4a307ae90b136adf3828fc18a2353f64b038cef6308839e66"
SCANNER = "aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c"


def now():
    return datetime.now(UTC).isoformat()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def capture(*args):
    return subprocess.check_output(args, text=True).strip()


def hashes(base):
    return {
        str(path.relative_to(base)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix != ".pyc" and "__pycache__" not in path.parts
    }


def packaged(base):
    result = {
        f"{prefix}/{name}": digest
        for prefix in ("src", "migrations")
        for name, digest in hashes(base / prefix).items()
    }
    for name in ("alembic.ini", "pyproject.toml", "uv.lock", "README.md"):
        result[name] = hashlib.sha256((base / name).read_bytes()).hexdigest()
    return result


def preflight():
    source_sha = os.environ["SOURCE_SHA"]
    available = shutil.disk_usage(".").free
    memory_kib = int(Path("/proc/meminfo").read_text().splitlines()[0].split()[1])
    receipt = {
        "checked_at": now(),
        "source_sha": source_sha,
        "checkout_sha": capture("git", "rev-parse", "HEAD"),
        "source_tree": capture("git", "rev-parse", "HEAD^{tree}"),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "memory_kib": memory_kib,
        "disk_free_bytes": available,
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_environment": os.environ.get("RUNNER_ENVIRONMENT"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    save("runner.json", receipt)
    assert receipt["runner_environment"] == "github-hosted", receipt
    assert receipt["architecture"] == "aarch64", receipt
    assert receipt["checkout_sha"] == source_sha, receipt
    assert available >= 8 * 1024**3, "Less than 8 GiB available; stop without deleting host data"
    assert (os.cpu_count() or 0) >= 2 and memory_kib >= 8 * 1024**2, receipt
    assert os.environ["TRIVY_IMAGE"] == SCANNER


def in_image():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    import snaketracker

    package = Path(snaketracker.__file__).parent
    assert str(package).startswith("/app/.venv/"), package
    assert not os.environ.get("PYTHONPATH")
    assert os.getuid() == 1001
    assert platform.machine() == "aarch64"
    assert sqlite3.sqlite_version == "3.40.1", sqlite3.sqlite_version
    config = Config("/app/alembic.ini")
    config.set_main_option("script_location", "/app/migrations")
    script = ScriptDirectory.from_config(config)
    chain = ["0025_natural_history", "0026_amphibian_care_guides", "0027_bioactive_plant_care"]
    assert script.get_heads() == [chain[-1]]
    for previous, current in itertools.pairwise(chain):
        assert script.get_revision(current).down_revision == previous
    versions = {
        name: capture("dpkg-query", "-W", "-f=${Version}", name) for name in ("libssl3", "openssl")
    }
    for version in versions.values():
        subprocess.run(
            ["dpkg", "--compare-versions", version, "ge", "3.0.22-1~deb12u2"], check=True
        )
    qualification = Path("/qualification")
    frog = qualification / "reference/care-guides/reviewed-amphibians-v1.json"
    assert hashlib.sha256(frog.read_bytes()).hexdigest() == FROG_SHA
    with tempfile.TemporaryDirectory(prefix="arm64-release-") as temporary:
        root = Path(temporary)
        for name in ("alembic.ini", "migrations"):
            (root / name).symlink_to(Path("/app") / name)
        (root / "reference").symlink_to(qualification / "reference")
        for name, function in (
            ("x5", "check_x5_upgrade"),
            ("bioactive", "check_bioactive_upgrade"),
        ):
            check = runpy.run_path(
                qualification / f"tests/integration/test_{name}_migration_runtime.py"
            )
            check[function](root / f"{name}.sqlite3", root=root)
    print(
        json.dumps(
            {
                "package_path": str(package),
                "uid": os.getuid(),
                "architecture": platform.machine(),
                "sqlite_version": sqlite3.sqlite_version,
                "trusted_schema": 0,
                "openssl": versions,
                "migration_chain": chain,
                "migration_checks": ["check_x5_upgrade", "check_bioactive_upgrade"],
                "frog_bundle_sha256": FROG_SHA,
                "packaged": packaged(Path("/app")),
                "installed": hashes(package),
            }
        )
    )


def qualify():
    source_sha = os.environ["SOURCE_SHA"]
    image = json.loads(capture("docker", "image", "inspect", f"snaketracker:release-{source_sha}"))[
        0
    ]
    image_id = image["Id"]
    (OUT / "image.id").write_text(image_id + "\n")
    save("image-inspect.json", image)
    assert image["Architecture"] == "arm64" and image["Os"] == "linux"
    assert image["Config"]["Labels"]["org.opencontainers.image.revision"] == source_sha
    assert f"SNAKETRACKER_BUILD_GIT_SHA={source_sha}" in image["Config"]["Env"]
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
        "--mount",
        f"type=bind,source={Path.cwd()},target=/qualification,readonly",
        "--entrypoint",
        "python",
        image_id,
        "/qualification/scripts/qualification/arm64_release.py",
        "in-image",
    ]
    completed = subprocess.run(args, text=True, capture_output=True, check=False)
    (OUT / "runtime.log").write_text(completed.stdout + completed.stderr)
    completed.check_returncode()
    runtime = json.loads(completed.stdout)
    assert runtime["packaged"] == packaged(Path.cwd()), "Packaged file set or bytes differ"
    assert runtime["installed"] == hashes(Path("src/snaketracker")), "Installed source differs"
    save(
        "image-identity.json",
        {
            "status": "passed",
            "checked_at": now(),
            "source_sha": source_sha,
            "image_id": image_id,
            "registry_digests": image["RepoDigests"],
            "runtime": runtime,
            "bidirectional_file_set_and_hash_equality": True,
            "application_from_installed_package": True,
            "migrations_from_actual_image": True,
            "production_volume_mounted": False,
        },
    )


def scan():
    image_id = (OUT / "image.id").read_text().strip()
    cache = Path(os.environ["RUNNER_TEMP"]) / "arm64-trivy-cache"
    cache.mkdir()
    scanner_args = [
        "docker",
        "run",
        "--rm",
        "--cpus",
        "2",
        "--memory",
        "4g",
        "--mount",
        f"type=bind,source={cache},target=/cache",
    ]
    subprocess.run(["docker", "pull", "--platform", "linux/arm64", SCANNER], check=True)
    scanner = json.loads(capture("docker", "image", "inspect", SCANNER))[0]
    assert scanner["Architecture"] == "arm64"
    version = capture(*scanner_args, SCANNER, "--version")
    assert "Version: 0.76.1" in version, version
    save(
        "scanner-identity.json",
        {"reference": SCANNER, "image_id": scanner["Id"], "version": version},
    )
    receipt = {
        "status": "failed",
        "started_at": now(),
        "image_id": image_id,
        "source_sha": os.environ["SOURCE_SHA"],
        "scanner": SCANNER,
        "policy": "fixed HIGH/CRITICAL",
        "advisory_suppressions": [],
    }
    try:
        with (OUT / "scanner-db.log").open("w") as log:
            subprocess.run(
                [
                    *scanner_args,
                    SCANNER,
                    "image",
                    "--cache-dir",
                    "/cache",
                    "--timeout",
                    "10m",
                    "--no-progress",
                    "--db-repository",
                    "ghcr.io/aquasecurity/trivy-db:2",
                    "--download-db-only",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=660,
            )
        database = json.loads((cache / "db/metadata.json").read_text())
        save("scanner-db-metadata.json", database)
        expires = datetime.fromisoformat(database["NextUpdate"].replace("Z", "+00:00"))
        assert expires > datetime.now(UTC), "Downloaded Trivy database is already expired"
        receipt["database_metadata"] = database
        with (OUT / "arm64-scan.log").open("w") as log:
            completed = subprocess.run(
                [
                    *scanner_args,
                    "--network",
                    "none",
                    "--mount",
                    "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock,readonly",
                    "--mount",
                    f"type=bind,source={OUT.resolve()},target=/evidence",
                    SCANNER,
                    "image",
                    "--timeout",
                    "10m",
                    "--cache-dir",
                    "/cache",
                    "--skip-db-update",
                    "--no-progress",
                    "--image-src",
                    "docker",
                    "--scanners",
                    "vuln",
                    "--severity",
                    "HIGH,CRITICAL",
                    "--ignore-unfixed",
                    "--ignorefile",
                    "/dev/null",
                    "--exit-code",
                    "1",
                    "--format",
                    "json",
                    "--output",
                    "/evidence/arm64-scan.json",
                    image_id,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=660,
            )
        receipt["exit_code"] = completed.returncode
        report = json.loads((OUT / "arm64-scan.json").read_text())
        assert report["Metadata"]["ImageID"] == image_id
        assert report["Metadata"]["OS"]["Family"] == "debian"
        assert any(result.get("Type") == "python-pkg" for result in report["Results"]), (
            "Trivy did not report the installed Python packages"
        )
        blockers = [
            v for result in report.get("Results", []) for v in result.get("Vulnerabilities", [])
        ]
        receipt["fixed_high_critical_findings"] = blockers
        completed.check_returncode()
        assert not blockers, "Vulnerability gate failed"
        assert expires > datetime.now(UTC), "Trivy database expired during the scan"
        receipt["status"] = "passed"
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        receipt["checked_at"] = now()
        save("arm64-scan-receipt.json", receipt)


def archive():
    image_id = (OUT / "image.id").read_text().strip()
    directory = Path("output/arm64-image")
    archive_path = directory / "image.tar.gz"
    with tarfile.open(archive_path, "r:gz") as saved:
        manifest = json.load(saved.extractfile("manifest.json"))
        assert len(manifest) == 1
        config = saved.extractfile(manifest[0]["Config"]).read()
        assert "sha256:" + hashlib.sha256(config).hexdigest() == image_id
    with archive_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    receipt = {
        "status": "passed",
        "source_sha": os.environ["SOURCE_SHA"],
        "image_id": image_id,
        "archive_sha256": digest,
        "archive_bytes": archive_path.stat().st_size,
        "digest_kind": "Docker image configuration digest; no registry publication",
        "checked_at": now(),
    }
    save("archive-receipt.json", receipt)
    (directory / "SHA256SUMS").write_text(f"{digest}  image.tar.gz\n")
    shutil.copyfile(OUT / "archive-receipt.json", directory / "archive-receipt.json")


if __name__ == "__main__":
    {
        "preflight": preflight,
        "in-image": in_image,
        "qualify": qualify,
        "scan": scan,
        "archive": archive,
    }[sys.argv[1]]()
