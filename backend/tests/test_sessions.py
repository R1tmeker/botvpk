from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.config import Settings
from app.services import sessions


def settings() -> Settings:
    return Settings(
        BOT_TOKEN="test:test",
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        SESSION_SECRET="session-secret-that-is-long-enough-for-tests",
        TOTP_ENCRYPTION_KEY="totp-key-that-is-long-enough-for-tests",
        LINK_CODE_PEPPER="link-pepper-that-is-long-enough-for-tests",
        REDIS_URL="redis://test/0",
    )


@pytest.mark.asyncio
async def test_session_lifecycle_and_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(sessions, "_redis", lambda _url: fake)
    cfg = settings()

    token, csrf = await sessions.create_auth_session(
        cfg,
        user_id=7,
        telegram_id=123,
        token_version=2,
        step_up=False,
    )
    resolved = await sessions.resolve_auth_session(cfg, token)
    assert resolved is not None
    assert resolved.user_id == 7
    assert resolved.token_version == 2
    assert sessions.csrf_matches(cfg, resolved, csrf)
    assert not sessions.csrf_matches(cfg, resolved, "wrong")

    assert await sessions.mark_session_step_up(cfg, token)
    stepped_up = await sessions.resolve_auth_session(cfg, token)
    assert stepped_up is not None and stepped_up.step_up_active

    await sessions.delete_auth_session(cfg, token, user_id=7)
    assert await sessions.resolve_auth_session(cfg, token) is None


@pytest.mark.asyncio
async def test_delete_all_user_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(sessions, "_redis", lambda _url: fake)
    cfg = settings()
    tokens = []
    for _ in range(2):
        token, _csrf = await sessions.create_auth_session(
            cfg,
            user_id=8,
            telegram_id=456,
            token_version=0,
            step_up=True,
        )
        tokens.append(token)

    await sessions.delete_user_sessions(cfg, 8)
    assert all([await sessions.resolve_auth_session(cfg, token) is None for token in tokens])
