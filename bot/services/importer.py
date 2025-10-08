from __future__ import annotations

import requests

from ..storage.sheet_url import SheetUrlStorage
from .exceptions import ValidationServiceError
from .roster import RosterService


class SheetImporter:
    def __init__(self, roster: RosterService, storage: SheetUrlStorage):
        self.roster = roster
        self.storage = storage

    def import_from_url(self, url: str | None = None) -> int:
        target_url = url or self.storage.get_url()
        if not target_url:
            raise ValidationServiceError("URL для импорта не задан.")

        response = requests.get(target_url, timeout=10)
        if response.status_code != 200:
            raise ValidationServiceError(f"Ошибка загрузки CSV ({response.status_code}).")
        content = response.content.decode("utf-8")
        self.roster.import_from_csv_text(content)
        if url:
            self.storage.set_url(url)
        return len(self.roster.list_members())

    def import_from_bytes(self, csv_bytes: bytes, encoding: str = "utf-8") -> int:
        try:
            content = csv_bytes.decode(encoding)
        except UnicodeDecodeError as exc:
            raise ValidationServiceError("Не удалось декодировать CSV файл.") from exc
        members = self.roster.import_from_csv_text(content)
        return len(members)

