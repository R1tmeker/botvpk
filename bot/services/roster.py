from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Iterable, Optional

from ..storage.members import (
    ALLOWED_ROLES,
    ALLOWED_STATUS,
    MEMBERS_HEADERS,
    Member,
    MembersStorage,
)
from ..storage.errors import ValidationError as StorageValidationError
from ..utils.roles import Role
from .exceptions import LinkAmbiguityError, NotFoundError, ValidationServiceError


@dataclass
class LinkResult:
    member: Member
    newly_confirmed: bool


class RosterService:
    def __init__(self, storage: MembersStorage):
        self.storage = storage

    # ---------------------------
    # Basic accessors
    # ---------------------------
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

    def find_by_fio(self, fio: str) -> list[Member]:
        return self.storage.find_by_fio(fio)

    # ---------------------------
    # Linking / updating members
    # ---------------------------
    def link_member(self, fio: str, tg_user_id: int, tg_username: Optional[str]) -> LinkResult:
        matches = self.storage.find_by_fio(fio)
        if not matches:
            raise NotFoundError("ФИО не найдено в реестре.")
        active_matches = [member for member in matches if member.status == "active"]
        if not active_matches:
            raise ValidationServiceError("Пользователь найден, но имеет статус removed.")
        if len(active_matches) > 1:
            raise LinkAmbiguityError(
                "Найдено несколько совпадений, укажите ID.",
                candidates=[member.id for member in active_matches],
            )

        member = active_matches[0]
        updated = self._build_member(
            member,
            tg_user_id=tg_user_id,
            tg_username=tg_username or member.tg_username,
            role=member.role if member.role != Role.USER_PENDING.value else Role.USER_CONFIRMED.value,
        )
        newly_confirmed = member.role == Role.USER_PENDING.value
        self.storage.update_member(updated)
        return LinkResult(member=updated, newly_confirmed=newly_confirmed)

    def link_member_by_id(self, member_id: int, tg_user_id: int, tg_username: Optional[str]) -> LinkResult:
        member = self.get_member_by_id(member_id)
        if member.status != "active":
            raise ValidationServiceError("Этот участник помечен как removed.")
        updated = self._build_member(
            member,
            tg_user_id=tg_user_id,
            tg_username=tg_username or member.tg_username,
            role=member.role if member.role != Role.USER_PENDING.value else Role.USER_CONFIRMED.value,
        )
        newly_confirmed = member.role == Role.USER_PENDING.value
        self.storage.update_member(updated)
        return LinkResult(member=updated, newly_confirmed=newly_confirmed)

    def set_role(self, member_id: int, role: str) -> Member:
        if role not in ALLOWED_ROLES:
            raise ValidationServiceError("Недопустимая роль.")
        member = self.get_member_by_id(member_id)
        updated = self._build_member(member, role=role)
        self.storage.update_member(updated)
        return updated

    def set_status(self, member_id: int, status: str) -> Member:
        if status not in ALLOWED_STATUS:
            raise ValidationServiceError("Недопустимый статус.")
        member = self.get_member_by_id(member_id)
        updated = self._build_member(member, status=status)
        self.storage.update_member(updated)
        return updated

    def update_username(self, member: Member, new_username: Optional[str]) -> Member:
        normalized = new_username or None
        if member.tg_username == normalized:
            return member
        updated = self._build_member(member, tg_username=normalized)
        self.storage.update_member(updated)
        return updated

    # ---------------------------
    # CSV operations
    # ---------------------------
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
        members = self.storage.list_members()
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=MEMBERS_HEADERS)
        writer.writeheader()
        for member in members:
            writer.writerow(member.to_csv_row())
        return buffer.getvalue()

    # ---------------------------
    # Helpers
    # ---------------------------
    def _validate_headers(self, fieldnames: Iterable[str] | None) -> None:
        if not fieldnames:
            raise ValidationServiceError("CSV не содержит заголовок.")
        missing = [field for field in MEMBERS_HEADERS if field not in fieldnames]
        if missing:
            raise ValidationServiceError(f"В CSV отсутствуют колонки: {', '.join(missing)}")

    def group_by_department(self, members: Optional[list[Member]] = None) -> dict[str, list[Member]]:
        members = members if members is not None else self.list_members()
        grouped: dict[str, list[Member]] = {}
        for member in members:
            grouped.setdefault(member.department, []).append(member)
        return grouped

    def birthdays_on_date(self, target_date: date, leap_policy: str) -> list[Member]:
        result: list[Member] = []
        for member in self.list_active_members():
            if member.birth_date.month == target_date.month and member.birth_date.day == target_date.day:
                result.append(member)
            elif member.birth_date.month == 2 and member.birth_date.day == 29:
                if (
                    leap_policy == "28"
                    and target_date.month == 2
                    and target_date.day == 28
                    and not _is_leap_year(target_date.year)
                ):
                    result.append(member)
                elif (
                    leap_policy == "01"
                    and target_date.month == 3
                    and target_date.day == 1
                    and not _is_leap_year(target_date.year)
                ):
                    result.append(member)
        return result

    # ---------------------------
    # Internal helper
    # ---------------------------
    def _build_member(
        self,
        member: Member,
        *,
        tg_user_id: Optional[int] = None,
        tg_username: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Member:
        return Member(
            id=member.id,
            fio=member.fio,
            birth_date=member.birth_date,
            department=member.department,
            tg_username=tg_username if tg_username is not None else member.tg_username,
            tg_user_id=tg_user_id if tg_user_id is not None else member.tg_user_id,
            role=role if role is not None else member.role,
            status=status if status is not None else member.status,
        )


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

