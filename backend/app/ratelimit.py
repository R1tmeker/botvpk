from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings

# Shared limiter instance so routers can apply per-endpoint limits
# (e.g. password login) using the same store as the app middleware.
settings = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri=settings.redis_url or "memory://",
)
