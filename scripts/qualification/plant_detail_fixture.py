#!/usr/bin/env python3
"""Serve real Plant Detail templates with synthetic state and a local reference photo.

No database, production settings, authentication credentials or provider fetches.
The image/provenance inputs must be a locally retained qualified reference asset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
PRESENTATION = ROOT / "src/snaketracker/presentation"
ENCLOSURE = "00000000-0000-4000-8000-000000000001"
PLANT = "00000000-0000-4000-8000-000000000002"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    fixture = ROOT / "tests/fixtures/reference-images"
    parser.add_argument("--image", type=Path, default=fixture / "swiss-cheese-plant.webp")
    parser.add_argument("--provenance", type=Path, default=fixture / "swiss-cheese-plant.json")
    parser.add_argument("--port", type=int, default=8193)
    args = parser.parse_args()
    image = args.image.resolve().read_bytes()
    provenance = json.loads(args.provenance.read_text())
    if hashlib.sha256(image).hexdigest() != provenance["local_sha256"]:
        parser.error("Reference image does not match its retained provenance checksum")
    env = Environment(
        loader=FileSystemLoader(PRESENTATION / "templates"),
        autoescape=select_autoescape(),
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/health":
                content, media = b"fictional plant layout fixture", "text/plain"
            elif path.startswith("/static/"):
                target = (PRESENTATION / path.lstrip("/")).resolve()
                if not target.is_relative_to(PRESENTATION / "static") or not target.is_file():
                    self.send_error(404)
                    return
                content = target.read_bytes()
                media = {
                    ".css": "text/css",
                    ".js": "text/javascript",
                    ".svg": "image/svg+xml",
                    ".webmanifest": "application/manifest+json",
                }.get(target.suffix, "application/octet-stream")
            elif path.startswith("/directory/reference-images/"):
                content, media = image, "image/webp"
            elif path in {"/plant/reference", "/plant/long-name", "/plant/missing-image"}:
                label = "Swiss Cheese Plant"
                if path.endswith("long-name"):
                    label = "CanopyMonstera" * 12 + " — beside the humid hide"
                taxon = SimpleNamespace(
                    taxon_id=provenance["taxon_id"],
                    display_name="Swiss Cheese Plant",
                    image_creator=provenance["creator"],
                    image_license_url=provenance["license_url"],
                    image_license_code=provenance["license_code"],
                    image_source_page_url=provenance["source_page_url"],
                    source_url=provenance["source_url"],
                    image_provider=provenance["provider"],
                    provider=provenance["provider"],
                )
                plant = SimpleNamespace(
                    label=label,
                    species_display="Swiss Cheese Plant",
                    confirmed_scientific_name="Monstera deliciosa",
                    confirmed_common_name="Swiss Cheese Plant",
                    status="active",
                    quantity=1,
                    date_added=date(2026, 11, 1),
                    taxon_id=taxon.taxon_id,
                    enclosure_plant_id=PLANT,
                    notes="Established beside the cork hide; check the substrate before watering.",
                )
                context = {
                    "plant": plant,
                    "enclosure": SimpleNamespace(enclosure_id=ENCLOSURE, name="Canopy habitat"),
                    "reference_taxon": None if path.endswith("missing-image") else taxon,
                    "care_guide_available": False,
                    "watering_rule": SimpleNamespace(enabled=True, interval_days=7),
                    "watering_due": SimpleNamespace(due_at=datetime(2026, 11, 9, 14, tzinfo=UTC)),
                    "watering_history": [
                        SimpleNamespace(
                            occurred_at=datetime(2026, 11, 2, 14, tzinfo=UTC),
                            notes="Substrate checked and watered.",
                        )
                    ],
                    "household_zone": UTC,
                    "principal": SimpleNamespace(
                        display_name="Fixture Keeper",
                        household_name="Fictional layout household",
                        household_timezone="UTC",
                        capabilities={"inventory.view", "expense.view"},
                    ),
                    "request": SimpleNamespace(url=SimpleNamespace(path=path), query_params={}),
                    "csrf_token": "fictional-nonfunctional-csrf",
                    "command_id": "fictional-layout-only",
                    "current_year": 2026,
                }
                content = env.get_template("enclosure_plant_detail.html").render(context).encode()
                media = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", media)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args: object) -> None:
            return

    print(f"Fictional rendered-template fixture: http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
