from __future__ import annotations

from typing import Iterable

from aiogram.types import Message

from .roles import Role, effective_role, role_label


async def ensure_role(message: Message, member_role: str | None, allowed_roles: Iterable[Role]) -> bool:
    allowed_effective = {effective_role(role) for role in allowed_roles}
    current_effective = effective_role(member_role)
    if current_effective in allowed_effective:
        return True
    roles_text = ", ".join(role_label(role) for role in allowed_roles)
    await message.answer(f"Команда доступна только ролям: {roles_text}.")
    return False

