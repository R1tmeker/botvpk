from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .backup import create_backup
from ..utils.files import atomic_write, ensure_directory


ATTENDANCE_HEADERS = [
    "date",
    "member_id",
    "department",
    "status",
    "marked_by",
    "marked_at",
    "comment",
]


@dataclass
class AttendanceRecord:
    date: str
    member_id: int
    department: str
    status: str
    marked_by: int
    marked_at: str
    comment: str = ""

    def to_csv_row(self) -> dict[str, str]:
        return {
            "date": self.date,
            "member_id": str(self.member_id),
            "department": self.department,
            "status": self.status,
            "marked_by": str(self.marked_by),
            "marked_at": self.marked_at,
            "comment": self.comment,
        }


class AttendanceStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_records(self) -> list[AttendanceRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            rows = list(reader)
        return [self._row_to_record(row) for row in rows]

    def save_records(self, records: Iterable[AttendanceRecord]) -> None:
        ensure_directory(self.path.parent)
        create_backup(self.path, self.backups_dir)
        rows = [record.to_csv_row() for record in records]
        content = self._render(rows)
        atomic_write(self.path, content, newline="")

    def upsert(self, record: AttendanceRecord) -> None:
        records = self.list_records()
        for index, existing in enumerate(records):
            if existing.date == record.date and existing.member_id == record.member_id:
                records[index] = record
                break
        else:
            records.append(record)
        records.sort(key=lambda item: (item.date, item.department, item.member_id))
        self.save_records(records)

    def _row_to_record(self, row: dict[str, str]) -> AttendanceRecord:
        return AttendanceRecord(
            date=row["date"].strip(),
            member_id=int(row["member_id"]),
            department=row["department"].strip(),
            status=row["status"].strip(),
            marked_by=int(row["marked_by"]),
            marked_at=row["marked_at"].strip(),
            comment=row.get("comment", "").strip(),
        )

    def _render(self, rows: list[dict[str, str]]) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=ATTENDANCE_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
