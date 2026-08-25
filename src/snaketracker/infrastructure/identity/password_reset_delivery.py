"""Explicit identity-message delivery adapters for password recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path

from snaketracker.application.identity import PasswordResetMessage


class LocalFilePasswordResetDelivery:
    """Capture one reset message as an operator-readable development/test artifact."""

    def __init__(self, directory: Path, *, environment: str) -> None:
        if environment not in {"development", "test"}:
            raise ValueError("Local password-reset delivery is restricted to development and test.")
        self._directory = directory

    def deliver(self, message: PasswordResetMessage) -> None:
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)
        destination = self._directory / f"password-reset-{message.message_id}.json"
        payload = json.dumps(
            {
                "message_id": str(message.message_id),
                "recipient_email": message.recipient_email,
                "expires_at": message.expires_at.isoformat(),
                "reset_url": message.reset_url,
            },
            sort_keys=True,
        )
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.write("\n")
        except Exception:
            destination.unlink(missing_ok=True)
            raise
