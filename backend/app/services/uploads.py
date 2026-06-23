from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedUpload:
    content: bytes
    mime_type: str
    extension: str
    size_bytes: int


IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
GENERAL_UPLOAD_MIME_TYPES = IMAGE_MIME_TYPES | {
    "application/pdf",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
}

_MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
}

_MIME_TO_PIL_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def detect_mime_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"%PDF"):
        return "application/pdf"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12].lower()
        if brand in {b"qt  "}:
            return "video/quicktime"
        return "video/mp4"
    if content.startswith(b"RIFF") and content[8:12] == b"AVI ":
        return "video/x-msvideo"
    return None


def prepare_upload(
    content: bytes,
    *,
    max_size_bytes: int,
    allowed_mime_types: set[str],
    image_max_side: int | None = None,
    reencode_images: bool = False,
) -> PreparedUpload:
    if not content:
        raise UploadValidationError("Файл пустой.")
    if len(content) > max_size_bytes:
        raise UploadValidationError("Файл слишком большой.")

    mime_type = detect_mime_type(content)
    if mime_type is None or mime_type not in allowed_mime_types:
        raise UploadValidationError("Неподдерживаемый или повреждённый тип файла.")

    if mime_type in IMAGE_MIME_TYPES:
        content = _validate_and_prepare_image(
            content,
            mime_type=mime_type,
            image_max_side=image_max_side,
            reencode=reencode_images,
        )
        if len(content) > max_size_bytes:
            raise UploadValidationError("Файл слишком большой после обработки.")

    extension = _MIME_TO_EXTENSION[mime_type]
    return PreparedUpload(
        content=content,
        mime_type=mime_type,
        extension=extension,
        size_bytes=len(content),
    )


def build_upload_path(root: Path, *parts: str, extension: str) -> Path:
    upload_dir = root.joinpath(*parts).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / f"{uuid4().hex}{extension}"


def _validate_and_prepare_image(
    content: bytes,
    *,
    mime_type: str,
    image_max_side: int | None,
    reencode: bool,
) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)
            if image_max_side:
                image.thumbnail((image_max_side, image_max_side))
            if not reencode:
                return content
            output = io.BytesIO()
            image_format = _MIME_TO_PIL_FORMAT[mime_type]
            if image_format == "JPEG":
                image = image.convert("RGB")
                image.save(output, image_format, quality=85, optimize=True)
            elif image_format == "PNG":
                image.save(output, image_format, optimize=True)
            else:
                image.save(output, image_format, quality=85, method=6)
            return output.getvalue()
    except (OSError, UnidentifiedImageError) as exc:
        raise UploadValidationError("Изображение повреждено или не поддерживается.") from exc
