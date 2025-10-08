from __future__ import annotations

from ..context import BotContext


def log_action(context: BotContext, user_id: int, action: str, details: str | None = None) -> None:
    message = f"{action}"
    if details:
        message += f" | {details}"
    context.logger.info("[ACTION][user_id=%s] %s", user_id, message)

