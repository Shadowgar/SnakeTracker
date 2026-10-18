"""Explicit operator publication after a separately verified deployment or rollback."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from snaketracker.presentation.updates import MAX_RELEASE_BYTES, _verified_release


def _prepared(ledger: Path, entry: dict[str, Any]) -> tuple[bytes, int]:
    try:
        with ledger.open("rb") as handle:
            existing = handle.read(MAX_RELEASE_BYTES + 1)
        if len(existing) > MAX_RELEASE_BYTES:
            raise ValueError("Release history exceeds the size limit; preserve it for review.")
        records = json.loads(existing.decode("utf-8"))
    except FileNotFoundError:
        records = []
    if not isinstance(records, list) or len(records) >= 200:
        raise ValueError("Release history must be an array with space for another record.")
    records = [*records, entry]
    instants: set[datetime] = set()
    for item in records:
        validated = _verified_release(item)
        if validated is None:
            raise ValueError("Every release must be verified and have valid notes and provenance.")
        instant = datetime.fromisoformat(validated["deployed_at"])
        if instant > datetime.now(UTC) or instant in instants:
            raise ValueError("Deployment timestamps must be past, distinct, actual instants.")
        instants.add(instant)
    contents = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(contents) > MAX_RELEASE_BYTES:
        raise ValueError("Updated release history exceeds the size limit; nothing was replaced.")
    return contents, len(records)


def record_release(ledger: Path, entry: dict[str, Any], *, apply: bool = False) -> int:
    """Append atomically on the persistent volume; never deploy or access a database."""
    if not ledger.is_absolute() or not ledger.parent.is_dir():
        raise ValueError("An absolute ledger path in an existing persistent directory is required.")
    if not apply:
        return _prepared(ledger, entry)[1]
    lock_path = ledger.with_name(ledger.name + ".lock")
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        contents, count = _prepared(ledger, entry)
        pending: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=ledger.parent, prefix=".release-", delete=False
            ) as file:
                pending = Path(file.name)
                file.write(contents)
                file.flush()
                os.fsync(file.fileno())
            os.replace(pending, ledger)
            descriptor = os.open(ledger.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, help="Plain-English notes for one verified deployment")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Append after deployment verification")
    args = parser.parse_args()
    try:
        with args.record.open("rb") as handle:
            contents = handle.read(MAX_RELEASE_BYTES + 1)
        if len(contents) > MAX_RELEASE_BYTES:
            raise ValueError("Release record exceeds the size limit.")
        count = record_release(args.ledger, json.loads(contents.decode("utf-8")), apply=args.apply)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"{'Recorded' if args.apply else 'Validated'} release history: {count} entries.")


if __name__ == "__main__":
    main()
