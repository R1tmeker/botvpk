from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Iterable, Optional

from ..storage.members import Member, MembersStorage, ALLOWED_ROLES, ALLOWED_STATUS
from ..storage.errors import ValidationError as StorageValidationError
from ..utils.roles import Role
from .exceptions import (
    LinkAmbiguityError,
    NotFoundError,
    ValidationServiceError,
)


@dataclass
class LinkResult:
    member: Member
    newly_confirmed: bool


class RosterService:
    def __init__(self, storage: MembersStorage):
        self.storage = storage

    def list_members(self) -> list[Member]:
        return self.storage.list_members()

    def list_active_members(self) -> list[Member]:
        return [member for member in self.list_members() if member.status == "active"]

    def get_member_by_user_id(self, tg_user_id: int) -> Optional[Member]:
        return self.storage.find_by_tg_user_id(tg_user_id)

    def get_member_by_id(self, member_id: int) -> Member:
        member = self.storage.find_by_id(member_id)
        if not member:
            raise NotFoundError(f"Member with id {member_id} not found")
        return member

    def link_member(self, fio: str, tg_user_id: int, tg_username: Optional[str]) -> LinkResult:
        matches = self.storage.find_by_fio(fio)
        if not matches:
            raise NotFoundError("ФИО не найдено в списке личного состава.")
        active_matches = [member for member in matches if member.status == "active"]
        if not active_matches:
            raise ValidationServiceError("Запись существует, но пользователь помечен как удалённый.")
        if len(active_matches) > 1:
            raise LinkAmbiguityError(
                "Найдено несколько совпадений, укажите id.",
                candidates=[member.id for member in active_matches],
            )

        member = active_matches[0]
        updated = Member(
            id=member.id,
            fio=member.fio,
            birth_date=member.birth_date,
            department=member.department,
            tg_username=tg_username or member.tg_username,
            tg_user_id=tg_user_id,
            role=member.role if member.role != Role.USER_PENDING.value else Role.USER_CONFIRMED.value,
            status=member.status,
        )
        newly_confirmed = member.role == Role.USER_PENDING.value
        self.storage.update_member(updated)
        return LinkResult(member=updated, newly_confirmed=newly_confirmed)

    def find_by_fio(self, fio: str) -> list[Member]:
        return self.storage.find_by_fio(fio)

    def set_role(self, member_id: int, role: str) -> Member:
        if role not in ALLOWED_ROLES:
            raise ValidationServiceError("Недопустимая роль.")
        member = self.get_member_by_id(member_id)
        updated = Member(
            id=member.id,
            fio=member.fio,
            birth_date=member.birth_date,
            department=member.department,
            tg_username=member.tg_username,
            tg_user_id=member.tg_user_id,
            role=role,
            status=member.status,
        )
        self.storage.update_member(updated)
        return updated

    def link_member_by_id(self, member_id: int, tg_user_id: int, tg_username: Optional[str]) -> LinkResult:
        member = self.get_member_by_id(member_id)
        if member.status != "active":
            raise ValidationServiceError("Этот участник помечен как удалённый.")
        updated = Member(
            id=member.id,
            fio=member.fio,
            birth_date=member.birth_date,
            department=member.department,
            tg_username=tg_username or member.tg_username,
            tg_user_id=tg_user_id,
            role=member.role if member.role != Role.USER_PENDING.value else Role.USER_CONFIRMED.value,
            status=member.status,
        )
        newly_confirmed = member.role == Role.USER_PENDING.value
        self.storage.update_member(updated)
        return LinkResult(member=updated, newly_confirmed=newly_confirmed)

    def set_status(self, member_id: int, status: str) -> Member:
        if status not in ALLOWED_STATUS:
            raise ValidationServiceError("Недопустимый статус.")
        member = self.get_member_by_id(member_id)
        updated = Member(
            id=member.id,
            fio=member.fio,
            birth_date=member.birth_date,
            department=member.department,
            tg_username=member.tg_username,
            tg_user_id=member.tg_user_id,
            role=member.role,
            status=status,
        )
        self.storage.update_member(updated)
        return updated

    def import_from_csv_text(self, csv_text: str) -> list[Member]:
        try:
            reader = csv.DictReader(StringIO(csv_text))
            self._validate_headers(reader.fieldnames)
            members = self.storage.parse_rows(list(reader), line_offset=2)
            self.storage.add_or_replace_members(members)
            return members
        except StorageValidationError as exc:
            raise ValidationServiceError(str(exc)) from exc

    def export_to_csv(self) -> str:
        from ..storage.members import MEMBERS_HEADERS

        members = self.storage.list_members()
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=MEMBERS_HEADERS)
        writer.writeheader()
        for member in members:
            writer.writerow(member.to_csv_row())
        return buffer.getvalue()

    def _validate_headers(self, fieldnames: Iterable[str] | None) -> None:
        from ..storage.members import MEMBERS_HEADERS

        if not fieldnames:
            raise ValidationServiceError("CSV не содержит заголовок.")
        missing = [field for field in MEMBERS_HEADERS if field not in fieldnames]
        if missing:
            raise ValidationServiceError(f"В CSV отсутствуют колонки: {', '.join(missing)}")

    def group_by_department(self, members: Optional[list[Member]] = None) -> dict[str, list[Member]]:
        members = members if members is not None else self.list_members()
        groups: dict[str, list[Member]] = {}
        for member in members:
            groups.setdefault(member.department, []).append(member)
        return groups

    def birthdays_on_date(self, target_date: date, leap_policy: str) -> list[Member]:
        result: list[Member] = []
        for member in self.list_active_members():
            if member.birth_date.month == target_date.month and member.birth_date.day == target_date.day:
                result.append(member)
            elif member.birth_date.month == 2 and member.birth_date.day == 29:
                if leap_policy == "28" and target_date.month == 2 and target_date.day == 28 and not _is_leap_year(target_date.year):
                    result.append(member)
                elif leap_policy == "01" and target_date.month == 3 and target_date.day == 1 and not _is_leap_year(target_date.year):
                    result.append(member)
        return result


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
