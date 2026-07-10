from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ChannelLinkCode
from ..config import get_settings

CODE_TTL_MINUTES = 10


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _code_digest(code: str) -> str:
    pepper = get_settings().effective_link_code_pepper
    if not pepper or len(pepper) < 32:
        raise RuntimeError("LINK_CODE_PEPPER must contain at least 32 characters.")
    return hmac.new(pepper.encode(), code.strip().encode(), hashlib.sha256).hexdigest()


async def issue_link_code(
    session: AsyncSession,
    user_id: int,
    channel: str = "VK",
    ttl_minutes: int = CODE_TTL_MINUTES,
) -> tuple[str, datetime]:
    """Create a fresh one-time link code, invalidating the user's previous unused ones."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(ChannelLinkCode)
        .where(
            ChannelLinkCode.user_id == user_id,
            ChannelLinkCode.channel == channel,
            ChannelLinkCode.used_at.is_(None),
        )
        .values(used_at=now)
    )
    code = _generate_code()
    expires_at = now + timedelta(minutes=ttl_minutes)
    session.add(
        ChannelLinkCode(
            user_id=user_id,
            channel=channel,
            code=None,
            code_digest=_code_digest(code),
            expires_at=expires_at,
        )
    )
    return code, expires_at


async def redeem_link_code(session: AsyncSession, code: str, channel: str = "VK") -> int | None:
    """Consume a valid code and return its user_id, or None if invalid/expired."""
    now = datetime.now(timezone.utc)
    row = await session.scalar(
        select(ChannelLinkCode)
        .where(
            ChannelLinkCode.channel == channel,
            ChannelLinkCode.code_digest == _code_digest(code),
            ChannelLinkCode.used_at.is_(None),
            ChannelLinkCode.expires_at > now,
        )
        .order_by(ChannelLinkCode.id.desc())
    )
    if row is None:
        return None
    row.used_at = now
    return row.user_id


async def redeem_link_code_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
    channel: str,
) -> bool:
    """Consume a valid code for a specific user and channel."""
    now = datetime.now(timezone.utc)
    row = await session.scalar(
        select(ChannelLinkCode)
        .where(
            ChannelLinkCode.user_id == user_id,
            ChannelLinkCode.channel == channel,
            ChannelLinkCode.code_digest == _code_digest(code),
            ChannelLinkCode.used_at.is_(None),
            ChannelLinkCode.expires_at > now,
        )
        .order_by(ChannelLinkCode.id.desc())
    )
    if row is None:
        return False
    row.used_at = now
    return True
