from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import Iterable, Optional

from ..storage.errors import ValidationError as StorageValidationError
from ..storage.members import (
    ALLOWED_ROLES,
    ALLOWED_STATUS,
    MEMBERS_HEADERS,
    Member,
    MembersStorage,
)
from ..utils.roles import Role
from .exceptions import LinkAmbiguityError, NotFoundError, ValidationServiceError

_UNSET = object()


@dataclass
class LinkResult:
    member: Member
    newly_confirmed: bool


class RosterService:
    def __init__(self, storage: MembersStorage):
        self.storage = storage

    # -------- basic queries --------
    def list_members(self) -> list[Member]:
        return self.storage.list_members()

    def list_active_members(self) -> list[Member]:
        return [member for member in self.list_members() if member.status == "active"]

    def get_member_by_user_id(self, tg_user_id: int) -> Optional[Member]:
        return self.storage.find_by_tg_user_id(tg_user_id)

    def get_member_by_id(self, member_id: int) -> Member:
        member = self.storage.find_by_id(member_id)
        if not member:
            raise NotFoundError(f"Участник с id {member_id} не найден.")
        return member

    def find_by_fio(self, fio: str) -> list[Member]:
        return self.storage.find_by_fio(fio)

    # -------- linking and updates --------
    def link_member(self, fio: str, tg_user_id: int, tg_username: Optional[str]) -> LinkResult:
        existing = self.get_member_by_user_id(tg_user_id)
        if existing and existing.fio.strip().lower() != fio.strip().lower():
            raise ValidationServiceError("Этот Telegram-аккаунт уже привязан к другому участнику.")

        matches = self.storage.find_by_fio(fio)
        if not matches:
            raise NotFoundError("ФИО не найдено в реестре.")
        active_matches = [member for member in matches if member.status == "active"]
        if not active_matches:
            raise ValidationServiceError("Пользователь найден, но имеет статус removed.")
        if len(active_matches) > 1:
            raise LinkAmbiguityError(
                "Найдено несколько совпадений — укажите ID.",
                candidates=[member.id for member in active_matches],
            )

        member = active_matches[0]
        if member.tg_user_id and member.tg_user_id != tg_user_id:
            raise ValidationServiceError("Запись уже привязана к другому Telegram-аккаунту.")

        updated = self._build_member(
            member,
            tg_user_id=tg_user_id,
            tg_username=tg_username or member.tg_username,
            role=member.role if member.role != Role.USER_PENDING.value else Role.PARTICIPANT.value,
        )
        newly_confirmed = member.role == Role.USER_PENDING.value
        self.storage.update_member(updated)
        return LinkResult(member=updated, newly_confirmed=newly_confirmed)

    def link_member_by_id(self, member_id: int, tg_user_id: int, tg_username: Optional[str]) -> LinkResult:
        existing = self.get_member_by_user_id(tg_user_id)
        if existing and existing.id != member_id:
            raise ValidationServiceError("Этот Telegram-аккаунт уже привязан к другому участнику.")

        member = self.get_member_by_id(member_id)
        if member.status != "active":
            raise ValidationServiceError("Этот участник помечен как removed.")
        if member.tg_user_id and member.tg_user_id != tg_user_id:
            raise ValidationServiceError("Запись уже привязана к другому Telegram-аккаунту.")

        updated = self._build_member(
            member,
            tg_user_id=tg_user_id,
            tg_username=tg_username or member.tg_username,
            role=member.role if member.role != Role.USER_PENDING.value else Role.PARTICIPANT.value,
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

    def reset_account(self, member_id: int) -> Member:
        member = self.get_member_by_id(member_id)
        updated = self._build_member(member, tg_user_id=None, tg_username=None)
        self.storage.update_member(updated)
        return updated

    def edit_member_field(self, member_id: int, field: str, value: str) -> Member:
        member = self.get_member_by_id(member_id)
        field = field.strip()
        value = value.strip()
        if field == "fio":
            if not value:
                raise ValidationServiceError("ФИО не может быть пустым.")
            updated = self._build_member(member, fio=value)
        elif field == "birth_date":
            try:
                birth = datetime.strptime(value, "%d.%m.%Y").date()
            except ValueError as exc:
                raise ValidationServiceError("Дата рождения должна быть в формате ДД.ММ.ГГГГ.") from exc
            updated = self._build_member(member, birth_date=birth)
        elif field == "department":
            if not value:
                raise ValidationServiceError("Отделение не может быть пустым.")
            updated = self._build_member(member, department=value)
        elif field == "tg_username":
            updated = self._build_member(member, tg_username=value.lstrip("@") or None)
        elif field == "tg_user_id":
            try:
                tg_user_id = int(value) if value else None
            except ValueError as exc:
                raise ValidationServiceError("tg_user_id должен быть числом или пустым.") from exc
            updated = self._build_member(member, tg_user_id=tg_user_id)
        elif field == "role":
            updated = self.set_role(member_id, value.upper())
            return updated
        elif field == "status":
            updated = self.set_status(member_id, value.lower())
            return updated
        else:
            raise ValidationServiceError(
                "Поле можно менять только так: fio, birth_date, department, tg_username, tg_user_id, role, status."
            )
        self.storage.update_member(updated)
        return updated

    def add_member(self, fio: str, birth_date: str, department: str, tg_username: Optional[str]) -> Member:
        try:
            birth = datetime.strptime(birth_date, "%d.%m.%Y").date()
        except ValueError as exc:
            raise ValidationServiceError("Дата рождения должна быть в формате ДД.ММ.ГГГГ.") from exc

        members = self.storage.list_members()
        next_id = max((m.id for m in members), default=0) + 1
        new_member = Member(
            id=next_id,
            fio=fio.strip(),
            birth_date=birth,
            department=department.strip(),
            tg_username=tg_username or None,
            tg_user_id=None,
            role=Role.USER_PENDING.value,
            status="active",
        )
        members.append(new_member)
        members.sort(key=lambda m: m.id)
        self.storage.save_members(members)
        return new_member

    def delete_member(self, member_id: int) -> Member:
        member = self.get_member_by_id(member_id)
        self.storage.delete_member(member_id)
        return member

    # -------- CSV operations --------
    def import_from_csv_text(self, csv_text: str) -> list[Member]:
        try:
            reader = csv.DictReader(StringIO(csv_text))
            self._validate_headers(reader.fieldnames)
            imported = self.storage.parse_rows(list(reader), line_offset=2)
            return self._merge_import(imported)
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

    # -------- helpers --------
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

    # internal helpers
    def _build_member(
        self,
        member: Member,
        *,
        fio: object = _UNSET,
        birth_date: object = _UNSET,
        department: object = _UNSET,
        tg_user_id: object = _UNSET,
        tg_username: object = _UNSET,
        role: object = _UNSET,
        status: object = _UNSET,
    ) -> Member:
        return Member(
            id=member.id,
            fio=fio if fio is not _UNSET else member.fio,
            birth_date=birth_date if birth_date is not _UNSET else member.birth_date,
            department=department if department is not _UNSET else member.department,
            tg_username=tg_username if tg_username is not _UNSET else member.tg_username,
            tg_user_id=tg_user_id if tg_user_id is not _UNSET else member.tg_user_id,
            role=role if role is not _UNSET else member.role,
            status=status if status is not _UNSET else member.status,
        )

    def _merge_import(self, imported: list[Member]) -> list[Member]:
        existing = self.storage.list_members()
        existing_by_id = {member.id: member for member in existing}
        merged: list[Member] = []

        for incoming in imported:
            if incoming.id in existing_by_id:
                current = existing_by_id.pop(incoming.id)
                merged.append(
                    self._build_member(
                        incoming,
                        tg_user_id=current.tg_user_id,
                        tg_username=current.tg_username,
                        role=current.role,
                        status=current.status,
                    )
                )
            else:
                merged.append(incoming)

        merged.extend(existing_by_id.values())
        merged.sort(key=lambda m: m.id)
        self.storage.add_or_replace_members(merged)
        return merged


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
