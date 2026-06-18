from __future__ import annotations

from functools import lru_cache

from pwdlib import PasswordHash


@lru_cache
def _hasher() -> PasswordHash:
    # PasswordHash.recommended() uses Argon2 with sensible parameters.
    return PasswordHash.recommended()


def hash_password(raw_password: str) -> str:
    return _hasher().hash(raw_password)


def verify_password(raw_password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher().verify(raw_password, password_hash)
    except Exception:  # noqa: BLE001 - malformed/legacy hash should fail closed
        return False
