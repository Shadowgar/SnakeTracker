"""Disposable, loopback-only M9 browser fixture; never accepts an existing database."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import uvicorn

from tests.browser.test_multispecies_workflow import _register, _setup
from tests.browser.test_public_sharing import sharing_client

ROOT = Path(__file__).parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8163)
    arguments = parser.parse_args()
    target = arguments.data_dir.resolve()
    if target.parent != Path("/tmp") or not target.name.startswith("carekeeper-m9-browser-"):
        parser.error("Use a fresh /tmp/carekeeper-m9-browser-* directory")
    if not 8150 <= arguments.port <= 8199:
        parser.error("Use a dedicated loopback qualification port from 8150 to 8199")
    target.mkdir(mode=0o700, exist_ok=True)
    if any(target.iterdir()):
        parser.error("Fixture directory must be empty; existing data is never reset")
    os.chmod(target, 0o700)
    with sharing_client(target) as client:
        _setup(client)
        animals = {
            "main": _register(client, "Fictional Ember", "snake", "Python regius"),
            "missing": _register(client, "Fictional Moss", "lizard", "Pogona vitticeps"),
            "long": _register(client, "Fictional Long Name", "snake", "Python regius"),
        }
        app = client.app
    manifest = {
        "fictional": True,
        "origin": f"http://127.0.0.1:{arguments.port}",
        "database": str(target / "sharing.sqlite3"),
        "source_checkout": str(ROOT),
        "base_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "qualification_includes_working_tree": True,
        "animals": animals,
        "email": "owner@example.com",
        "password": "correct horse battery staple",
        "image": str(ROOT / "src/snaketracker/presentation/static/animal-fallbacks/snake.webp"),
        "image_scope": "Existing group illustration used only as fictional uploaded media",
        "production_data_used": False,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(target / "manifest.json", 0o600)
    uvicorn.run(app, host="127.0.0.1", port=arguments.port, workers=1, proxy_headers=False)


if __name__ == "__main__":
    main()
