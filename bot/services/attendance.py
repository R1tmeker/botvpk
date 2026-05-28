from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pytz

from ..storage.attendance import AttendanceRecord, AttendanceStorage
from ..storage.members import Member


STATUS_LABELS = {
    "present": "присутствовал",
    "absent": "отсутствовал",
    "late": "опоздал",
    "excused": "уважительная причина",
}

STATUS_ALIASES = {
    "present": "present",
    "присутствовал": "present",
    "присут": "present",
    "был": "present",
    "absent": "absent",
    "отсутствовал": "absent",
    "нет": "absent",
    "late": "late",
    "опоздал": "late",
    "excused": "excused",
    "уваж": "excused",
    "уважительная": "excused",
}


@dataclass
class AttendanceSummary:
    total: int
    present: int
    absent: int
    late: int
    excused: int


class AttendanceService:
    def __init__(self, storage: AttendanceStorage, timezone: str):
        self.storage = storage
        self.timezone = timezone

    def update_settings(self, *, timezone: str | None = None) -> None:
        if timezone:
            self.timezone = timezone

    def today(self) -> date:
        return datetime.now(pytz.timezone(self.timezone)).date()

    def normalize_status(self, raw: str) -> str:
        normalized = raw.strip().lower()
        if normalized not in STATUS_ALIASES:
            raise ValueError("Статус: present/absent/late/excused или присутствовал/отсутствовал/опоздал/уваж.")
        return STATUS_ALIASES[normalized]

    def mark(
        self,
        *,
        target: Member,
        status: str,
        marked_by: int,
        target_date: date,
        comment: str = "",
    ) -> AttendanceRecord:
        marked_at = datetime.now(pytz.timezone(self.timezone)).isoformat(timespec="minutes")
        record = AttendanceRecord(
            date=target_date.isoformat(),
            member_id=target.id,
            department=target.department,
            status=status,
            marked_by=marked_by,
            marked_at=marked_at,
            comment=comment.strip(),
        )
        self.storage.upsert(record)
        return record

    def list_for_member(self, member_id: int, limit: int = 10) -> list[AttendanceRecord]:
        records = [record for record in self.storage.list_records() if record.member_id == member_id]
        records.sort(key=lambda item: item.date, reverse=True)
        return records[:limit]

    def list_for_date(self, target_date: date, department: str | None = None) -> list[AttendanceRecord]:
        target = target_date.isoformat()
        records = [record for record in self.storage.list_records() if record.date == target]
        if department:
            records = [record for record in records if record.department == department]
        records.sort(key=lambda item: (item.department, item.member_id))
        return records

    def summarize(self, records: list[AttendanceRecord]) -> AttendanceSummary:
        return AttendanceSummary(
            total=len(records),
            present=sum(1 for item in records if item.status == "present"),
            absent=sum(1 for item in records if item.status == "absent"),
            late=sum(1 for item in records if item.status == "late"),
            excused=sum(1 for item in records if item.status == "excused"),
        )
