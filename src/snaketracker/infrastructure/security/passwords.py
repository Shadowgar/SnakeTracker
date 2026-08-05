"""Argon2id password hashing adapter."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type


class Argon2PasswordHasher:
    """Established-library Argon2id hashing with versioned encoded parameters."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher(type=Type.ID)

    @classmethod
    def for_testing(cls) -> Argon2PasswordHasher:
        return cls(
            PasswordHasher(
                time_cost=1,
                memory_cost=8192,
                parallelism=1,
                hash_len=32,
                salt_len=16,
                type=Type.ID,
            )
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except VerificationError:
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)
