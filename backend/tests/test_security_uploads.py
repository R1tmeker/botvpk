from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.auth_security import PasswordPolicyError, validate_password_policy
from app.services.uploads import IMAGE_MIME_TYPES, UploadValidationError, detect_mime_type, prepare_upload


def test_password_policy_rejects_numeric_password() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("12345678", telegram_id=12345678)


def test_password_policy_accepts_letters_and_digits() -> None:
    validate_password_policy("Zvezda2026", telegram_id=12345678)


def test_detect_mime_type_uses_magic_bytes_not_filename() -> None:
    assert detect_mime_type(b"%PDF-1.7\nbody") == "application/pdf"
    assert detect_mime_type(b"not an image") is None


def test_prepare_upload_rejects_disguised_image() -> None:
    with pytest.raises(UploadValidationError):
        prepare_upload(
            b"console.log('not really a jpg')",
            max_size_bytes=1024,
            allowed_mime_types=IMAGE_MIME_TYPES,
        )


def test_prepare_upload_reencodes_valid_png() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(255, 0, 0)).save(buffer, format="PNG")

    prepared = prepare_upload(
        buffer.getvalue(),
        max_size_bytes=1024 * 1024,
        allowed_mime_types=IMAGE_MIME_TYPES,
        image_max_side=8,
        reencode_images=True,
    )

    assert prepared.mime_type == "image/png"
    assert prepared.extension == ".png"
    assert prepared.size_bytes < 1024 * 1024
