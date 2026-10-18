"""Human-readable Care Keeper development history and confirmed deployment notes.

GitHub merges are not deployments. Only verified operator release records appear
under 'On this website'. Reading this page never changes household data.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

HISTORY_FILE = Path(__file__).with_name("updates_history.json")
MAX_RELEASE_BYTES = 128 * 1024
_ALLOWED_KINDS = frozenset({"New", "Improved", "Fixed"})
_ALLOWED_STATUSES = frozenset({"deployed", "rolled_back"})
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,39}$")


def development_history() -> dict[str, Any]:
    """Read bundled, source-audited milestones (not a deployment log)."""
    with HISTORY_FILE.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def _verified_release(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict) or entry.get("verified") is not True:
        return None
    version = entry.get("version")
    title = entry.get("title")
    description = entry.get("description")
    timestamp = entry.get("deployed_at")
    build_sha = entry.get("build_sha")
    status = entry.get("status")
    if (
        not isinstance(version, str)
        or not _VERSION_PATTERN.fullmatch(version)
        or not isinstance(title, str)
        or not 1 <= len(title.strip()) <= 100
        or not isinstance(description, str)
        or not 1 <= len(description.strip()) <= 280
        or not isinstance(timestamp, str)
        or not isinstance(build_sha, str)
        or not _SHA_PATTERN.fullmatch(build_sha)
        or not isinstance(status, str)
        or status not in _ALLOWED_STATUSES
    ):
        return None
    try:
        instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        return None
    changes = entry.get("changes")
    if not isinstance(changes, list) or not 1 <= len(changes) <= 8:
        return None
    clean_changes: list[dict[str, str]] = []
    for change in changes:
        if not isinstance(change, dict):
            return None
        kind = change.get("kind")
        wording = change.get("text")
        if (
            not isinstance(kind, str)
            or kind not in _ALLOWED_KINDS
            or not isinstance(wording, str)
            or not 1 <= len(wording.strip()) <= 200
        ):
            return None
        clean_changes.append({"kind": kind, "text": wording.strip()})
    return {
        "version": version,
        "title": title.strip(),
        "description": description.strip(),
        "deployed_at": instant.isoformat(),
        "date_label": instant.strftime("%B %-d, %Y"),
        "status": status,
        "changes": clean_changes,
    }


def confirmed_production_updates(path: Path | None) -> tuple[dict[str, Any], ...]:
    """Read only compact, operator-verified records from persistent storage."""
    if path is None:
        return ()
    try:
        if path.stat().st_size > MAX_RELEASE_BYTES:
            return ()
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return ()
    if not isinstance(data, list) or len(data) > 200:
        return ()
    releases = [record for item in data if (record := _verified_release(item)) is not None]
    releases.sort(key=lambda item: item["deployed_at"], reverse=True)
    return tuple(releases)
