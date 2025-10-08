from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .backup import create_backup
from .errors import ValidationError
from ..utils.files import ensure_directory, atomic_write


class GreetingsStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_greetings(self) -> list[str]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig") as greeting_file:
            return [line.strip() for line in greeting_file.readlines() if line.strip()]

    def add_greeting(self, template: str) -> None:
        templates = self.list_greetings()
        templates.append(template.strip())
        self._persist(templates)

    def remove_greeting(self, index: int) -> None:
        templates = self.list_greetings()
        if not 0 <= index < len(templates):
            raise ValidationError("Invalid greeting index")
        del templates[index]
        self._persist(templates)

    def _persist(self, templates: Iterable[str]) -> None:
        templates_list = [template.strip() for template in templates if template.strip()]
        if len(templates_list) < 5:
            raise ValidationError("At least 5 greeting templates are required")
        create_backup(self.path, self.backups_dir)
        ensure_directory(self.path.parent)
        content = "\n".join(templates_list) + "\n"
        atomic_write(self.path, content)
