from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from .errors import ValidationError
from .backup import create_backup
from ..utils.files import atomic_write, ensure_directory

MEMBERS_HEADERS = [
    "id",
    "fio",
    "birth_date",
    "department",
    "tg_username",
    "tg_user_id",
    "role",
    "status",
]

ALLOWED_ROLES = {
    "SUPER_ADMIN",
    "ADMIN",
    "LEAD",
    "USER_CONFIRMED",
    "USER_PENDING",
}

ALLOWED_STATUS = {"active", "removed"}


@dataclass
class Member:
    id: int
    fio: str
    birth_date: date
    department: str
    tg_username: Optional[str]
    tg_user_id: Optional[int]
    role: str
    status: str

    @property
    def birth_date_str(self) -> str:
        return self.birth_date.strftime("%d.%m.%Y")

    def to_csv_row(self) -> dict[str, str]:
        return {
            "id": str(self.id),
            "fio": self.fio,
            "birth_date": self.birth_date_str,
            "department": self.department,
            "tg_username": (self.tg_username or "").strip(),
            "tg_user_id": str(self.tg_user_id) if self.tg_user_id else "",
            "role": self.role,
            "status": self.status,
        }


class MembersStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_members(self) -> list[Member]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            self._validate_headers(reader.fieldnames)
            rows = list(reader)
        return self.parse_rows(rows, line_offset=2)

    def save_members(self, members: Iterable[Member]) -> None:
        ensure_directory(self.path.parent)
        create_backup(self.path, self.backups_dir)
        rows = [member.to_csv_row() for member in members]
        content = self._render(rows)
        atomic_write(self.path, content, newline="")

    def find_by_id(self, member_id: int) -> Optional[Member]:
        return next((m for m in self.list_members() if m.id == member_id), None)

    def find_by_tg_user_id(self, tg_user_id: int) -> Optional[Member]:
        return next((m for m in self.list_members() if m.tg_user_id == tg_user_id), None)

    def find_by_fio(self, fio: str) -> list[Member]:
        fio_normalized = fio.strip().lower()
        return [
            member
            for member in self.list_members()
            if member.fio.strip().lower() == fio_normalized
        ]

    def update_member(self, updated_member: Member) -> None:
        members = self.list_members()
        index = next((i for i, m in enumerate(members) if m.id == updated_member.id), None)
        if index is None:
            raise ValidationError(f"Member with id {updated_member.id} not found")
        members[index] = updated_member
        self.save_members(members)

    def delete_member(self, member_id: int) -> None:
        members = self.list_members()
        filtered = [member for member in members if member.id != member_id]
        if len(filtered) == len(members):
            raise ValidationError(f"Member with id {member_id} not found")
        self.save_members(filtered)

    def add_or_replace_members(self, members: Iterable[Member]) -> None:
        member_list = list(members)
        self._validate_unique_ids(member_list)
        self.save_members(member_list)

    def parse_rows(self, rows: list[dict[str, str]], line_offset: int = 1) -> list[Member]:
        members: list[Member] = []
        seen_ids: set[int] = set()
        for index, row in enumerate(rows, start=line_offset):
            member = self._row_to_member(row, index)
            if member.id in seen_ids:
                raise ValidationError(f"Line {index}: duplicate id {member.id}")
            seen_ids.add(member.id)
            members.append(member)
        return members

    def _validate_headers(self, fieldnames: Optional[list[str]]) -> None:
        if not fieldnames:
            raise ValidationError("Members CSV has no header")
        missing = [field for field in MEMBERS_HEADERS if field not in fieldnames]
        if missing:
            raise ValidationError(f"Members CSV missing headers: {', '.join(missing)}")

    def _row_to_member(self, row: dict[str, str], line_number: int) -> Member:
        try:
            member_id = int(row["id"])
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid id value") from exc
        if member_id <= 0:
            raise ValidationError(f"Line {line_number}: id must be > 0")

        fio = row["fio"].strip()
        if not fio:
            raise ValidationError(f"Line {line_number}: fio cannot be empty")

        birth_raw = row["birth_date"].strip()
        try:
            birth_date = datetime.strptime(birth_raw, "%d.%m.%Y").date()
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid birth_date '{birth_raw}'") from exc

        department = row["department"].strip()
        tg_username = row["tg_username"].strip() or None
        tg_user_id_raw = row["tg_user_id"].strip()
        try:
            tg_user_id = int(tg_user_id_raw) if tg_user_id_raw else None
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid tg_user_id '{tg_user_id_raw}'") from exc

        role = row["role"].strip()
        if role not in ALLOWED_ROLES:
            raise ValidationError(f"Line {line_number}: unsupported role '{role}'")

        status = row["status"].strip()
        if status not in ALLOWED_STATUS:
            raise ValidationError(f"Line {line_number}: unsupported status '{status}'")

        return Member(
            id=member_id,
            fio=fio,
            birth_date=birth_date,
            department=department,
            tg_username=tg_username,
            tg_user_id=tg_user_id,
            role=role,
            status=status,
        )

    def _render(self, rows: list[dict[str, str]]) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=MEMBERS_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()

    def _validate_unique_ids(self, members: list[Member]) -> None:
        ids = [member.id for member in members]
        if len(ids) != len(set(ids)):
            raise ValidationError("Duplicate member id detected during import")
