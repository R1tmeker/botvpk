from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TotpSecretError(ValueError):
    pass


def _key(value: str | None) -> bytes:
    if not value or len(value) < 32:
        raise TotpSecretError("TOTP_ENCRYPTION_KEY must contain at least 32 characters.")
    return hashlib.sha256(value.encode("utf-8")).digest()


def encrypt_totp_secret(secret: str, encryption_key: str | None) -> str:
    nonce = os.urandom(12)
    encrypted = AESGCM(_key(encryption_key)).encrypt(nonce, secret.encode("utf-8"), b"botvpk-totp-v1")
    return "v1:" + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_totp_secret(value: str, encryption_key: str | None) -> str:
    if not value.startswith("v1:"):
        raise TotpSecretError("Unsupported encrypted TOTP secret version.")
    try:
        payload = base64.urlsafe_b64decode(value[3:].encode("ascii"))
        plain = AESGCM(_key(encryption_key)).decrypt(payload[:12], payload[12:], b"botvpk-totp-v1")
        return plain.decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - corrupted ciphertext must fail closed
        raise TotpSecretError("Unable to decrypt TOTP secret.") from exc
