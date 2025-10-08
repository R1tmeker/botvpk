from __future__ import annotations

from typing import Iterable

from aiogram.types import Message

from .roles import Role


async def ensure_role(message: Message, member_role: str | None, allowed_roles: Iterable[Role]) -> bool:
    allowed_values = {role.value for role in allowed_roles}
    if member_role in allowed_values:
        return True
    roles_text = ", ".join(role.name for role in allowed_roles)
    await message.answer(f"Команда доступна только ролям: {roles_text}.")
    return False

