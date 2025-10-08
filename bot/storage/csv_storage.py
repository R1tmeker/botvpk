from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from .errors import StorageError
from ..utils.files import atomic_write, ensure_directory


class Serializer(Protocol):
    def serialize(self) -> list[str]:
        ...


@dataclass
class CSVStorage:
    path: Path
    headers: list[str]

    def read_rows(self) -> list[dict[str, str]]:
        ensure_directory(self.path.parent)
        if not self.path.exists():
            self._write_rows([])
            return []

        with self.path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            missing_headers = [header for header in self.headers if header not in reader.fieldnames or not reader.fieldnames]
            if missing_headers:
                raise StorageError(f"CSV {self.path} missing headers: {', '.join(missing_headers)}")
            return list(reader)

    def _write_rows(self, rows: Iterable[dict[str, str]]) -> None:
        ensure_directory(self.path.parent)
        with self.path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.headers)
            writer.writeheader()
            writer.writerows(rows)

    def overwrite(self, rows: Iterable[dict[str, str]]) -> None:
        ensure_directory(self.path.parent)
        with tempfile_csv(self.headers, rows) as rendered:
            atomic_write(self.path, rendered)


class tempfile_csv:
    def __init__(self, headers: list[str], rows: Iterable[dict[str, str]]):
        self.headers = headers
        self.rows = list(rows)

    def __enter__(self) -> str:
        import io

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.headers)
        writer.writeheader()
        writer.writerows(self.rows)
        self._buffer = output
        return output.getvalue()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, "_buffer"):
            self._buffer.close()

