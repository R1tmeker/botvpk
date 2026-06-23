from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.exceptions import TelegramRetryAfter

logger = logging.getLogger(__name__)

T = TypeVar("T")

TELEGRAM_SEND_DELAY_SECONDS = 0.05
VK_SEND_DELAY_SECONDS = 0.12


async def call_telegram_with_rate_limit(
    factory: Callable[[], Awaitable[T]],
    *,
    delay_seconds: float = TELEGRAM_SEND_DELAY_SECONDS,
) -> T:
    try:
        return await factory()
    except TelegramRetryAfter as exc:
        retry_after = float(getattr(exc, "retry_after", 1) or 1)
        logger.warning("Telegram rate limit hit; retrying after %.1fs", retry_after)
        await asyncio.sleep(retry_after + 0.5)
        return await factory()
    finally:
        await asyncio.sleep(delay_seconds)


async def vk_rate_limit_pause(delay_seconds: float = VK_SEND_DELAY_SECONDS) -> None:
    await asyncio.sleep(delay_seconds)
