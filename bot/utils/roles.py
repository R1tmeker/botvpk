from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    PARTICIPANT = "PARTICIPANT"
    DEPUTY_SQUAD_COMMANDER = "DEPUTY_SQUAD_COMMANDER"
    SQUAD_COMMANDER = "SQUAD_COMMANDER"
    DEPUTY_PLATOON_COMMANDER = "DEPUTY_PLATOON_COMMANDER"
    PLATOON_COMMANDER = "PLATOON_COMMANDER"

    # Legacy roles kept for existing rosters.
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    LEAD = "LEAD"
    USER_CONFIRMED = "USER_CONFIRMED"
    USER_PENDING = "USER_PENDING"


ROLE_LABELS = {
    Role.PARTICIPANT: "Участник",
    Role.DEPUTY_SQUAD_COMMANDER: "Заместитель командира отделения",
    Role.SQUAD_COMMANDER: "Командир отделения",
    Role.DEPUTY_PLATOON_COMMANDER: "Заместитель командира взвода",
    Role.PLATOON_COMMANDER: "Командир взвода",
    Role.SUPER_ADMIN: "Командир взвода",
    Role.ADMIN: "Заместитель командира взвода",
    Role.LEAD: "Командир отделения",
    Role.USER_CONFIRMED: "Участник",
    Role.USER_PENDING: "Ожидает привязки",
}

LEGACY_EFFECTIVE_ROLES = {
    Role.SUPER_ADMIN: Role.PLATOON_COMMANDER,
    Role.ADMIN: Role.DEPUTY_PLATOON_COMMANDER,
    Role.LEAD: Role.SQUAD_COMMANDER,
    Role.USER_CONFIRMED: Role.PARTICIPANT,
}


def parse_role(role: str | Role | None) -> Role | None:
    if isinstance(role, Role):
        return role
    if not role:
        return None
    try:
        return Role(role)
    except ValueError:
        return None


def effective_role(role: str | Role | None) -> Role | None:
    parsed = parse_role(role)
    if not parsed:
        return None
    return LEGACY_EFFECTIVE_ROLES.get(parsed, parsed)


def role_label(role: str | Role | None) -> str:
    parsed = parse_role(role)
    if not parsed:
        return "Не привязан"
    return ROLE_LABELS.get(parsed, parsed.value)


CONFIRMED_ROLES = {
    Role.PARTICIPANT,
    Role.DEPUTY_SQUAD_COMMANDER,
    Role.SQUAD_COMMANDER,
    Role.DEPUTY_PLATOON_COMMANDER,
    Role.PLATOON_COMMANDER,
    Role.SUPER_ADMIN,
    Role.ADMIN,
    Role.LEAD,
    Role.USER_CONFIRMED,
}

SQUAD_NOTIFY_ROLES = {
    Role.DEPUTY_SQUAD_COMMANDER,
    Role.SQUAD_COMMANDER,
    Role.DEPUTY_PLATOON_COMMANDER,
    Role.PLATOON_COMMANDER,
    Role.SUPER_ADMIN,
    Role.ADMIN,
    Role.LEAD,
}

SQUAD_ATTENDANCE_ROLES = SQUAD_NOTIFY_ROLES

ALL_ATTENDANCE_ROLES = {
    Role.SQUAD_COMMANDER,
    Role.DEPUTY_PLATOON_COMMANDER,
    Role.PLATOON_COMMANDER,
    Role.SUPER_ADMIN,
    Role.ADMIN,
    Role.LEAD,
}

PLATOON_STAFF_ROLES = {
    Role.DEPUTY_PLATOON_COMMANDER,
    Role.PLATOON_COMMANDER,
    Role.SUPER_ADMIN,
    Role.ADMIN,
}

ADMIN_ROLES = PLATOON_STAFF_ROLES
LEAD_ROLES = SQUAD_NOTIFY_ROLES

