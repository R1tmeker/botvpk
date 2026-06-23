from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from ..config import Settings


def create_access_token(payload: dict[str, Any], settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        **payload,
        "jti": payload.get("jti") or f"{payload.get('user_id', 'public')}:{int(now.timestamp() * 1000)}",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
