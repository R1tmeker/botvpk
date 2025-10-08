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
        data["member"] = member
        return await handler(event, data)

