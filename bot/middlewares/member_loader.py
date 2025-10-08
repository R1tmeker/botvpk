from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..context import BotContext


class MemberLoaderMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        context: BotContext = data["context"]
        from_user = getattr(event, "from_user", None)
        member = None
        if from_user:
            member = context.roster_service.get_member_by_user_id(from_user.id)
            if member is not None:
                new_username = from_user.username or None
                if member.tg_username != new_username:
                    member = context.roster_service.update_username(member, new_username)
        data["member"] = member
        return await handler(event, data)
