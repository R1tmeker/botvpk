from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute

from app.config import Settings
from app.dependencies import auth as auth_dependencies
from app.dependencies.auth import get_current_user
from app.main import app
from app.models import User
from app.routers import auth
from app.services import sessions
from app.services.sessions import AuthSession


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_MUTATIONS = {
    ("POST", "/api/auth/telegram"),
    ("POST", "/api/auth/password/login"),
    ("POST", "/api/auth/password/reset"),
}


def _dependency_calls(dependant, target) -> bool:
    if dependant.call is target:
        return True
    return any(_dependency_calls(child, target) for child in dependant.dependencies)


def test_every_non_public_mutation_requires_an_authenticated_session() -> None:
    unprotected: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods & MUTATING_METHODS):
            if (method, route.path) in PUBLIC_MUTATIONS:
                continue
            if not _dependency_calls(route.dependant, get_current_user):
                unprotected.append(f"{method} {route.path}")
    assert unprotected == []


def production_settings() -> Settings:
    return Settings(
        BOT_TOKEN="123456789:production-bot-token",
        DATABASE_URL="postgresql+asyncpg://vpk:password@postgres/vpk",
        APP_ENV="production",
        REDIS_URL="redis://redis:6379/0",
        CLAMAV_REQUIRED=True,
        SESSION_SECRET="s" * 48,
        TOTP_ENCRYPTION_KEY="t" * 48,
        LINK_CODE_PEPPER="p" * 48,
    )


def authenticated_session(settings: Settings, csrf: str = "csrf-token") -> AuthSession:
    now = datetime.now(timezone.utc)
    return AuthSession(
        digest="session-digest",
        user_id=7,
        telegram_id=700,
        token_version=0,
        csrf_digest=sessions._digest(csrf, settings.effective_session_secret),
        created_at=now,
        absolute_expires_at=now + timedelta(hours=1),
        step_up_until=None,
    )


@pytest.mark.asyncio
async def test_production_session_cookie_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_session(*args, **kwargs) -> tuple[str, str]:
        return "opaque-session-token", "csrf-token"

    monkeypatch.setattr(auth, "create_auth_session", fake_session)
    response = Response()
    user = User(id=7, telegram_id=700, full_name="Cookie Test", role_code="PARTICIPANT")

    await auth._establish_session(response, user, production_settings(), step_up=False)

    cookies = response.headers.getlist("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("vpk_session="))
    csrf_cookie = next(value for value in cookies if value.startswith("vpk_csrf="))
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Secure" in csrf_cookie
    assert "SameSite=lax" in csrf_cookie


@pytest.mark.asyncio
async def test_mutation_rejects_missing_csrf_before_database_access(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = production_settings()
    monkeypatch.setattr(
        auth_dependencies,
        "resolve_auth_session",
        AsyncMock(return_value=authenticated_session(settings)),
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/me",
            "headers": [(b"cookie", b"vpk_session=opaque-session-token")],
        }
    )
    database = SimpleNamespace(scalar=AsyncMock())

    with pytest.raises(HTTPException) as caught:
        await get_current_user(request, database, settings)

    assert caught.value.status_code == 403
    assert caught.value.detail == "CSRF validation failed."
    database.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_mutation_accepts_matching_cookie_and_csrf_header(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = production_settings()
    auth_session = authenticated_session(settings)
    monkeypatch.setattr(auth_dependencies, "resolve_auth_session", AsyncMock(return_value=auth_session))
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/me",
            "headers": [
                (b"cookie", b"vpk_session=opaque-session-token; vpk_csrf=csrf-token"),
                (b"x-csrf-token", b"csrf-token"),
            ],
        }
    )
    user = User(
        id=7,
        telegram_id=700,
        full_name="CSRF Test",
        role_code="PARTICIPANT",
        status_code="ACTIVE",
        token_version=0,
    )
    database = SimpleNamespace(scalar=AsyncMock(return_value=user))

    current = await get_current_user(request, database, settings)

    assert current.user_id == 7
    assert current.session_token == "opaque-session-token"


def test_production_nginx_enforces_security_headers() -> None:
    config = (Path(__file__).parents[2] / "nginx" / "nginx.prod.conf").read_text(encoding="utf-8")
    assert "Content-Security-Policy-Report-Only" not in config
    assert "add_header Content-Security-Policy" in config
    csp_line = next(line for line in config.splitlines() if "add_header Content-Security-Policy" in line)
    script_policy = csp_line.split("script-src", 1)[1].split(";", 1)[0]
    assert "'unsafe-inline'" not in script_policy
    assert script_policy.strip() == "'self'"
    assert "trycloudflare.com" not in csp_line
    assert "object-src 'none'" in csp_line
    assert "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org" in csp_line
    assert "X-Frame-Options" not in config
    for header in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert f"add_header {header}" in config
