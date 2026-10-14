from __future__ import annotations

import hashlib
import logging
import time

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
_local_claims: dict[str, float] = {}


def message_key(message) -> str | None:
    peer = getattr(message, "peer_id", message.from_id)
    # Community message IDs can be zero; conversation IDs remain scoped to the peer.
    for field in ("conversation_message_id", "id"):
        value = getattr(message, field, None)
        if isinstance(value, int) and value > 0:
            return f"botvpk:vk:inbound:{peer}:{field}:{value}"
    return None


async def claim(key: str, redis, *, ttl: int = 86400) -> bool:
    if redis is not None:
        try:
            return bool(await redis.set(key, "1", nx=True, ex=ttl))
        except RedisError:
            logger.warning("VK deduplication Redis unavailable; using process cache")
    now = time.monotonic()
    for old_key, expiry in list(_local_claims.items()):
        if expiry <= now:
            _local_claims.pop(old_key, None)
    if key in _local_claims:
        return False
    if len(_local_claims) >= 10000:
        _local_claims.pop(next(iter(_local_claims)))
    _local_claims[key] = now + ttl
    return True


async def release(key: str, redis) -> None:
    if redis is not None:
        try:
            await redis.delete(key)
        except RedisError:
            logger.warning("VK deduplication claim release unavailable")
    _local_claims.pop(key, None)


class RepeatableReplies:
    """Keep VK's random_id stable if the same incoming event is retried."""

    def __init__(self, message, key: str):
        self._message = message
        self._key = key
        self._index = 0

    def __getattr__(self, name):
        return getattr(self._message, name)

    async def answer(self, *args, **kwargs):
        digest = hashlib.sha256(f"{self._key}:{self._index}".encode()).digest()
        # Negative IDs keep replies separate from positive notification IDs.
        kwargs["random_id"] = -(int.from_bytes(digest[:4], "big") % 2_147_480_000 + 1000)
        self._index += 1
        return await self._message.answer(*args, **kwargs)
