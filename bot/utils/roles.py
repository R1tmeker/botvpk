from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    LEAD = "LEAD"
    USER_CONFIRMED = "USER_CONFIRMED"
    USER_PENDING = "USER_PENDING"


ADMIN_ROLES = {Role.SUPER_ADMIN, Role.ADMIN}
CONFIRMED_ROLES = {Role.SUPER_ADMIN, Role.ADMIN, Role.LEAD, Role.USER_CONFIRMED}
LEAD_ROLES = {Role.SUPER_ADMIN, Role.ADMIN, Role.LEAD}

