from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..context import BotContext


class ContextMiddleware(BaseMiddleware):
    def __init__(self, context: BotContext):
        super().__init__()
        self.context = context

    async def __call__(self, handler, event: TelegramObject, data: dict):
        data["context"] = self.context
        return await handler(event, data)

