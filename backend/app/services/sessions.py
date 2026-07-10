from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from redis.asyncio import Redis

from ..config import Settings


class SessionUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthSession:
    digest: str
    user_id: int
    telegram_id: int
    token_version: int
    csrf_digest: str
    created_at: datetime
    absolute_expires_at: datetime
    step_up_until: datetime | None

    @property
    def step_up_active(self) -> bool:
        return bool(self.step_up_until and self.step_up_until > datetime.now(timezone.utc))


def _digest(value: str, secret: str | None) -> str:
    return hmac.new((secret or "").encode(), value.encode(), hashlib.sha256).hexdigest()


@lru_cache(maxsize=8)
def _redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


def _client(settings: Settings) -> Redis:
    if not settings.redis_url:
        raise SessionUnavailableError("Redis is required for authenticated sessions.")
    return _redis(settings.redis_url)


def _session_key(digest: str) -> str:
    return f"auth:session:{digest}"


def _user_sessions_key(user_id: int) -> str:
    return f"auth:user:{user_id}:sessions"


async def create_auth_session(
    settings: Settings,
    *,
    user_id: int,
    telegram_id: int,
    token_version: int,
    step_up: bool,
) -> tuple[str, str]:
    client = _client(settings)
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    digest = _digest(token, settings.effective_session_secret)
    now = datetime.now(timezone.utc)
    absolute_expires_at = now + timedelta(minutes=settings.session_absolute_minutes)
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "token_version": token_version,
        "csrf_digest": _digest(csrf, settings.effective_session_secret),
        "created_at": now.isoformat(),
        "absolute_expires_at": absolute_expires_at.isoformat(),
        "step_up_until": (now + timedelta(minutes=5)).isoformat() if step_up else None,
    }
    ttl = min(settings.session_idle_minutes * 60, settings.session_absolute_minutes * 60)
    async with client.pipeline(transaction=True) as pipe:
        pipe.setex(_session_key(digest), ttl, json.dumps(payload, separators=(",", ":")))
        pipe.sadd(_user_sessions_key(user_id), digest)
        pipe.expire(_user_sessions_key(user_id), settings.session_absolute_minutes * 60)
        await pipe.execute()
    return token, csrf


async def resolve_auth_session(settings: Settings, token: str) -> AuthSession | None:
    client = _client(settings)
    digest = _digest(token, settings.effective_session_secret)
    raw = await client.get(_session_key(digest))
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        absolute_expires_at = datetime.fromisoformat(payload["absolute_expires_at"])
        created_at = datetime.fromisoformat(payload["created_at"])
        step_up_until = datetime.fromisoformat(payload["step_up_until"]) if payload.get("step_up_until") else None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        await client.delete(_session_key(digest))
        return None
    now = datetime.now(timezone.utc)
    if absolute_expires_at <= now:
        await delete_auth_session(settings, token, user_id=int(payload["user_id"]))
        return None
    ttl = min(settings.session_idle_minutes * 60, max(1, int((absolute_expires_at - now).total_seconds())))
    await client.expire(_session_key(digest), ttl)
    return AuthSession(
        digest=digest,
        user_id=int(payload["user_id"]),
        telegram_id=int(payload["telegram_id"]),
        token_version=int(payload.get("token_version", 0)),
        csrf_digest=str(payload["csrf_digest"]),
        created_at=created_at,
        absolute_expires_at=absolute_expires_at,
        step_up_until=step_up_until,
    )


async def mark_session_step_up(settings: Settings, token: str) -> bool:
    session = await resolve_auth_session(settings, token)
    if not session:
        return False
    client = _client(settings)
    key = _session_key(session.digest)
    raw = await client.get(key)
    if not raw:
        return False
    payload = json.loads(raw)
    payload["step_up_until"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    ttl = max(1, await client.ttl(key))
    await client.setex(key, ttl, json.dumps(payload, separators=(",", ":")))
    return True


async def delete_auth_session(settings: Settings, token: str, *, user_id: int | None = None) -> None:
    client = _client(settings)
    digest = _digest(token, settings.effective_session_secret)
    async with client.pipeline(transaction=True) as pipe:
        pipe.delete(_session_key(digest))
        if user_id is not None:
            pipe.srem(_user_sessions_key(user_id), digest)
        await pipe.execute()


async def delete_user_sessions(settings: Settings, user_id: int) -> None:
    client = _client(settings)
    set_key = _user_sessions_key(user_id)
    digests = list(await client.smembers(set_key))
    if digests:
        await client.delete(*[_session_key(digest) for digest in digests])
    await client.delete(set_key)


def csrf_matches(settings: Settings, session: AuthSession, value: str) -> bool:
    return hmac.compare_digest(session.csrf_digest, _digest(value, settings.effective_session_secret))


async def consume_fixed_window_limit(settings: Settings, key: str, *, limit: int, window_seconds: int) -> bool:
    client = _client(settings)
    redis_key = f"limit:{key}"
    async with client.pipeline(transaction=True) as pipe:
        pipe.incr(redis_key)
        pipe.ttl(redis_key)
        count, ttl = await pipe.execute()
    if ttl < 0:
        await client.expire(redis_key, window_seconds)
    return int(count) <= limit
