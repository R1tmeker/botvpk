from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis

from ..config import Settings

logger = logging.getLogger(__name__)
GLOBAL_CHANNEL = "botvpk:events"


async def publish_realtime_event(
    settings: Settings,
    *,
    event_type: str,
    entity_id: int | None = None,
    user_id: int | None = None,
    query_keys: list[str] | None = None,
) -> None:
    if not settings.redis_url:
        return
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    payload = json.dumps(
        {
            "type": event_type,
            "entity_id": entity_id,
            "query_keys": query_keys or [],
        },
        ensure_ascii=False,
    )
    try:
        await redis.publish(f"botvpk:user:{user_id}" if user_id is not None else GLOBAL_CHANNEL, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to publish realtime event %s", event_type)
    finally:
        await redis.aclose()


async def event_stream(
    settings: Settings,
    request: Request,
    *,
    user_id: int | None,
) -> AsyncIterator[str]:
    yield 'event: connected\ndata: {"type":"connected"}\n\n'
    if not settings.redis_url:
        while not await request.is_disconnected():
            yield ": heartbeat\n\n"
            import asyncio

            await asyncio.sleep(15)
        return
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    channels = [GLOBAL_CHANNEL]
    if user_id is not None:
        channels.append(f"botvpk:user:{user_id}")
    await pubsub.subscribe(*channels)
    try:
        while not await request.is_disconnected():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
            if message and message.get("type") == "message":
                yield f"event: invalidate\ndata: {message['data']}\n\n"
            else:
                yield ": heartbeat\n\n"
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
        await redis.aclose()
