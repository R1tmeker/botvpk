from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from ..utils.files import atomic_write, ensure_directory
from .backup import create_backup
from .errors import ValidationError


class SheetUrlStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def get_url(self) -> str | None:
        if not self.path.exists():
            return None
        return self.path.read_text(encoding="utf-8-sig").strip() or None

    def set_url(self, url: str) -> None:
        self._validate(url)
        create_backup(self.path, self.backups_dir)
        atomic_write(self.path, url.strip() + "\n")

    def _validate(self, url: str) -> None:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValidationError("Sheet URL must start with http:// or https://")
        if not parsed.path.endswith(".csv"):
            raise ValidationError("Sheet URL must point to a CSV export")
