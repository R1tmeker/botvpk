from __future__ import annotations

from ..roles import RoleLevel


def visible_audiences(role_code: str, role: RoleLevel) -> set[str]:
    audiences = {"ALL", role_code}
    if role >= RoleLevel.PARTICIPANT:
        audiences.add("PARTICIPANTS")
    if role >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        audiences.add("COMMANDERS")
    return audiences
